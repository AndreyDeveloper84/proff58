"""#558 (B2B Wave 1): для юрлиц доставки нет — счёт формируется только на товары.

Контракт (#444, уточнение Wave 1): у B2B-заказа delivery_calc_status=not_required,
delivery_cost=0, зона игнорируется (не влияет на сумму), manual_required недостижим,
НДС считается от товарной суммы. Курьерская доставка — явный отказ.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.delivery.models import DeliveryZone
from apps.orders.models import DeliveryCalcStatus
from apps.orders.services import add_to_cart, place_order


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


def _b2b():
    return {
        "customer_name": "Иван Петров",
        "customer_phone": "+79001234567",
        "customer_email": "buh@romashka.ru",
        "customer_type": "b2b",
        "company_name": "ООО «Ромашка»",
        "inn": "7700000000",
        "kpp": "770001001",
        "legal_address": "г. Пенза, ул. Ленина, 1",
    }


@pytest.mark.django_db
def test_b2b_zone_ignored_delivery_not_required(cart, product, penza_zone):
    """Присланная зона не влияет на сумму: кост 0, not_required, зона очищена."""
    add_to_cart(cart, product, 1)  # 1000 < 7000 → для B2C было бы +500
    order = place_order(cart, customer_data=_b2b(), delivery={"delivery_zone": "penza"})
    assert order.delivery_calc_status == DeliveryCalcStatus.NOT_REQUIRED
    assert order.delivery_cost == Decimal("0.00")
    assert order.delivery_zone == ""
    assert order.delivery_snapshot == {"reason": "b2b_delivery_not_supported"}
    assert order.total == Decimal("1000.00")  # только товары


@pytest.mark.django_db
def test_b2b_courier_rejected(cart, product):
    add_to_cart(cart, product, 1)
    with pytest.raises(ValidationError, match="самовывоз"):
        place_order(cart, customer_data=_b2b(), delivery={"delivery_method": "courier"})


@pytest.mark.django_db
def test_b2b_pickup_allowed(cart, product):
    add_to_cart(cart, product, 1)
    order = place_order(cart, customer_data=_b2b(), delivery={"delivery_method": "pickup"})
    assert order.delivery_method == "pickup"
    assert order.delivery_calc_status == DeliveryCalcStatus.NOT_REQUIRED


@pytest.mark.django_db
def test_b2b_manual_required_impossible(cart, product, cdek_zone):
    """СДЭК без весогабаритов для B2C даёт manual_required — для B2B недостижимо."""
    add_to_cart(cart, product, 1)
    order = place_order(cart, customer_data=_b2b(), delivery={"delivery_zone": "cdek"})
    assert order.delivery_calc_status == DeliveryCalcStatus.NOT_REQUIRED
    assert order.delivery_cost == Decimal("0.00")


@pytest.mark.django_db
def test_b2b_vat_from_goods_only(settings, cart, product, penza_zone):
    """НДС считается от товарной суммы: доставка не попадает в базу."""
    settings.VAT_RATE_PERCENT = 22
    add_to_cart(cart, product, 1)  # 1000
    order = place_order(cart, customer_data=_b2b(), delivery={"delivery_zone": "penza"})

    from apps.pricing.vat import vat_breakdown

    net, vat = vat_breakdown(Decimal("1000.00"), 22)
    assert order.vat_rate == 22
    assert order.amount_without_vat == net
    assert order.vat_amount == vat


@pytest.mark.django_db
def test_b2c_delivery_unchanged(cart, product, penza_zone):
    """Контроль: для B2C зона по-прежнему считается сервером (+500 ниже порога)."""
    add_to_cart(cart, product, 1)
    order = place_order(
        cart,
        customer_data={"customer_name": "Гость", "customer_phone": "+79001234567"},
        delivery={"delivery_zone": "penza"},
    )
    assert order.delivery_calc_status == DeliveryCalcStatus.CALCULATED
    assert order.delivery_cost == Decimal("500.00")
    assert order.total == Decimal("1500.00")


@pytest.mark.django_db
def test_api_b2b_courier_rejected_and_zone_cleared(api, cart_with_item):
    """Границa API: courier → 400 на сериализаторе; зона вычищается до place_order."""
    payload = {**_b2b(), "delivery_method": "courier", "delivery_address": "Пенза, Ленина 1"}
    resp = api.post("/api/orders/", payload, format="json")
    assert resp.status_code == 400
    assert "delivery_method" in resp.json()
