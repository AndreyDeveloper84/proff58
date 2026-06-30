"""Тесты API заказов и корзины."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.orders.models import Order


# ---------------------------------------------------------------------------
# Корзина
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_cart_add_and_get(api, product):
    resp = api.post("/api/cart/items/", {"product_id": product.id, "quantity": 2}, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["lines"]) == 1
    assert body["lines"][0]["quantity"] == 2
    assert body["lines"][0]["price_final"] == "1000.00"
    assert body["total"] == "2000.00"


@pytest.mark.django_db
def test_cart_mixed_currency_returns_400(api, product):
    """Корзина с товарами в разных валютах → 400, а не молчаливый неверный total (#7)."""
    from apps.catalog.models import Product, ProductStatus

    usd = Product.objects.create(
        name="Импортный",
        code_1c="1c-usd-api",
        slug="usd-api",
        price=Decimal("50.00"),
        currency="USD",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("10"),
    )
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    # Добавление второго товара в другой валюте — ответ собирается через _cart_response.
    resp = api.post("/api/cart/items/", {"product_id": usd.id, "quantity": 1}, format="json")
    assert resp.status_code == 400
    assert api.get("/api/cart/").status_code == 400


@pytest.mark.django_db
def test_cart_update_and_delete(api, product):
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 2}, format="json")
    cart = api.get("/api/cart/").json()
    item_id = cart["lines"][0]["id"]

    resp = api.patch(f"/api/cart/items/{item_id}/", {"quantity": 5}, format="json")
    assert resp.status_code == 200
    assert resp.json()["lines"][0]["quantity"] == 5

    resp = api.delete(f"/api/cart/items/{item_id}/")
    assert resp.status_code == 200
    assert resp.json()["lines"] == []


# ---------------------------------------------------------------------------
# Backend-цена: тело запроса игнорируется
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_order_ignores_price_from_body(api, product):
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 2}, format="json")
    # Подкладываем фейковую цену в тело — должна быть проигнорирована.
    resp = api.post(
        "/api/orders/",
        {
            "customer_name": "Гость",
            "customer_phone": "+79990000000",
            "price": "1",
            "price_final": "1",
            "total": "1",
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["total"] == "2000.00"
    assert body["items"][0]["price_final"] == "1000.00"


@pytest.mark.django_db
def test_order_empty_cart_rejected(api):
    resp = api.post("/api/orders/", {"customer_name": "Гость"}, format="json")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Доступ к заказам
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_orders_list_requires_auth(api):
    resp = api.get("/api/orders/")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_orders_list_only_own(api, b2c_user, product):
    api.force_authenticate(user=b2c_user)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    api.post("/api/orders/", {}, format="json")

    resp = api.get("/api/orders/")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.django_db
def test_order_detail_owner_only(api, b2c_user, b2b_user, product):
    api.force_authenticate(user=b2c_user)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    create = api.post("/api/orders/", {}, format="json")
    number = create.json()["order_number"]

    # Владелец видит
    resp = api.get(f"/api/orders/{number}/")
    assert resp.status_code == 200

    # Чужой пользователь — не видит (404)
    other = type(api)()
    other.force_authenticate(user=b2b_user)
    resp = other.get(f"/api/orders/{number}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_order_detail_anonymous_closed(api, b2c_user, product):
    api.force_authenticate(user=b2c_user)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    number = api.post("/api/orders/", {}, format="json").json()["order_number"]

    anon = type(api)()
    resp = anon.get(f"/api/orders/{number}/")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_b2b_order_via_api_snapshots_requisites(api, b2b_user, product):
    from .conftest import make_wholesale

    make_wholesale(product, "800.00")
    api.force_authenticate(user=b2b_user)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 2}, format="json")
    resp = api.post("/api/orders/", {}, format="json")
    assert resp.status_code == 201
    body = resp.json()
    assert body["customer_type"] == "b2b"
    assert body["inn"] == "7700000000"
    assert body["items"][0]["price_final"] == "800.00"
    assert body["total"] == "1600.00"


@pytest.mark.django_db
def test_order_persisted_after_api_create(api, b2c_user, product):
    api.force_authenticate(user=b2c_user)
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    api.post("/api/orders/", {}, format="json")
    assert Order.objects.filter(user=b2c_user).count() == 1
    order = Order.objects.get(user=b2c_user)
    assert order.total == Decimal("1000.00")
