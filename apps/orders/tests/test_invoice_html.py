"""Тест HTML-счёта (#324)."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import CustomerType, Profile
from apps.catalog.models import Product, ProductStatus

User = get_user_model()


@pytest.mark.django_db
def test_b2b_invoice_html():
    user = User.objects.create_user(
        phone="+79007777777", password="pass", customer_type=CustomerType.B2B, full_name="Директор"
    )
    Profile.objects.create(user=user, company_name='ООО "Тест"', inn="7701234567")
    product = Product.objects.create(
        name="Дрель",
        slug="inv-drel",
        price=Decimal("5000.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_quantity=10,
        available_quantity=10,
    )

    client = APIClient()
    client.force_authenticate(user=user)
    client.post("/api/cart/items/", {"product_id": product.id, "quantity": 2}, format="json")
    create = client.post("/api/orders/", {}, format="json")
    assert create.status_code == 201
    number = create.json()["order_number"]

    resp = client.get(f"/api/orders/{number}/invoice/")
    assert resp.status_code == 200
    assert "text/html" in resp["Content-Type"]
    content = resp.content.decode()
    assert "7701234567" in content
    assert number in content


@pytest.mark.django_db
def test_b2c_invoice_rejected():
    user = User.objects.create_user(phone="+79008888888", password="pass")
    product = Product.objects.create(
        name="Пила",
        slug="inv-pila",
        price=Decimal("3000.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_quantity=5,
        available_quantity=5,
    )

    client = APIClient()
    client.force_authenticate(user=user)
    client.post("/api/cart/items/", {"product_id": product.id, "quantity": 1}, format="json")
    create = client.post("/api/orders/", {}, format="json")
    number = create.json()["order_number"]

    resp = client.get(f"/api/orders/{number}/invoice/")
    assert resp.status_code == 400
