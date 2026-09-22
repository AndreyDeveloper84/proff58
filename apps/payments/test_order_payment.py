"""Запуск оплаты заказа с витрины: POST /api/payments/orders/{number}/.

Главное, что проверяем — оформленный заказ не теряется ни при каком исходе:
касса выключена, ключей нет, провайдер лёг, покупатель нажал дважды. Во всех
случаях заказ остаётся, а оплату можно повторить той же кнопкой.
"""

from decimal import Decimal
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.orders.models import FulfillmentStatus, Order, OrderItem
from apps.orders.models import PaymentStatus as OrderPaymentStatus

from .atolpay.client import AtolPayError
from .models import Payment, PaymentMethod, PaymentStatus

pytestmark = pytest.mark.django_db


def make_order(**kwargs) -> Order:
    defaults = {
        "order_number": "П-PAY-001",
        "total": Decimal("5000.00"),
        "currency": "RUB",
        "customer_phone": "+79001234567",
        "payment_method": "online",
        "access_token": "guest-token-123",
    }
    order = Order.objects.create(**{**defaults, **kwargs})
    # Позиция нужна не ручке, а чеку: касса принимает платёж только вместе с
    # фискальными позициями на ту же сумму (54-ФЗ).
    OrderItem.objects.create(
        order=order,
        name="Перфоратор",
        unit="шт",
        price_final=order.total,
        quantity=1,
        line_total=order.total,
    )
    return order


def url(order: Order) -> str:
    return reverse("payments:order-payment", args=[order.order_number])


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def payments_on(settings):
    """Касса включена — состояние, в котором работают все сценарии оплаты."""
    settings.PAYMENTS_ENABLED = True


@pytest.fixture
def payments_off(settings):
    settings.PAYMENTS_ENABLED = False


ATOLPAY_REPLY = {
    "orderId": "P-PAY-001",
    "amount": 500000,
    "paymentUrl": "https://pay.atolpay.test/P-PAY-001",
}
PAY_URL = ATOLPAY_REPLY["paymentUrl"]


class TestДоступКОплате:
    @pytest.fixture(autouse=True)
    def _on(self, payments_on):
        pass

    @mock.patch("apps.payments.atolpay.service.register_payment", return_value=ATOLPAY_REPLY)
    def test_гость_с_токеном_получает_ссылку(self, _api, client):
        order = make_order()

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 200
        assert resp.json()["confirmation_url"] == PAY_URL

    @mock.patch("apps.payments.atolpay.service.register_payment", return_value=ATOLPAY_REPLY)
    def test_владелец_получает_ссылку_без_токена(self, _api, client):
        user = User.objects.create_user(phone="+79005553311", password="pass12345")
        order = make_order(user=user, access_token="")
        client.force_login(user)

        assert client.post(url(order)).status_code == 200

    # Номер заказа предсказуем, поэтому одного номера мало: без токена чужой
    # заказ оплатить (и узнать о его существовании) нельзя.
    def test_без_токена_чужой_заказ_не_найден(self, client):
        order = make_order()

        assert client.post(url(order)).status_code == 404
        assert client.post(f"{url(order)}?t=не-тот-токен").status_code == 404


class TestСостоянияЗаказа:
    @pytest.fixture(autouse=True)
    def _on(self, payments_on):
        pass

    @mock.patch("apps.payments.atolpay.service.register_payment", return_value=ATOLPAY_REPLY)
    def test_повторный_вызов_возвращает_ту_же_ссылку(self, api, client):
        """Двойной клик и «Повторить оплату» не должны плодить платежи."""
        order = make_order()

        first = client.post(f"{url(order)}?t={order.access_token}")
        second = client.post(f"{url(order)}?t={order.access_token}")

        assert first.json()["confirmation_url"] == second.json()["confirmation_url"]
        assert Payment.objects.filter(order=order).count() == 1
        assert api.call_count == 1  # второй раз в кассу не ходим

    def test_оплаченный_заказ_не_ошибка(self, client):
        """Возврат по старой ссылке после оплаты — норма, а не сбой."""
        order = make_order(payment_status=OrderPaymentStatus.PAID)

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 200
        assert resp.json()["payment_status"] == OrderPaymentStatus.PAID
        assert resp.json()["confirmation_url"] == ""

    def test_счёт_для_организации_онлайн_не_оплачивают(self, client):
        order = make_order(payment_method="invoice")

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 409
        assert resp.json()["code"] == "not_online"

    def test_отменённый_заказ_оплатить_нельзя(self, client):
        order = make_order(fulfillment_status=FulfillmentStatus.CANCELLED)

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 409
        assert resp.json()["code"] == "canceled"


