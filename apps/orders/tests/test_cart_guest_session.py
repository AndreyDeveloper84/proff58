"""Чтение корзины не заводит гостю сессию.

Почему это важно: CartProvider фронта зовёт GET /api/cart/ на каждой странице.
Пока чтение создавало корзину, Django выдавал cookie `sessionid` любому
посетителю — и серверная защита кабинета принимала гостя за вошедшего, показывая
ему разметку личного кабинета до того, как браузер уведёт его на форму входа.
"""

from __future__ import annotations

import pytest

from apps.orders.models import Cart


@pytest.mark.django_db
def test_cart_get_does_not_start_session_for_guest(api):
    resp = api.get("/api/cart/")

    assert resp.status_code == 200
    assert "sessionid" not in resp.cookies
    assert not Cart.objects.exists()


@pytest.mark.django_db
def test_cart_get_returns_neutral_empty_cart(api):
    body = api.get("/api/cart/").json()

    assert body["lines"] == []
    assert body["total"] == "0.00"
    assert body["grand_total"] == "0.00"
    assert body["items_discount_total"] == "0.00"
    assert body["currency"] == "RUB"
    assert body["has_mixed_currencies"] is False
    assert body["promo_code"] == ""
    assert body["applied_promotions"] == []
    assert body["promo_code_error"] is None


@pytest.mark.django_db
def test_cart_add_still_starts_session(api, product):
    """Сессия нужна там, где есть что хранить, — при добавлении товара."""
    resp = api.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")

    assert resp.status_code == 200
    assert Cart.objects.count() == 1
    assert Cart.objects.get().session_key

    # И следующее чтение видит ту же корзину — сессия гостя работает как раньше.
    body = api.get("/api/cart/").json()
    assert len(body["lines"]) == 1
