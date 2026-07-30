"""Админка заказа: матрица переходов и защита снимков.

До спринта 0 админка была единственным местом, где `fulfillment_status`
менялся мимо `transitions.py`, а снимки заказа (суммы НДС, промо, резерв)
правились руками. Тесты фиксируют оба правила.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite

from apps.orders.admin import OrderAdmin, OrderAdminForm
from apps.orders.models import FulfillmentStatus, Order


@pytest.fixture
def order(db):
    return Order.objects.create(
        order_number="ADM-1",
        fulfillment_status=FulfillmentStatus.NEW,
        total=Decimal("1000.00"),
    )


def _form(order, **overrides):
    """Форма админки с данными заказа и точечными переопределениями.

    Форма объявлена с ``fields="__all__"``; в реальной админке readonly-поля из
    неё исключаются (`ModelAdmin.get_form`), поэтому здесь их значения просто
    передаём — проверяем логику переходов, а не состав формы.
    """
    data = {
        "order_number": order.order_number,
        "currency": order.currency,
        "fulfillment_status": order.fulfillment_status,
        "payment_status": order.payment_status,
        "sync_1c_status": order.sync_1c_status,
        "customer_type": order.customer_type,
        "total": order.total,
        "vat_rate": order.vat_rate,
        "vat_amount": order.vat_amount,
        "amount_without_vat": order.amount_without_vat,
        "items_discount_total": order.items_discount_total,
        "delivery_discount": order.delivery_discount,
        "delivery_calc_status": order.delivery_calc_status,
        "reservation_status": order.reservation_status,
    }
    data.update(overrides)
    return OrderAdminForm(data=data, instance=order)


@pytest.mark.parametrize(
    "old,new",
    [
        (FulfillmentStatus.COMPLETED, FulfillmentStatus.NEW),
        (FulfillmentStatus.CANCELLED, FulfillmentStatus.SHIPPED),
        (FulfillmentStatus.NEW, FulfillmentStatus.SHIPPED),
        (FulfillmentStatus.READY, FulfillmentStatus.NEW),
    ],
)
def test_недопустимый_переход_отклоняется(order, old, new):
    Order.objects.filter(pk=order.pk).update(fulfillment_status=old)
    order.refresh_from_db()

    form = _form(order, fulfillment_status=new)

    assert not form.is_valid()
    assert "fulfillment_status" in form.errors


@pytest.mark.parametrize(
    "old,new",
    [
        (FulfillmentStatus.NEW, FulfillmentStatus.CONFIRMED),
        (FulfillmentStatus.NEW, FulfillmentStatus.CANCELLED),
        (FulfillmentStatus.CONFIRMED, FulfillmentStatus.ASSEMBLING),
        (FulfillmentStatus.READY, FulfillmentStatus.SHIPPED),
        (FulfillmentStatus.SHIPPED, FulfillmentStatus.COMPLETED),
    ],
)
def test_допустимый_переход_проходит(order, old, new):
    Order.objects.filter(pk=order.pk).update(fulfillment_status=old)
    order.refresh_from_db()

    form = _form(order, fulfillment_status=new)

    assert form.is_valid(), form.errors


def test_статус_без_изменения_проходит(order):
    """Сохранение карточки без смены статуса — не переход, а no-op."""
    form = _form(order, fulfillment_status=FulfillmentStatus.NEW)

    assert form.is_valid(), form.errors


def test_ошибка_называет_допустимые_статусы(order):
    """Человеку нужно знать не только «нельзя», но и «а что можно»."""
    Order.objects.filter(pk=order.pk).update(fulfillment_status=FulfillmentStatus.READY)
    order.refresh_from_db()

    form = _form(order, fulfillment_status=FulfillmentStatus.NEW)

    assert not form.is_valid()
    error = " ".join(form.errors["fulfillment_status"])
    assert "В доставке" in error and "Отменён" in error


def test_конечный_статус_объясняется_отдельно(order):
    Order.objects.filter(pk=order.pk).update(fulfillment_status=FulfillmentStatus.COMPLETED)
    order.refresh_from_db()

    form = _form(order, fulfillment_status=FulfillmentStatus.CONFIRMED)

    assert not form.is_valid()
    assert "конечный статус" in " ".join(form.errors["fulfillment_status"])


def test_новый_заказ_не_проверяется_на_переход(db):
    """У формы добавления нет исходного статуса — валидировать нечего."""
    form = OrderAdminForm(
        data={
            "order_number": "ADM-NEW",
            "currency": "RUB",
            "fulfillment_status": FulfillmentStatus.SHIPPED,
            "payment_status": "pending",
            "sync_1c_status": "pending",
            "customer_type": "b2c",
            "total": Decimal("0.00"),
            "vat_rate": 0,
            "vat_amount": Decimal("0.00"),
            "amount_without_vat": Decimal("0.00"),
            "items_discount_total": Decimal("0.00"),
            "delivery_discount": Decimal("0.00"),
            "delivery_calc_status": "not_required",
            "reservation_status": "none",
        }
    )

    assert "fulfillment_status" not in form.errors


SNAPSHOT_FIELDS = [
    "order_number",
    "promo_snapshot",
    "promo_code",
    "items_discount_total",
    "delivery_discount",
    "delivery_snapshot",
    "delivery_slot_snapshot",
    "vat_rate",
    "vat_amount",
    "amount_without_vat",
    "reservation_status",
    "reserved_until",
    "exported_at",
    "access_token",
]


@pytest.mark.parametrize("field", SNAPSHOT_FIELDS)
def test_снимки_заказа_только_для_чтения(field):
    admin_obj = OrderAdmin(Order, AdminSite())

    assert field in admin_obj.readonly_fields


@pytest.mark.parametrize("field", ["total", "delivery_cost", "delivery_calc_status"])
def test_ручной_расчёт_доставки_остаётся_доступным(field):
    """При manual_required стоимость доставки вводит менеджер (help_text поля).

    Пересчёта итогов вне place_order пока нет, поэтому заморозка этих полей
    обрубила бы сценарий. Снять — когда появится действие «Указать стоимость
    доставки», зовущее сервис.
    """
    admin_obj = OrderAdmin(Order, AdminSite())

    assert field not in admin_obj.readonly_fields