class TestКассаНедоступна:
    def test_выключенная_оплата_отвечает_понятно(self, payments_off, client):
        order = make_order()

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 503
        assert resp.json()["code"] == "payments_disabled"

    @mock.patch(
        "apps.payments.atolpay.service.register_payment",
        side_effect=AtolPayError(code="NOT_CONFIGURED", message="ATOLPAY_TOKEN не задан"),
    )
    def test_сбой_провайдера_не_теряет_заказ(self, _api, payments_on, client):
        order = make_order()

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 503
        assert resp.json()["code"] == "provider_unavailable"
        order.refresh_from_db()
        assert order.payment_status != OrderPaymentStatus.PAID
        assert Order.objects.filter(pk=order.pk).exists()
        assert not Payment.objects.filter(order=order).exists()

    @mock.patch("apps.payments.atolpay.service.register_payment", return_value=ATOLPAY_REPLY)
    def test_после_сбоя_оплата_повторяется(self, _api, payments_on, client):
        """Касса поднялась — та же кнопка доводит покупателя до оплаты."""
        order = make_order()

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 200
        payment = Payment.objects.get(order=order)
        assert payment.status == PaymentStatus.PENDING
        assert payment.method == PaymentMethod.ATOLPAY


class TestРучнойРасчётДоставки:
    """DRF-2299: пока стоимость доставки не рассчитана, итог предварительный —
    платёж на него в кассу не уходит."""

    @pytest.fixture(autouse=True)
    def _on(self, payments_on):
        pass

    @mock.patch("apps.payments.atolpay.service.register_payment", return_value=ATOLPAY_REPLY)
    def test_при_ручном_расчёте_оплата_недоступна_и_платёж_не_создан(self, api, client):
        order = make_order(delivery_calc_status="manual_required", delivery_cost=None)

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 409
        assert resp.json()["code"] == "delivery_pending"
        api.assert_not_called()
        assert not Payment.objects.filter(order=order).exists()

    @mock.patch("apps.payments.atolpay.service.register_payment", return_value=ATOLPAY_REPLY)
    def test_после_расчёта_менеджером_оплата_открывается(self, _api, client):
        order = make_order(delivery_calc_status="manual_required", delivery_cost=None)
        assert client.post(f"{url(order)}?t={order.access_token}").status_code == 409

        # Менеджер ввёл стоимость и поправил итог (как в памятке админки).
        Order.objects.filter(pk=order.pk).update(
            delivery_calc_status="calculated",
            delivery_cost=Decimal("700.00"),
            total=Decimal("5700.00"),
        )
        resp = client.post(f"{url(order)}?t={order.access_token}")
        assert resp.status_code == 200
        assert resp.json()["confirmation_url"] == PAY_URL

    def test_сервис_создания_платежа_тоже_отказывает(self):
        from .services import create_payment

        order = make_order(delivery_calc_status="manual_required", delivery_cost=None)
        with pytest.raises(ValueError, match="не рассчитана"):
            create_payment(order)


class TestИстёкшийРезервПриОплате:
    """DRF-2299: оплата позже окна резерва — товар удерживается заново или честный отказ."""

    @pytest.fixture(autouse=True)
    def _on(self, payments_on):
        pass

    def _order_with_product(self, available, reservation="released", **kw):
        from apps.catalog.models import Product, ProductStatus

        product = Product.objects.create(
            name="Перфоратор",
            code_1c="pay-rh",
            slug="pay-rh",
            unit="шт",
            price=Decimal("5000.00"),
            currency="RUB",
            status=ProductStatus.PUBLISHED,
            is_active=True,
            available_quantity=Decimal(available),
        )
        order = make_order(reservation_status=reservation, **kw)
        order.items.update(product=product)
        return order, product

    @mock.patch("apps.payments.atolpay.service.register_payment", return_value=ATOLPAY_REPLY)
    def test_товар_есть_удерживаем_заново_и_даём_ссылку(self, _api, client):
        order, product = self._order_with_product("4")

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 200
        order.refresh_from_db()
        product.refresh_from_db()
        assert order.reservation_status == "held"
        assert order.reserved_until is not None
        assert product.available_quantity == Decimal("3") and product.reserved_quantity == Decimal(
            "1"
        )

    @mock.patch("apps.payments.atolpay.service.register_payment", return_value=ATOLPAY_REPLY)
    def test_товара_нет_отказ_и_платёж_не_создан(self, api, client):
        order, product = self._order_with_product("0")

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 409 and resp.json()["code"] == "reservation_expired"
        api.assert_not_called()
        assert not Payment.objects.filter(order=order).exists()
        product.refresh_from_db()
        assert product.available_quantity == Decimal("0")

    @mock.patch("apps.payments.atolpay.service.register_payment", return_value=ATOLPAY_REPLY)
    def test_при_ручном_расчёте_остаток_не_трогаем(self, api, client):
        order, product = self._order_with_product(
            "4", delivery_calc_status="manual_required", delivery_cost=None
        )
        resp = client.post(f"{url(order)}?t={order.access_token}")
        assert resp.status_code == 409 and resp.json()["code"] == "delivery_pending"
        product.refresh_from_db()
        assert product.available_quantity == Decimal("4")  # rehold не дошёл

    def test_эндпоинт_троттлится(self):
        from apps.core.throttling import OrdersRateThrottle
        from apps.payments.api import OrderPaymentView

        assert OrdersRateThrottle in OrderPaymentView.throttle_classes
