"""Оформление заказа с доставкой СДЭК (DRF-2299): расчёт в корзине → заказ."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.catalog.models import Category
from apps.delivery.models import DeliveryZone
from apps.integration_ship.providers import cdek
from apps.orders.models import DeliveryCalcStatus, Order

pytestmark = pytest.mark.django_db

GUEST = {"customer_name": "Гость", "customer_phone": "+79001234567"}
PVZ = {
    "zone": "cdek-ru",
    "method": "cdek_pvz",
    "city_code": 44,
    "city_name": "Москва",
    "pvz_code": "MSK123",
}
POINT = cdek.DeliveryPoint(code="MSK123", name="На Тверской", address="Тверская, 1")


@pytest.fixture(autouse=True)
def cdek_on(settings, monkeypatch, product):
    cache.clear()
    settings.FEATURES = {**settings.FEATURES, "external_ship": True}
    settings.SHIP_PROVIDER = "cdek"
    settings.CDEK_API_URL = ""
    monkeypatch.setattr(
        cdek,
        "tariff",
        lambda code, **kw: cdek.Tariff(
            code=code, name="", delivery_mode=4, cost=Decimal("408.00"), period_min=2, period_max=3
        ),
    )
    monkeypatch.setattr(cdek, "delivery_points", lambda city_code, **kw: [POINT])
    monkeypatch.setattr(cdek, "city_name", lambda code: "Москва")
    DeliveryZone.objects.create(
        slug="cdek-ru", name="СДЭК по России", is_external=True, price=Decimal("0")
    )
    cat = Category.add_root(
        name="Дрели",
        slug="cc-root",
        package_weight_g=2500,
        package_length_cm=35,
        package_width_cm=25,
        package_height_cm=10,
    )
    product.category = cat
    product.save(update_fields=["category"])
    yield
    cache.clear()


def _cart(api, product, qty=1):
    resp = api.post("/api/cart/items/", {"product_id": product.id, "quantity": qty}, format="json")
    assert resp.status_code in (200, 201), resp.content


def _quote(api, **extra):
    resp = api.post("/api/cart/delivery-quote/", {**PVZ, **extra}, format="json")
    assert resp.status_code == 200, resp.content
    return resp.json()


def _order(api, quote_id, **extra):
    return api.post(
        "/api/orders/",
        {
            **GUEST,
            "delivery_method": "cdek_pvz",
            "delivery_zone": "cdek-ru",
            "delivery_quote_id": quote_id,
            **extra,
        },
        format="json",
    )


def test_расчёт_в_корзине_и_заказ_с_доставкой_сдэк(api, product):
    _cart(api, product, 2)
    body = _quote(api)
    assert body["status"] == "calculated" and body["cost"] == "408.00"
    assert (body["period_min"], body["period_max"]) == (2, 3)
    assert body["free_delivery_promo_applies"] is False

    resp = _order(api, body["quote_id"])
    assert resp.status_code == 201, resp.content
    order = Order.objects.get(order_number=resp.json()["order_number"])
    assert order.delivery_calc_status == DeliveryCalcStatus.CALCULATED
    assert order.delivery_cost == Decimal("408.00")
    assert order.total == Decimal("2408.00")
    assert order.delivery_method == "cdek_pvz"
    assert order.delivery_address == "СДЭК, пункт выдачи MSK123, Москва, Тверская, 1"
    assert order.delivery_snapshot["tariff_code"] == 136
    assert order.payment_method == "online"


def test_цену_доставки_из_браузера_сервер_не_берёт(api, product):
    _cart(api, product)
    body = _quote(api, cost="1.00", delivery_cost="1.00")
    resp = _order(api, body["quote_id"], delivery_cost="1.00", total="1.00")
    order = Order.objects.get(order_number=resp.json()["order_number"])
    assert order.delivery_cost == Decimal("408.00")


def test_корзина_изменилась_после_расчёта_409(api, product):
    _cart(api, product, 1)
    body = _quote(api)
    _cart(api, product, 1)  # ещё штука — посылка тяжелее
    resp = _order(api, body["quote_id"])
    assert resp.status_code == 409
    assert resp.json()["code"] == "delivery_quote_stale"
    assert not Order.objects.exists()


def test_расчёт_истёк_409(api, product):
    _cart(api, product)
    body = _quote(api)
    cache.clear()
    resp = _order(api, body["quote_id"])
    assert resp.status_code == 409
    assert resp.json()["code"] == "delivery_quote_expired"


def test_без_расчёта_заказ_уходит_менеджеру(api, product):
    _cart(api, product)
    resp = _order(api, "")
    assert resp.status_code == 201
    order = Order.objects.get(order_number=resp.json()["order_number"])
    assert order.delivery_calc_status == DeliveryCalcStatus.MANUAL_REQUIRED
    assert order.delivery_cost is None


def test_сдэк_только_онлайн_оплата(api, product):
    _cart(api, product)
    body = _quote(api)
    resp = _order(api, body["quote_id"], payment_method="cash")
    assert resp.status_code == 400


def test_юрлицу_доставка_сдэк_недоступна(api, product):
    _cart(api, product)
    body = _quote(api)
    resp = _order(
        api,
        body["quote_id"],
        customer_type="b2b",
        company_name="ООО Профи",
        inn="7700000000",
        kpp="770001001",
        legal_address="Пенза",
        customer_email="b@p.ru",
        payment_method="invoice",
    )
    assert resp.status_code == 400
    assert "юрлиц" in resp.json()["delivery_method"][0]


def test_способ_сдэк_без_зоны_сдэк_отклоняется(api, product):
    _cart(api, product)
    resp = _order(api, "", delivery_zone="")
    assert resp.status_code == 400


def test_промокод_бесплатная_доставка_на_сдэк_не_действует(api, product, settings):
    from apps.promotions.models import DiscountType, PromoScope, Promotion

    settings.FEATURES = {**settings.FEATURES, "promotions": True}
    Promotion.objects.create(
        name="Доставка даром",
        discount_type=DiscountType.FREE_DELIVERY,
        discount_value=Decimal("0"),
        scope=PromoScope.CART,
        promo_code="FREESHIP",
    )
    _cart(api, product)
    assert api.post("/api/cart/promo/", {"code": "FREESHIP"}, format="json").status_code == 200
    body = _quote(api)
    resp = _order(api, body["quote_id"])
    assert resp.status_code == 201, resp.content
    order = Order.objects.get(order_number=resp.json()["order_number"])
    assert order.delivery_discount == Decimal("0.00")
    assert order.total == Decimal("1408.00")

    settings.PROMO_FREE_DELIVERY_EXTERNAL = True
    _cart(api, product)
    assert api.post("/api/cart/promo/", {"code": "FREESHIP"}, format="json").status_code == 200
    body = _quote(api)
    order = Order.objects.get(order_number=_order(api, body["quote_id"]).json()["order_number"])
    assert order.delivery_discount == Decimal("408.00")
