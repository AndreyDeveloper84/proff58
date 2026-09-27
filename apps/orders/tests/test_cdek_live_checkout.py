"""Живой проход чекаута СДЭК через API сайта на тестовом контуре api.edu.cdek.ru (DRF-2491).

Города → пункты выдачи → расчёт по корзине → заказ: цена в заказе совпадает с
показанной. Не входит в обычный прогон и CI: нужен выход в интернет. Запуск:
``CDEK_LIVE=1 pytest -m cdek_live apps/orders/tests/test_cdek_live_checkout.py``
(в docker — с ``--network host``).
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.catalog.models import Category
from apps.delivery.models import DeliveryZone
from apps.integration_ship.providers import cdek
from apps.orders.models import DeliveryCalcStatus, Order

pytestmark = [
    pytest.mark.cdek_live,
    pytest.mark.django_db,
    pytest.mark.skipif(os.environ.get("CDEK_LIVE") != "1", reason="нужен CDEK_LIVE=1"),
]

GUEST = {"customer_name": "Гость", "customer_phone": "+79001234567"}


@pytest.fixture(autouse=True)
def live_cdek(settings, product):
    cache.clear()
    settings.FEATURES = {**settings.FEATURES, "external_ship": True}
    settings.SHIP_PROVIDER = "cdek"
    settings.CDEK_API_URL = cdek.TEST_API_URL
    settings.CDEK_ACCOUNT = ""
    settings.CDEK_SECURE = ""
    settings.CDEK_ALLOW_TEST = True
    DeliveryZone.objects.create(
        slug="cdek-ru", name="СДЭК по России", is_external=True, price=Decimal("0")
    )
    cat = Category.add_root(
        name="Дрели",
        slug="live-root",
        package_weight_g=2500,
        package_length_cm=35,
        package_width_cm=25,
        package_height_cm=10,
    )
    product.category = cat
    product.save(update_fields=["category"])
    yield
    cache.clear()


def _moscow(api) -> dict:
    zones = api.get("/api/delivery/zones/").json()["zones"]
    assert any(z["zone"] == "cdek-ru" and z["carrier_available"] for z in zones)
    cities = api.get("/api/delivery/cdek/cities/", {"q": "Москва"}).json()["cities"]
    return next(c for c in cities if c["name"] == "Москва")


def _order(api, **fields):
    resp = api.post("/api/orders/", {**GUEST, "delivery_zone": "cdek-ru", **fields}, format="json")
    assert resp.status_code == 201, resp.content
    return Order.objects.get(order_number=resp.json()["order_number"])


def test_пункт_выдачи_цена_в_заказе_как_показана(api, product):
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    city = _moscow(api)
    points = api.get("/api/delivery/cdek/points/", {"city_code": city["code"]}).json()["points"]
    assert points
    quote = api.post(
        "/api/cart/delivery-quote/",
        {
            "zone": "cdek-ru",
            "method": "cdek_pvz",
            "city_code": city["code"],
            "city_name": city["name"],
            "pvz_code": points[0]["code"],
        },
        format="json",
    ).json()
    assert quote["status"] == "calculated", quote
    assert Decimal(quote["cost"]) > 0

    order = _order(api, delivery_method="cdek_pvz", delivery_quote_id=quote["quote_id"])
    assert order.delivery_calc_status == DeliveryCalcStatus.CALCULATED
    assert order.delivery_cost == Decimal(quote["cost"])
    assert points[0]["code"] in order.delivery_address


def test_курьер_цена_в_заказе_как_показана(api, product):
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    city = _moscow(api)
    quote = api.post(
        "/api/cart/delivery-quote/",
        {
            "zone": "cdek-ru",
            "method": "cdek_courier",
            "city_code": city["code"],
            "city_name": city["name"],
            "address": "ул. Тверская, 1",
        },
        format="json",
    ).json()
    assert quote["status"] == "calculated", quote

    order = _order(api, delivery_method="cdek_courier", delivery_quote_id=quote["quote_id"])
    assert order.delivery_cost == Decimal(quote["cost"])
    assert "ул. Тверская, 1" in order.delivery_address


def test_без_расчёта_адрес_покупателя_сохраняется(api, product):
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    order = _order(api, delivery_method="cdek_pvz", delivery_address="Казань, ул. Баумана, 1")
    assert order.delivery_calc_status == DeliveryCalcStatus.MANUAL_REQUIRED
    assert order.delivery_address == "Казань, ул. Баумана, 1"
