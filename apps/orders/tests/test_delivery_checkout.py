"""Серверный расчёт доставки в checkout (#429, M-05, ADR #444).

Стоимость доставки считается сервером по серверной корзине, входит в итог заказа
и облагается НДС вместе с товарами. СДЭК без весогабаритов → manual_required.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.delivery.models import DeliveryZone
from apps.orders.models import DeliveryCalcStatus
from apps.orders.services import add_to_cart, place_order


@pytest.fixture
def pickup_zone(db):
    return DeliveryZone.objects.create(
        slug="pu", name="Самовывоз", delivery_type="pickup", price=Decimal("0")
    )


@pytest.fixture
def penza_zone(db):
    return DeliveryZone.objects.create(
        slug="penza", name="Пенза (курьер)", price=Decimal("500"), free_from=Decimal("7000")
    )


@pytest.fixture
def cdek_zone(db):
    return DeliveryZone.objects.create(
        slug="cdek", name="Область (СДЭК)", is_external=True, price=Decimal("0")
    )


def _guest():
    return {"customer_name": "Гость", "customer_phone": "+79001234567"}


@pytest.mark.django_db
def test_pickup_zero_cost(cart, product, pickup_zone):
    product.available_quantity = Decimal("5")
    product.save(update_fields=["available_quantity"])
    add_to_cart(cart, product, 1)  # 1000
    order = place_order(cart, customer_data=_guest(), delivery={"delivery_zone": "pu"})
    assert order.delivery_calc_status == DeliveryCalcStatus.CALCULATED
    assert order.delivery_cost == Decimal("0.00")
    assert order.total == Decimal("1000.00")


@pytest.mark.django_db
def test_penza_below_threshold_adds_delivery(cart, product, penza_zone):
    product.available_quantity = Decimal("5")
    product.save(update_fields=["available_quantity"])
    add_to_cart(cart, product, 1)  # 1000 < 7000
    order = place_order(cart, customer_data=_guest(), delivery={"delivery_zone": "penza"})
    assert order.delivery_cost == Decimal("500.00")
    assert order.total == Decimal("1500.00")  # 1000 + 500


@pytest.mark.django_db
def test_penza_free_from_threshold(cart, product, penza_zone):
    product.available_quantity = Decimal("10")
    product.save(update_fields=["available_quantity"])
    add_to_cart(cart, product, 7)  # 7000 ≥ 7000 → бесплатно
    order = place_order(cart, customer_data=_guest(), delivery={"delivery_zone": "penza"})
    assert order.delivery_cost == Decimal("0.00")
    assert order.total == Decimal("7000.00")


@pytest.mark.django_db
def test_cdek_manual_required_preliminary_total(cart, product, cdek_zone):
    """СДЭК без весогабаритов → стоимость неизвестна, итог предварительный (товары)."""
    product.available_quantity = Decimal("5")
    product.save(update_fields=["available_quantity"])
    add_to_cart(cart, product, 2)  # 2000
    order = place_order(cart, customer_data=_guest(), delivery={"delivery_zone": "cdek"})
    assert order.delivery_calc_status == DeliveryCalcStatus.MANUAL_REQUIRED
    assert order.delivery_cost is None
    assert order.total == Decimal("2000.00")  # только товары


@pytest.mark.django_db
def test_b2b_vat_includes_delivery(cart, product, penza_zone, b2b_user):
    add_to_cart(cart, product, 1)  # 1000 + 500 доставка = 1500
    order = place_order(cart, user=b2b_user, delivery={"delivery_zone": "penza"})
    assert order.total == Decimal("1500.00")
    # НДС 22% на (товары+доставка): 1500*22/122 = 270.49; без НДС = 1229.51.
    assert order.vat_rate == 22
    assert order.vat_amount == Decimal("270.49")
    assert order.amount_without_vat == Decimal("1229.51")


@pytest.mark.django_db
def test_no_zone_not_required(cart, product):
    product.available_quantity = Decimal("5")
    product.save(update_fields=["available_quantity"])
    add_to_cart(cart, product, 1)
    order = place_order(cart, customer_data=_guest(), delivery={})
    assert order.delivery_calc_status == DeliveryCalcStatus.NOT_REQUIRED
    assert order.total == Decimal("1000.00")
