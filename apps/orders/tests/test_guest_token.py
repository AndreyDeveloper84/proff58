"""Тесты гостевого доступа к заказу по токену (#322)."""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductStatus


@pytest.fixture
def product(db):
    return Product.objects.create(
        name="Дрель",
        slug="drel-token",
        price=Decimal("1000.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_quantity=10,
        available_quantity=10,
    )


@pytest.fixture
def guest_client():
    return APIClient()


@pytest.mark.django_db
def test_guest_order_has_token(guest_client, product):
    guest_client.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = guest_client.post(
        "/api/orders/", {"customer_name": "Гость", "customer_phone": "+79001234567"}, format="json"
    )
    assert resp.status_code == 201
    assert "access_token" in resp.json()
    assert len(resp.json()["access_token"]) == 32


@pytest.mark.django_db
def test_guest_order_accessible_by_token(guest_client, product):
    guest_client.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    create = guest_client.post(
        "/api/orders/", {"customer_name": "Гость", "customer_phone": "+79005555555"}, format="json"
    )
    number = create.json()["order_number"]
    token = create.json()["access_token"]

    anon = APIClient()
    resp = anon.get(f"/api/orders/{number}/guest/?t={token}")
    assert resp.status_code == 200
    assert resp.json()["order_number"] == number


@pytest.mark.django_db
def test_guest_order_denied_without_token(guest_client, product):
    guest_client.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    create = guest_client.post(
        "/api/orders/", {"customer_name": "Гость", "customer_phone": "+79006666666"}, format="json"
    )
    number = create.json()["order_number"]

    anon = APIClient()
    assert anon.get(f"/api/orders/{number}/guest/").status_code == 404
    assert anon.get(f"/api/orders/{number}/guest/?t=wrong").status_code == 404
