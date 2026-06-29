"""Тесты доставки: расчёт по зонам, бесплатная доставка, самовывоз."""

from decimal import Decimal

import pytest

from apps.delivery.models import DeliveryType, DeliveryZone, PickupPoint
from apps.delivery.services import calculate


@pytest.fixture(autouse=True)
def _clean_delivery(db):
    DeliveryZone.objects.all().delete()
    PickupPoint.objects.all().delete()
    yield
    DeliveryZone.objects.all().delete()
    PickupPoint.objects.all().delete()


@pytest.fixture
def zones(_clean_delivery):
    city = DeliveryZone.objects.create(
        name="Пенза город",
        slug="test-city",
        delivery_type=DeliveryType.COURIER,
        price=Decimal("300.00"),
        free_from=Decimal("5000.00"),
        sort_order=1,
    )
    region = DeliveryZone.objects.create(
        name="Область",
        slug="test-region",
        delivery_type=DeliveryType.COURIER,
        price=Decimal("500.00"),
        free_from=Decimal("10000.00"),
        sort_order=2,
    )
    pickup = DeliveryZone.objects.create(
        name="Самовывоз",
        slug="test-pickup",
        delivery_type=DeliveryType.PICKUP,
        price=Decimal("0.00"),
        free_from=None,
        sort_order=3,
    )
    return city, region, pickup


@pytest.mark.django_db
def test_str():
    zone = DeliveryZone(name="Пенза", slug="pz")
    assert str(zone) == "Пенза"


@pytest.mark.django_db
def test_pickup_str():
    p = PickupPoint(name="Склад", address="ул. Ленина, 1")
    assert str(p) == "Склад (ул. Ленина, 1)"


@pytest.mark.django_db
def test_ordering():
    DeliveryZone.objects.create(name="Б", slug="tz-b", sort_order=2)
    DeliveryZone.objects.create(name="А", slug="tz-a", sort_order=1)
    assert list(DeliveryZone.objects.values_list("name", flat=True)) == ["А", "Б"]


@pytest.mark.django_db
def test_all_active_zones(zones):
    assert len(calculate(cart_total=Decimal("0"))) == 3


@pytest.mark.django_db
def test_city_cost(zones):
    opts = calculate(cart_total=Decimal("1000"))
    city = next(o for o in opts if o["zone"] == "test-city")
    assert city["cost"] == Decimal("300.00")
    assert city["free_delivery"] is False


@pytest.mark.django_db
def test_city_free_at_threshold(zones):
    city = next(o for o in calculate(cart_total=Decimal("5000")) if o["zone"] == "test-city")
    assert city["cost"] == Decimal("0")
    assert city["free_delivery"] is True


@pytest.mark.django_db
def test_region_cost(zones):
    region = next(o for o in calculate(cart_total=Decimal("3000")) if o["zone"] == "test-region")
    assert region["cost"] == Decimal("500.00")


@pytest.mark.django_db
def test_pickup_always_free(zones):
    pickup = next(o for o in calculate(cart_total=Decimal("0")) if o["zone"] == "test-pickup")
    assert pickup["cost"] == Decimal("0")
    assert pickup["type"] == "pickup"


@pytest.mark.django_db
def test_inactive_hidden(zones):
    city, _, _ = zones
    city.is_active = False
    city.save()
    slugs = [o["zone"] for o in calculate(cart_total=Decimal("0"))]
    assert "test-city" not in slugs


@pytest.mark.django_db
def test_empty_zones():
    assert calculate(cart_total=Decimal("0")) == []


@pytest.mark.django_db
def test_filter_by_slug(zones):
    opts = calculate(zone_slug="test-city", cart_total=Decimal("0"))
    assert len(opts) == 1


@pytest.mark.django_db
def test_nonexistent_slug():
    assert calculate(zone_slug="nope", cart_total=Decimal("0")) == []


@pytest.mark.django_db
def test_result_keys(zones):
    city = next(o for o in calculate(cart_total=Decimal("0")) if o["zone"] == "test-city")
    assert set(city.keys()) == {"zone", "name", "type", "cost", "free_delivery", "pickup_points"}


@pytest.mark.django_db
def test_pickup_points_in_result(zones):
    PickupPoint.objects.create(name="Склад", address="ул. Мира, 1", working_hours="9-18")
    pickup = next(o for o in calculate(cart_total=Decimal("0")) if o["zone"] == "test-pickup")
    assert len(pickup["pickup_points"]) == 1
    assert pickup["pickup_points"][0]["name"] == "Склад"


@pytest.mark.django_db
def test_courier_no_pickup_points(zones):
    PickupPoint.objects.create(name="Склад", address="ул. Мира, 1", working_hours="9-18")
    city = next(o for o in calculate(cart_total=Decimal("0")) if o["zone"] == "test-city")
    assert city["pickup_points"] == []


@pytest.mark.django_db
def test_below_threshold(zones):
    city = next(o for o in calculate(cart_total=Decimal("4999.99")) if o["zone"] == "test-city")
    assert city["cost"] == Decimal("300.00")
