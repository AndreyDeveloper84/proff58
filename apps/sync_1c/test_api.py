"""Тесты API для 1С (/api/1c/...)."""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductStatus

API_KEY = "test-key-123"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def auth_client():
    c = APIClient()
    c.credentials(HTTP_X_API_KEY=API_KEY)
    return c


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_products_import_requires_key(client):
    resp = client.post("/api/1c/products/import", {"items": []}, format="json")
    assert resp.status_code == 403


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_products_import_creates(auth_client):
    payload = {
        "items": [
            {"external_id": "1c-100", "sku": "A-1", "name": "Дрель", "price": "1000", "stock": "3"}
        ]
    }
    resp = auth_client.post("/api/1c/products/import", payload, format="json")
    assert resp.status_code == 200
    assert resp.json()["created"] == 1
    p = Product.objects.get(code_1c="1c-100")
    assert p.price == 1000
    assert p.status == ProductStatus.NEEDS_REVIEW  # без правил — на проверку


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_products_import_validation_error(auth_client):
    # элемент без единого идентификатора
    resp = auth_client.post(
        "/api/1c/products/import", {"items": [{"name": "Без id"}]}, format="json"
    )
    assert resp.status_code == 400


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_prices_update(auth_client):
    Product.objects.create(name="Т", code_1c="1c-200", slug="t-200")
    resp = auth_client.post(
        "/api/1c/prices/update",
        {"items": [{"external_id": "1c-200", "price": "777"}]},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 1
    assert Product.objects.get(code_1c="1c-200").price == 777


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_stocks_update(auth_client):
    Product.objects.create(name="Т", code_1c="1c-300", slug="t-300")
    resp = auth_client.post(
        "/api/1c/stocks/update",
        {"items": [{"external_id": "1c-300", "stock": "10", "reserved": "2"}]},
        format="json",
    )
    assert resp.status_code == 200
    p = Product.objects.get(code_1c="1c-300")
    assert p.stock_quantity == 10
    assert p.available_quantity == 8


@override_settings(ONEC_API_KEY=API_KEY)
@pytest.mark.django_db
def test_orders_endpoints_are_stubbed(auth_client):
    assert auth_client.get("/api/1c/orders/new").status_code == 501
    assert auth_client.post("/api/1c/orders/confirm", {}, format="json").status_code == 501


@override_settings(ONEC_API_KEY="")
@pytest.mark.django_db
def test_empty_server_key_denies(auth_client):
    # если ключ на сервере не задан — доступ закрыт
    resp = auth_client.post("/api/1c/products/import", {"items": []}, format="json")
    assert resp.status_code == 403
