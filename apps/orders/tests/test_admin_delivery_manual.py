"""Ручной расчёт доставки в админке (DRF-2299).

Пока стоимость не введена, итог предварительный и оплата закрыта. Ввод стоимости
сам переводит статус в «Рассчитано», но только с согласованным итогом; статус
«Рассчитано» без стоимости не сохраняется.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.orders.admin import OrderAdminForm
from apps.orders.models import DeliveryCalcStatus, Order, OrderItem


@pytest.fixture
def заказ(db):
    order = Order.objects.create(
        order_number="MAN-1",
        total=Decimal("2000.00"),  # предварительно: только товары
        delivery_method="courier",
        delivery_zone="cdek",
        delivery_calc_status=DeliveryCalcStatus.MANUAL_REQUIRED,
        delivery_cost=None,
        customer_phone="+79001112233",
    )
    OrderItem.objects.create(
        order=order,
        name="Дрель",
        quantity=2,
        price_final=Decimal("1000.00"),
        line_total=Decimal("2000.00"),
    )
    return order


def _form(order, **overrides):
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
        "delivery_cost": "" if order.delivery_cost is None else order.delivery_cost,
        "delivery_method": order.delivery_method,
        "delivery_zone": order.delivery_zone,
        "reservation_status": order.reservation_status,
    }
    data.update(overrides)
    return OrderAdminForm(data=data, instance=order)


def test_ввод_стоимости_с_верным_итогом_переводит_в_рассчитано(заказ):
    form = _form(заказ, delivery_cost="700.00", total="2700.00")
    assert form.is_valid(), form.errors
    assert form.cleaned_data["delivery_calc_status"] == DeliveryCalcStatus.CALCULATED
    assert form.delivery_auto_calculated is True


def test_ввод_стоимости_с_неверным_итогом_не_проходит(заказ):
    form = _form(заказ, delivery_cost="700.00", total="2000.00")  # итог забыли поправить
    assert not form.is_valid()
    assert "2700.00" in form.errors["total"][0]
    заказ.refresh_from_db()
    assert заказ.delivery_calc_status == DeliveryCalcStatus.MANUAL_REQUIRED


def test_рассчитано_без_стоимости_нельзя(заказ):
    form = _form(заказ, delivery_calc_status=DeliveryCalcStatus.CALCULATED)
    assert not form.is_valid()
    assert "delivery_cost" in form.errors


def test_без_изменений_форма_проходит(заказ):
    form = _form(заказ)
    assert form.is_valid(), form.errors
    assert form.cleaned_data["delivery_calc_status"] == DeliveryCalcStatus.MANUAL_REQUIRED
    assert form.delivery_auto_calculated is False
