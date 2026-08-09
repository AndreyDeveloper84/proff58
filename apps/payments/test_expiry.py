"""Истечение неоплаченных онлайн-заказов (DRF-952).

Проверяем то, что стоит денег и товара: оплаченный заказ не должен отменяться
ни при каких обстоятельствах, а неоплаченный — не должен вечно держать остаток.
Сценарии взяты из таблицы в описании задачи.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone

from apps.catalog.models import Product, ProductStatus
from apps.orders.models import (
    FulfillmentStatus,
    Order,
    OrderItem,
    ReservationStatus,
)
from apps.orders.models import PaymentStatus as OrderPaymentStatus

from .expiry import expire_one, expire_unpaid_online_orders
from .models import Payment, PaymentMethod, PaymentStatus

pytestmark = pytest.mark.django_db


def make_product(qty: int = 5) -> Product:
    return Product.objects.create(
        name="Перфоратор",
        slug=f"perf-{timezone.now().timestamp()}",
        price=Decimal("10000.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_quantity=qty,
        available_quantity=qty - 1,  # одна штука уже удержана заказом ниже
        reserved_quantity=1,
    )


def make_order(product: Product, *, minutes_left: int = -1, **kwargs) -> Order:
    """Заказ с онлайн-оплатой и удержанным резервом.

    minutes_left < 0 — резерв уже истёк (кандидат на отмену).
    """
    defaults = {
        "order_number": f"П-{timezone.now().strftime('%H%M%S%f')}",
        "total": Decimal("10000.00"),
        "currency": "RUB",
        "customer_phone": "+79001234567",
        "payment_method": "online",
        "payment_status": OrderPaymentStatus.PENDING,
        "fulfillment_status": FulfillmentStatus.NEW,
        "reservation_status": ReservationStatus.HELD,
        "reserved_until": timezone.now() + timedelta(minutes=minutes_left),
    }
    order = Order.objects.create(**{**defaults, **kwargs})
    OrderItem.objects.create(
        order=order,
        product=product,
        name=product.name,
        price_base=product.price,
        price_final=product.price,
        quantity=1,
        line_total=product.price,
    )
    return order


def make_payment(order: Order, status: str = PaymentStatus.PENDING) -> Payment:
    return Payment.objects.create(
        order=order,
        yookassa_id=f"yoo-{order.order_number}",
        method=PaymentMethod.YOOKASSA,
        status=status,
        amount=order.total,
        currency="RUB",
        idempotency_key=f"order-{order.order_number}",
    )


UNPAID = {"paid": False, "status": "pending"}
PAID = {"paid": True, "status": "succeeded"}


class TestОтменаПоТаймауту:
    @mock.patch("apps.payments.expiry._yookassa_request", return_value=UNPAID)
    def test_неоплаченный_заказ_отменяется_и_возвращает_товар(self, _api):
        product = make_product()
        order = make_order(product)
        make_payment(order)

        assert expire_one(order.pk) is True

        order.refresh_from_db()
        product.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.CANCELLED
        assert order.payment_status == OrderPaymentStatus.EXPIRED
        assert order.reservation_status == ReservationStatus.RELEASED
        assert product.available_quantity == 5  # товар вернулся в продажу
        assert product.reserved_quantity == 0

    @mock.patch("apps.payments.expiry._yookassa_request", return_value=UNPAID)
    def test_резерв_ещё_не_истёк_заказ_не_трогаем(self, _api):
        product = make_product()
        order = make_order(product, minutes_left=+10)
        make_payment(order)

        assert expire_one(order.pk) is False

        order.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.NEW
        assert order.reservation_status == ReservationStatus.HELD

    @mock.patch("apps.payments.expiry._yookassa_request", return_value=UNPAID)
    def test_повторный_прогон_ничего_не_ломает(self, _api):
        product = make_product()
        order = make_order(product)
        make_payment(order)

        assert expire_one(order.pk) is True
        assert expire_one(order.pk) is False  # уже отменён

        product.refresh_from_db()
        assert product.available_quantity == 5  # остаток не вернулся дважды


class TestОплаченныйЗаказНеТеряется:
    """Главный инвариант: за деньги покупателя товар остаётся за ним."""

    def test_оплаченный_заказ_не_кандидат(self):
        product = make_product()
        make_order(product, payment_status=OrderPaymentStatus.PAID)

        assert expire_unpaid_online_orders() == 0

    # Вебхук мог не дойти: сеть, 5xx, ретраи ЮKassa. Локальный статус тогда врёт,
    # и последнее слово — за кассой.
    @mock.patch("apps.payments.expiry._yookassa_request", return_value=PAID)
    def test_касса_говорит_оплачено_отмены_нет(self, _api):
        product = make_product()
        order = make_order(product)
        make_payment(order)

        assert expire_one(order.pk) is False

        order.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.NEW
        assert order.reservation_status == ReservationStatus.HELD

    # Молчание провайдера — не повод отдавать чужой товар.
    @mock.patch(
        "apps.payments.expiry._yookassa_request",
        side_effect=RuntimeError("YooKassa API error 503"),
    )
    def test_касса_не_ответила_отмену_откладываем(self, _api):
        product = make_product()
        order = make_order(product)
        make_payment(order)

        assert expire_one(order.pk) is False

        order.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.NEW
        assert order.reservation_status == ReservationStatus.HELD


class TestГраницы:
    @mock.patch("apps.payments.expiry._yookassa_request", return_value=UNPAID)
    def test_заказ_ушедший_в_работу_не_отменяется(self, _api):
        """Собранный заказ отменять нельзя — деньги тут решает менеджер."""
        product = make_product()
        order = make_order(product, fulfillment_status=FulfillmentStatus.SHIPPED)
        make_payment(order)

        assert expire_one(order.pk) is False

        order.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.SHIPPED

    def test_счёт_для_организации_этой_задачей_не_трогается(self):
        """B2B-счета живут 24 часа и истекают своим механизмом."""
        product = make_product()
        make_order(product, payment_method="invoice")

        assert expire_unpaid_online_orders() == 0

    @mock.patch("apps.payments.expiry._yookassa_request", return_value=UNPAID)
    def test_заказ_без_платежа_всё_равно_истекает(self, api):
        """Покупатель ушёл, не дойдя до кассы: платежа нет, резерв держится."""
        product = make_product()
        order = make_order(product)

        assert expire_one(order.pk) is True
        assert api.call_count == 0  # спрашивать про несуществующий платёж не о чем

        order.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.CANCELLED

    @mock.patch("apps.payments.expiry._yookassa_request", return_value=UNPAID)
    def test_пакетный_прогон_считает_отменённые(self, _api):
        product = make_product(qty=10)
        make_order(product)
        make_order(product)
        make_order(product, minutes_left=+10)  # ещё в резерве

        assert expire_unpaid_online_orders() == 2


class TestПоздняяОплата:
    """Деньги пришли после того, как заказ отменили по таймауту."""

    @mock.patch("apps.payments.services.verify_webhook")
    def test_отменённый_заказ_не_воскресает_молча(self, verify):
        from .services import handle_webhook

        product = make_product()
        order = make_order(
            product,
            fulfillment_status=FulfillmentStatus.CANCELLED,
            payment_status=OrderPaymentStatus.EXPIRED,
        )
        payment = make_payment(order)
        verify.return_value = {
            "id": payment.yookassa_id,
            "status": "succeeded",
            "paid": True,
            "amount": {"value": "10000.00", "currency": "RUB"},
            "metadata": {"order_id": order.id},
        }

        handle_webhook({"event": "payment.succeeded", "object": {"id": payment.yookassa_id}})

        payment.refresh_from_db()
        order.refresh_from_db()
        # Деньги пришли — платёж это фиксирует.
        assert payment.status == PaymentStatus.SUCCEEDED
        # Но заказ остаётся отменённым: товар мог уйти другому покупателю,
        # и обещать отгрузку нельзя. Случай уходит в лог для ручного разбора.
        assert order.fulfillment_status == FulfillmentStatus.CANCELLED
        assert order.payment_status == OrderPaymentStatus.EXPIRED

    @mock.patch("apps.payments.services.verify_webhook")
    def test_живой_заказ_оплата_проходит_как_обычно(self, verify):
        from .services import handle_webhook

        product = make_product()
        order = make_order(product, minutes_left=+10)
        payment = make_payment(order)
        verify.return_value = {
            "id": payment.yookassa_id,
            "status": "succeeded",
            "paid": True,
            "amount": {"value": "10000.00", "currency": "RUB"},
            "metadata": {"order_id": order.id},
        }

        handle_webhook({"event": "payment.succeeded", "object": {"id": payment.yookassa_id}})

        order.refresh_from_db()
        assert order.payment_status == OrderPaymentStatus.PAID
        assert order.fulfillment_status == FulfillmentStatus.NEW
