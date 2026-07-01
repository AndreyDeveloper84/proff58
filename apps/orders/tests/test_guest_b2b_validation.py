"""Тесты серверной валидации гостя и B2B (#321, #323)."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import CustomerType, Profile
from apps.catalog.models import Product, ProductStatus
from apps.orders.models import Cart, CartItem

User = get_user_model()


@pytest.fixture
def product(db):
    return Product.objects.create(
        name="Дрель",
        slug="drel-val",
        price=Decimal("3000.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_quantity=10,
        available_quantity=10,
    )


@pytest.fixture
def guest_client():
    return APIClient()


@pytest.fixture
def guest_cart(product):
    cart = Cart.objects.create()
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    return cart


@pytest.fixture
def b2b_user(db):
    user = User.objects.create_user(
        phone="+79001111111",
        password="pass",
        customer_type=CustomerType.B2B,
    )
    Profile.objects.create(
        user=user,
        company_name='ООО "Тест"',
        inn="7701234567",
    )
    return user


# ═══════════ #321 — Гость без контакта ═══════════


@pytest.mark.django_db
def test_guest_without_name_rejected(guest_client, product):
    guest_client.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = guest_client.post(
        "/api/orders/",
        {"customer_phone": "+79001234567"},
        format="json",
    )
    assert resp.status_code == 400
    assert "customer_name" in str(resp.json())


@pytest.mark.django_db
def test_guest_without_phone_rejected(guest_client, product):
    guest_client.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = guest_client.post(
        "/api/orders/",
        {"customer_name": "Иван"},
        format="json",
    )
    assert resp.status_code == 400
    assert "customer_phone" in str(resp.json())


@pytest.mark.django_db
def test_guest_happy_path(guest_client, product):
    guest_client.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = guest_client.post(
        "/api/orders/",
        {
            "customer_name": "Иван Иванов",
            "customer_phone": "+79001234567",
        },
        format="json",
    )
    assert resp.status_code in (200, 201), resp.json()


# ═══════════ #323 — B2B без реквизитов ═══════════
# Гость не может быть B2B (#282): customer_type из тела игнорируется.


@pytest.mark.django_db
def test_b2b_without_inn_rejected(guest_client, product):
    """Гость с customer_type=b2b игнорируется → заказ создаётся как b2c (#282)."""
    guest_client.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = guest_client.post(
        "/api/orders/",
        {
            "customer_name": "Директор",
            "customer_phone": "+79002222222",
            "customer_type": "b2b",
            "company_name": "",
            "inn": "",
        },
        format="json",
    )
    # Гость → b2c, заказ принят
    assert resp.status_code in (200, 201)
    assert resp.json()["customer_type"] == "b2c"


@pytest.mark.django_db
def test_b2b_card_payment_rejected(guest_client, product):
    """Гость с customer_type=b2b и payment_method=card → b2c заказ с card (#282)."""
    guest_client.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = guest_client.post(
        "/api/orders/",
        {
            "customer_name": "Директор",
            "customer_phone": "+79003333333",
            "customer_type": "b2b",
            "company_name": 'ООО "Стройка"',
            "inn": "7701234567",
            "payment_method": "card",
        },
        format="json",
    )
    # Гость → b2c, оплата картой для b2c допустима
    assert resp.status_code in (200, 201)
    assert resp.json()["customer_type"] == "b2c"


@pytest.mark.django_db
def test_b2c_invoice_rejected(guest_client, product):
    guest_client.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    resp = guest_client.post(
        "/api/orders/",
        {
            "customer_name": "Покупатель",
            "customer_phone": "+79004444444",
            "payment_method": "invoice",
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "payment_method" in str(resp.json())
