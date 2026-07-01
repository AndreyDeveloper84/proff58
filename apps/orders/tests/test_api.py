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
# Undo-удаление (#380)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_cart_delete_is_soft(api, product):
    """DELETE скрывает строку (soft-delete), физически не удаляет."""
    from apps.orders.models import CartItem

    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    item_id = api.get("/api/cart/").json()["lines"][0]["id"]

    resp = api.delete(f"/api/cart/items/{item_id}/")
    assert resp.status_code == 200
    assert resp.json()["lines"] == []

    # Строка в БД, но помечена как удалённая
    item = CartItem.objects.get(pk=item_id)
    assert item.is_deleted is True
    assert item.deleted_at is not None


@pytest.mark.django_db
def test_cart_restore_after_delete(api, product):
    """POST /restore/ возвращает строку в корзину."""
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 3}, format="json")
    item_id = api.get("/api/cart/").json()["lines"][0]["id"]

    api.delete(f"/api/cart/items/{item_id}/")
    assert api.get("/api/cart/").json()["lines"] == []

    resp = api.post(f"/api/cart/items/{item_id}/restore/")
    assert resp.status_code == 200
    lines = resp.json()["lines"]
    assert len(lines) == 1
    assert lines[0]["quantity"] == 3


@pytest.mark.django_db
def test_cart_restore_twice_is_404(api, product):
    """Повторный /restore/ для уже восстановленной строки → 404."""
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    item_id = api.get("/api/cart/").json()["lines"][0]["id"]

    api.delete(f"/api/cart/items/{item_id}/")
    api.post(f"/api/cart/items/{item_id}/restore/")
    resp = api.post(f"/api/cart/items/{item_id}/restore/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_cart_add_after_delete_restores(api, product):
    """Добавление товара, у которого есть soft-deleted строка — восстанавливает её."""
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 2}, format="json")
    item_id = api.get("/api/cart/").json()["lines"][0]["id"]

    api.delete(f"/api/cart/items/{item_id}/")
    resp = api.post("/api/cart/items/", {"product_id": product.id, "quantity": 5}, format="json")
    assert resp.status_code == 200
    lines = resp.json()["lines"]
    assert len(lines) == 1
    assert lines[0]["quantity"] == 5


# ---------------------------------------------------------------------------
# Смешение валют в корзине (#375)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_cart_no_mixed_currencies_by_default(api, product):
    """Однородная корзина: has_mixed_currencies=False, total корректен."""
    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 2}, format="json")
    body = api.get("/api/cart/").json()
    assert body["has_mixed_currencies"] is False
    assert body["total"] == "2000.00"


@pytest.mark.django_db
def test_cart_mixed_currencies_zeroes_total(api, product, db):
    """Корзина с двумя валютами: has_mixed_currencies=True, total='0.00' (#375)."""
    from apps.catalog.models import ProductStatus

    # product уже стоит 1000 RUB (из conftest); добавляем USD-товар
    product_usd = product.__class__.objects.create(
        name="Зарубежный товар",
        code_1c="1c-ord-usd",
        article="ART-USD",
        slug="foreign-product-usd",
        unit="шт",
        price=Decimal("50.00"),
        currency="USD",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("10"),
    )

    api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    api.post("/api/cart/items/", {"product_id": product_usd.id, "quantity": 1}, format="json")

    body = api.get("/api/cart/").json()
    assert body["has_mixed_currencies"] is True
    assert body["total"] == "0.00"
    assert len(body["lines"]) == 2


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
