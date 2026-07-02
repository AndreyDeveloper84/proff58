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


# ═══════════ API ═══════════


@pytest.fixture
def api_client():
    from django.test import Client

    return Client()


@pytest.mark.django_db
def test_api_zones_returns_all(api_client, zones):
    resp = api_client.get("/api/delivery/zones/")
    assert resp.status_code == 200
    data = resp.json()
    assert "zones" in data
    assert len(data["zones"]) == 3


@pytest.mark.django_db
def test_api_zones_cart_total(api_client, zones):
    resp = api_client.get("/api/delivery/zones/?cart_total=5000")
    assert resp.status_code == 200
    city = next(z for z in resp.json()["zones"] if z["zone"] == "test-city")
    assert city["free_delivery"] is True
    assert city["cost"] == 0


@pytest.mark.django_db
def test_api_zones_filter_by_zone(api_client, zones):
    resp = api_client.get("/api/delivery/zones/?zone=test-city")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["zones"]) == 1
    assert data["zones"][0]["zone"] == "test-city"


@pytest.mark.django_db
def test_api_zones_invalid_cart_total(api_client, zones):
    resp = api_client.get("/api/delivery/zones/?cart_total=abc")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_api_zones_negative_cart_total(api_client, zones):
    resp = api_client.get("/api/delivery/zones/?cart_total=-100")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_api_zones_pickup_points_included(api_client, zones):
    PickupPoint.objects.create(name="Склад", address="ул. Мира, 1", working_hours="9-18")
    resp = api_client.get("/api/delivery/zones/")
    pickup = next(z for z in resp.json()["zones"] if z["zone"] == "test-pickup")
    assert len(pickup["pickup_points"]) == 1


# ═══════════ #429 (M-05) серверный quote_for_order ═══════════


@pytest.mark.django_db
class TestQuoteForOrder:
    def _zone(self, slug, **kw):
        from apps.delivery.models import DeliveryZone

        defaults = dict(name=slug, delivery_type="courier", price=Decimal("500"), sort_order=1)
        defaults.update(kw)
        return DeliveryZone.objects.create(slug=slug, **defaults)

    def test_no_zone_not_required(self):
        from apps.delivery.services import NOT_REQUIRED, quote_for_order

        q = quote_for_order(zone_slug="", goods_total=Decimal("1000"), items=[])
        assert q.status == NOT_REQUIRED
        assert q.cost == Decimal("0.00")

    def test_unknown_zone_manual(self):
        from apps.delivery.services import MANUAL_REQUIRED, quote_for_order

        q = quote_for_order(zone_slug="nope", goods_total=Decimal("1000"), items=[])
        assert q.status == MANUAL_REQUIRED
        assert q.cost is None

    def test_pickup_zero(self):
        from apps.delivery.services import CALCULATED, quote_for_order

        self._zone("pu", delivery_type="pickup", price=Decimal("0"))
        q = quote_for_order(zone_slug="pu", goods_total=Decimal("100"), items=[])
        assert q.status == CALCULATED
        assert q.cost == Decimal("0.00")
        assert q.free_delivery is True

    def test_own_penza_below_threshold_charged(self):
        from apps.delivery.services import CALCULATED, quote_for_order

        self._zone("penza", price=Decimal("500"), free_from=Decimal("7000"))
        q = quote_for_order(zone_slug="penza", goods_total=Decimal("6999"), items=[])
        assert q.status == CALCULATED
        assert q.cost == Decimal("500")
        assert q.free_delivery is False

    def test_own_penza_at_threshold_free(self):
        from apps.delivery.services import quote_for_order

        self._zone("penza", price=Decimal("500"), free_from=Decimal("7000"))
        q = quote_for_order(zone_slug="penza", goods_total=Decimal("7000"), items=[])
        assert q.cost == Decimal("0.00")
        assert q.free_delivery is True

    def test_cdek_without_dimensions_manual(self):
        """СДЭК без весогабаритов у товара → manual_required."""
        from apps.catalog.models import Product, ProductStatus
        from apps.delivery.services import MANUAL_REQUIRED, quote_for_order

        self._zone("cdek", is_external=True, price=Decimal("0"))
        p = Product.objects.create(
            name="Т",
            slug="cdek-t",
            price=Decimal("100"),
            status=ProductStatus.PUBLISHED,
            is_active=True,
        )

        class _Item:
            product = p

        q = quote_for_order(zone_slug="cdek", goods_total=Decimal("100"), items=[_Item()])
        assert q.status == MANUAL_REQUIRED
        assert q.cost is None
        assert q.reason == "missing_dimensions"
