"""СДЭК по России (DRF-2299): посылки, расчёт для корзины, сверка при оформлении."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductStatus
from apps.catalog.packaging import Package
from apps.delivery import services as delivery
from apps.delivery.models import DeliveryZone
from apps.delivery.packaging import (
    MISSING_PACKAGE,
    OVERSIZE_FOR_POINT,
    OVERWEIGHT,
    build_parcels,
)
from apps.integration_ship import services as ship
from apps.integration_ship.ports import Parcel
from apps.integration_ship.providers import cdek

# ── посылки ───────────────────────────────────────────────────────────────


def test_одна_штука_одна_посылка_её_размера():
    plan = build_parcels([(Package(2000, 30, 20, 10), 1)], max_weight_g=30000)
    assert plan.parcels == (Parcel(2000, 30, 20, 10),)


def test_делим_по_штукам_до_предела_веса():
    plan = build_parcels([(Package(4000, 40, 30, 15), 10)], max_weight_g=30000)
    assert [p.weight_g for p in plan.parcels] == [28000, 12000]
    assert all(p.weight_g <= 30000 for p in plan.parcels)


def test_коробка_вмещает_объём_и_самую_длинную_штуку():
    plan = build_parcels([(Package(500, 100, 10, 10), 10)], max_weight_g=30000)
    (box,) = plan.parcels
    assert box.length_cm >= 100
    assert box.length_cm * box.width_cm * box.height_cm >= 10 * 100 * 10 * 10


def test_кубики_складываются_в_куб_без_погрешности():
    plan = build_parcels([(Package(100, 3, 3, 3), 1)], max_weight_g=30000)
    assert plan.parcels == (Parcel(100, 3, 3, 3),)
    plan = build_parcels([(Package(100, 10, 10, 10), 8)], max_weight_g=30000)
    assert plan.parcels == (Parcel(800, 20, 20, 20),)


def test_без_упаковки_или_тяжелее_предела_считает_менеджер():
    assert build_parcels([(None, 1)], max_weight_g=30000).reason == MISSING_PACKAGE
    assert build_parcels([(Package(31000, 1, 1, 1), 1)], max_weight_g=30000).reason == OVERWEIGHT


def test_раскладка_не_зависит_от_порядка_строк():
    a, b = (Package(7000, 40, 30, 20), 3), (Package(1000, 20, 10, 10), 5)
    assert build_parcels([a, b], max_weight_g=30000) == build_parcels([b, a], max_weight_g=30000)


# ── расчёт для корзины ────────────────────────────────────────────────────

# ── предел объёма и ячейки (DRF-2503) ───────────────────────────────────────

LIMIT_CM3 = 149_500  # 29 900 г × 5000 / 1000


def _volume(p: Parcel) -> int:
    return p.length_cm * p.width_cm * p.height_cm


def test_объёмный_заказ_делится_в_пределах_объёма():
    """Лёгкие объёмные штуки: по весу влезли бы в одну посылку, по объёму — нет."""
    plan = build_parcels(
        [(Package(1000, 40, 40, 40), 10)], max_weight_g=29900, max_volume_cm3=LIMIT_CM3
    )
    assert not plan.reason
    assert sum(p.weight_g for p in plan.parcels) == 10000
    assert len(plan.parcels) > 1
    assert all(_volume(p) <= LIMIT_CM3 for p in plan.parcels)


def test_штука_больше_предела_объёма_едет_одна_без_ручного_расчёта():
    """Коробку 60³ СДЭК везёт запасным тарифом (замер 27.09), в ручной расчёт не уходит."""
    plan = build_parcels(
        [(Package(5000, 60, 60, 60), 2), (Package(1000, 10, 10, 10), 1)],
        max_weight_g=29900,
        max_volume_cm3=LIMIT_CM3,
    )
    assert not plan.reason
    big = [p for p in plan.parcels if _volume(p) > LIMIT_CM3]
    assert [p.weight_g for p in big] == [5000, 5000]


def test_без_предела_объёма_раскладка_как_раньше():
    plan = build_parcels([(Package(1000, 40, 40, 40), 10)], max_weight_g=29900)
    assert len(plan.parcels) == 1


def test_раскладка_детерминирована():
    lines = [(Package(1200, 35, 20, 15), 3), (Package(800, 50, 30, 30), 4)]
    kw = dict(max_weight_g=29900, max_volume_cm3=LIMIT_CM3)
    assert build_parcels(lines, **kw) == build_parcels(list(reversed(lines)), **kw)


def test_ячейки_пункта_посылки_помещаются_каждая():
    cells = ((60, 40, 30),)
    plan = build_parcels(
        [(Package(1000, 30, 20, 20), 6)], max_weight_g=29900, max_volume_cm3=LIMIT_CM3, cells=cells
    )
    assert not plan.reason
    for p in plan.parcels:
        sides = sorted((p.length_cm, p.width_cm, p.height_cm), reverse=True)
        assert all(s <= c for s, c in zip(sides, cells[0], strict=True))


def test_штука_не_влезает_в_ячейки_пункта():
    plan = build_parcels(
        [(Package(1000, 70, 10, 10), 1)], max_weight_g=29900, cells=((60, 40, 30),)
    )
    assert plan.reason == OVERSIZE_FOR_POINT


POINT = cdek.DeliveryPoint(
    code="MSK123", name="На Тверской", address="Москва, Тверская, 1", city_code=44
)


def _points(*points):
    """Подмена поиска пункта по коду: ``delivery_point(code)`` из заданного набора."""
    by_code = {p.code: p for p in points}
    return lambda code: by_code.get(code)


@pytest.fixture
def cdek_on(settings, monkeypatch):
    cache.clear()
    settings.FEATURES = {**settings.FEATURES, "external_ship": True}
    settings.SHIP_PROVIDER = "cdek"
    settings.CDEK_API_URL = ""
    calls = []

    def fake_tariff(code, **kw):
        calls.append({"code": code, **kw})
        return cdek.Tariff(
            code=code, name="", delivery_mode=4, cost=Decimal("408.00"), period_min=2, period_max=3
        )

    monkeypatch.setattr(cdek, "tariff", fake_tariff)
    monkeypatch.setattr(cdek, "delivery_point", _points(POINT))
    monkeypatch.setattr(cdek, "delivery_points", lambda city_code, **kw: [POINT])
    monkeypatch.setattr(cdek, "city_name", lambda code: {44: "Москва"}.get(code, ""))
    yield calls
    cache.clear()


@pytest.fixture
def zone(db):
    return DeliveryZone.objects.create(
        slug="cdek-ru", name="СДЭК по России", is_external=True, price=Decimal("0")
    )


@pytest.fixture
def goods(db):
    cat = Category.add_root(
        name="Дрели",
        slug="cr-root",
        package_weight_g=2500,
        package_length_cm=35,
        package_width_cm=25,
        package_height_cm=10,
    )
    boxed = Product.objects.create(
        name="Дрель",
        slug="cr-drel",
        price=Decimal("5000"),
        category=cat,
        status=ProductStatus.PUBLISHED,
        is_active=True,
    )
    bare_cat = Category.add_root(name="Разное", slug="cr-bare")
    bare = Product.objects.create(
        name="Без коробки",
        slug="cr-bare-p",
        price=Decimal("100"),
        category=bare_cat,
        status=ProductStatus.PUBLISHED,
        is_active=True,
    )
    return boxed, bare


PVZ = {"city_code": 44, "city_name": "Москва", "pvz_code": "MSK123"}


def test_пункт_выдачи_цена_сдэк_и_снимок(cdek_on, zone, goods):
    boxed, _ = goods
    quote, quote_id = delivery.quote_carrier(
        zone_slug="cdek-ru",
        method="cdek_pvz",
        lines=[(boxed.pk, 2)],
        goods_total=Decimal("10000"),
        destination=PVZ,
    )
    assert quote.status == delivery.CALCULATED and quote.cost == Decimal("408.00")
    assert quote_id
    snap = quote.snapshot
    assert snap["address"] == "Москва, Тверская, 1" and snap["tariff_code"] == 136
    assert snap["parcels"] == [{"weight_g": 5000, "length_cm": 35, "width_cm": 25, "height_cm": 20}]
    assert cdek_on[0]["declared_value"] == Decimal("10000")
    assert cdek_on[0]["to_code"] == 44


def test_курьеру_нужен_адрес_пункту_выдачи_пункт_из_справочника(cdek_on, zone, goods):
    boxed, _ = goods
    kw = dict(zone_slug="cdek-ru", lines=[(boxed.pk, 1)], goods_total=Decimal("1"))
    with pytest.raises(delivery.DeliveryInputError) as err:
        delivery.quote_carrier(method="cdek_courier", destination={"city_code": 44}, **kw)
    assert err.value.field == "address"
    with pytest.raises(delivery.DeliveryInputError) as err:
        delivery.quote_carrier(method="cdek_pvz", destination={**PVZ, "pvz_code": "X"}, **kw)
    assert err.value.field == "pvz_code"
    with pytest.raises(delivery.DeliveryInputError) as err:
        delivery.quote_carrier(method="cdek_pvz", destination={"city_code": "abc"}, **kw)
    assert err.value.field == "city_code"


def test_город_берётся_у_сдэк_по_коду_а_не_из_браузера(cdek_on, zone, goods):
    boxed, _ = goods
    kw = dict(
        zone_slug="cdek-ru", method="cdek_pvz", lines=[(boxed.pk, 1)], goods_total=Decimal("1")
    )
    quote, _ = delivery.quote_carrier(destination={**PVZ, "city_name": "Сочи"}, **kw)
    assert quote.snapshot["city_name"] == "Москва"
    with pytest.raises(delivery.DeliveryInputError) as err:
        delivery.quote_carrier(destination={**PVZ, "city_code": 999999}, **kw)
    assert err.value.field == "city_code"


def test_сдэк_не_ответил_на_пункты_тариф_не_запрашиваем(cdek_on, zone, goods, monkeypatch):
    def down(code):
        raise cdek.CdekError("down", retryable=True)

    monkeypatch.setattr(cdek, "delivery_point", down)
    boxed, _ = goods
    quote, _ = delivery.quote_carrier(
        zone_slug="cdek-ru",
        method="cdek_pvz",
        lines=[(boxed.pk, 1)],
        goods_total=Decimal("1"),
        destination=PVZ,
    )
    assert (quote.status, quote.reason) == (delivery.MANUAL_REQUIRED, ship.PROVIDER_UNAVAILABLE)
    assert quote.snapshot["pvz_code"] == "MSK123"
    assert cdek_on == []


def test_лимит_веса_пункта_выдачи(cdek_on, zone, goods, monkeypatch):
    small = cdek.DeliveryPoint(
        code="MSK123", name="Малый", address="А", weight_max_kg=5.0, city_code=44
    )
    monkeypatch.setattr(cdek, "delivery_point", _points(small))
    boxed, _ = goods  # 2,5 кг за штуку
    kw = dict(zone_slug="cdek-ru", method="cdek_pvz", goods_total=Decimal("1"), destination=PVZ)
    quote, _ = delivery.quote_carrier(lines=[(boxed.pk, 3)], **kw)
    assert [p["weight_g"] for p in quote.snapshot["parcels"]] == [5000, 2500]

    boxed.package_weight_g = 6000
    boxed.save(update_fields=["package_weight_g"])
    with pytest.raises(delivery.DeliveryInputError) as err:
        delivery.quote_carrier(lines=[(boxed.pk, 1)], **kw)
    assert err.value.field == "pvz_code" and "5 кг" in err.value.message


def test_товар_без_упаковки_ручной_расчёт_с_адресом(cdek_on, zone, goods):
    boxed, bare = goods
    quote, quote_id = delivery.quote_carrier(
        zone_slug="cdek-ru",
        method="cdek_pvz",
        lines=[(boxed.pk, 1), (bare.pk, 1)],
        goods_total=Decimal("5100"),
        destination=PVZ,
    )
    assert quote.status == delivery.MANUAL_REQUIRED and quote.cost is None
    assert quote.reason == MISSING_PACKAGE
    assert quote.snapshot["pvz_code"] == "MSK123"
    assert cdek_on == []


def test_сдэк_выключен_ручной_расчёт(settings, zone, goods):
    settings.FEATURES = {**settings.FEATURES, "external_ship": False}
    boxed, _ = goods
    quote, _ = delivery.quote_carrier(
        zone_slug="cdek-ru",
        method="cdek_pvz",
        lines=[(boxed.pk, 1)],
        goods_total=Decimal("1"),
        destination=PVZ,
    )
    assert (quote.status, quote.reason) == (delivery.MANUAL_REQUIRED, ship.PROVIDER_DISABLED)


class _Item:
    def __init__(self, product_id, quantity):
        self.product_id, self.quantity = product_id, quantity


def test_оформление_читает_расчёт_и_сверяет_корзину(cdek_on, zone, goods):
    boxed, bare = goods
    _, quote_id = delivery.quote_carrier(
        zone_slug="cdek-ru",
        method="cdek_pvz",
        lines=[(boxed.pk, 2)],
        goods_total=Decimal("10000"),
        destination=PVZ,
    )
    calls_before = len(cdek_on)
    kw = dict(
        zone_slug="cdek-ru",
        goods_total=Decimal("10000"),
        method="cdek_pvz",
        carrier_quote_id=quote_id,
    )
    quote = delivery.quote_for_order(items=[_Item(boxed.pk, 2)], **kw)
    assert quote.status == delivery.CALCULATED and quote.cost == Decimal("408.00")
    assert quote.is_external and quote.snapshot["quote_id"] == quote_id
    assert len(cdek_on) == calls_before  # при оформлении СДЭК не вызывается

    with pytest.raises(delivery.DeliveryQuoteError) as err:
        delivery.quote_for_order(items=[_Item(boxed.pk, 3)], **kw)
    assert err.value.code == delivery.QUOTE_STALE
    with pytest.raises(delivery.DeliveryQuoteError) as err:
        delivery.quote_for_order(items=[_Item(boxed.pk, 2)], **{**kw, "method": "cdek_courier"})
    assert err.value.code == delivery.QUOTE_STALE

    cache.clear()
    with pytest.raises(delivery.DeliveryQuoteError) as err:
        delivery.quote_for_order(items=[_Item(boxed.pk, 2)], **kw)
    assert err.value.code == delivery.QUOTE_EXPIRED


def test_без_расчёта_сдэк_при_оформлении_ручной_расчёт(cdek_on, zone, goods):
    boxed, _ = goods
    quote = delivery.quote_for_order(
        zone_slug="cdek-ru",
        goods_total=Decimal("1"),
        items=[_Item(boxed.pk, 1)],
        method="cdek_pvz",
    )
    assert (quote.status, quote.reason) == (delivery.MANUAL_REQUIRED, "no_carrier_quote")
    assert quote.cost is None


# ── справочники ───────────────────────────────────────────────────────────


def test_справочники_закрыты_когда_сдэк_выключен(settings, db):
    settings.FEATURES = {**settings.FEATURES, "external_ship": False}
    api = APIClient()
    assert api.get("/api/delivery/cdek/cities/?q=Мос").status_code == 503
    assert api.get("/api/delivery/cdek/points/?city_code=44").status_code == 503


def test_города_и_пункты_выдачи(cdek_on, monkeypatch, db):
    monkeypatch.setattr(
        cdek,
        "suggest_cities",
        lambda q, **kw: [cdek.City(code=44, name="Москва", full_name="Москва, Россия")],
    )
    api = APIClient()
    body = api.get("/api/delivery/cdek/cities/?q=Мос").json()
    assert body == {"cities": [{"code": 44, "name": "Москва", "full_name": "Москва, Россия"}]}
    body = api.get("/api/delivery/cdek/points/?city_code=44").json()
    assert body["points"][0]["code"] == "MSK123"
    assert api.get("/api/delivery/cdek/points/?city_code=x").status_code == 400


def test_сдэк_не_отвечает_503(cdek_on, monkeypatch, db):
    def boom(city_code, **kw):
        raise cdek.CdekError("down", retryable=True)

    monkeypatch.setattr(cdek, "delivery_points", boom)
    assert APIClient().get("/api/delivery/cdek/points/?city_code=45").status_code == 503


# ── пункт выдачи по коду (DRF-2503) ─────────────────────────────────────────


@pytest.mark.parametrize(
    "point",
    [
        cdek.DeliveryPoint(code="MSK123", name="", address="", city_code=504),
        cdek.DeliveryPoint(code="MSK123", name="", address="", city_code=44, type="POSTAMAT"),
        cdek.DeliveryPoint(code="MSK123", name="", address="", city_code=44, handout=False),
    ],
    ids=["другой-город", "постамат", "только-приём"],
)
def test_пункт_не_того_города_постамат_или_без_выдачи_не_принимаем(
    cdek_on, zone, goods, monkeypatch, point
):
    monkeypatch.setattr(cdek, "delivery_point", _points(point))
    boxed, _ = goods
    with pytest.raises(delivery.DeliveryInputError) as err:
        delivery.quote_carrier(
            zone_slug="cdek-ru",
            method="cdek_pvz",
            lines=[(boxed.pk, 1)],
            goods_total=Decimal("1"),
            destination=PVZ,
        )
    assert err.value.field == "pvz_code"


def test_код_пункта_неверного_формата_без_запроса_в_сдэк(cdek_on, zone, goods, monkeypatch):
    asked = []
    monkeypatch.setattr(cdek, "delivery_point", lambda code: asked.append(code))
    boxed, _ = goods
    with pytest.raises(delivery.DeliveryInputError) as err:
        delivery.quote_carrier(
            zone_slug="cdek-ru",
            method="cdek_pvz",
            lines=[(boxed.pk, 1)],
            goods_total=Decimal("1"),
            destination={**PVZ, "pvz_code": "MSK 1; x"},
        )
    assert err.value.field == "pvz_code"
    assert asked == []


def test_сдэк_отверг_код_пункта_это_ошибка_ввода_а_не_недоступность(
    cdek_on, zone, goods, monkeypatch
):
    def rejected(code):
        raise cdek.CdekError("СДЭК HTTP 400", retryable=False, status=400)

    monkeypatch.setattr(cdek, "delivery_point", rejected)
    boxed, _ = goods
    with pytest.raises(delivery.DeliveryInputError) as err:
        delivery.quote_carrier(
            zone_slug="cdek-ru",
            method="cdek_pvz",
            lines=[(boxed.pk, 1)],
            goods_total=Decimal("1"),
            destination=PVZ,
        )
    assert err.value.field == "pvz_code"


def test_посылка_не_помещается_в_ячейки_пункта(cdek_on, zone, goods, monkeypatch):
    tiny = cdek.DeliveryPoint(
        code="MSK123", name="", address="А", city_code=44, cells=((30, 20, 5),)
    )
    monkeypatch.setattr(cdek, "delivery_point", _points(tiny))
    boxed, _ = goods  # 35×25×10 — в ячейку 30×20×5 не влезает
    with pytest.raises(delivery.DeliveryInputError) as err:
        delivery.quote_carrier(
            zone_slug="cdek-ru",
            method="cdek_pvz",
            lines=[(boxed.pk, 1)],
            goods_total=Decimal("1"),
            destination=PVZ,
        )
    assert err.value.field == "pvz_code" and "не помещается" in err.value.message
    assert cdek_on == []


def test_предел_объёма_считается_от_предела_перевозчика_а_не_пункта(
    cdek_on, zone, goods, monkeypatch, settings
):
    """Лимит пункта по весу 5 кг не должен урезать объём коробки до 25 000 см³."""
    settings.CDEK_MAX_PARCEL_WEIGHT_G = 29900
    small = cdek.DeliveryPoint(code="MSK123", name="", address="А", weight_max_kg=5.0, city_code=44)
    monkeypatch.setattr(cdek, "delivery_point", _points(small))
    boxed, _ = goods
    boxed.package_weight_g = 1000
    boxed.package_length_cm = boxed.package_width_cm = boxed.package_height_cm = 30
    boxed.save()
    quote, _ = delivery.quote_carrier(
        zone_slug="cdek-ru",
        method="cdek_pvz",
        lines=[(boxed.pk, 2)],
        goods_total=Decimal("1"),
        destination=PVZ,
    )
    assert [p["weight_g"] for p in quote.snapshot["parcels"]] == [2000]
