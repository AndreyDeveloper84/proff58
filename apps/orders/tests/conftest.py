"""Общие фикстуры тестов заказов и корзины."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.catalog.models import Product, ProductStatus
from apps.orders.models import Cart
from apps.orders.services import add_to_cart
from apps.pricing.models import PriceRecord

User = get_user_model()


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def product(db):
    """Опубликованный товар в наличии с розничной ценой."""
    return Product.objects.create(
        name="Дрель",
        code_1c="1c-ord-1",
        article="ART-1",
        slug="drel-ord-1",
        unit="шт",
        price=Decimal("1000.00"),
        old_price=Decimal("1200.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("10"),
    )


@pytest.fixture
def product2(db):
    return Product.objects.create(
        name="Шуруповёрт",
        code_1c="1c-ord-2",
        article="ART-2",
        slug="shurupovert-ord-2",
        unit="шт",
        price=Decimal("500.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("5"),
    )


@pytest.fixture
def b2c_user(db):
    return User.objects.create_user(
        phone="+79990000010", customer_type="b2c", full_name="Иван Иванов", email="i@example.com"
    )


@pytest.fixture
def b2b_user(db):
    user = User.objects.create_user(
        phone="+79990000011", customer_type="b2b", full_name="ООО Контакт"
    )
    Profile.objects.create(
        user=user,
        company_name="ООО Профи",
        inn="7700000000",
        kpp="770001001",
        legal_address="г. Пенза, ул. Ленина, 1",
        is_b2b_verified=True,
    )
    return user


@pytest.fixture
def cart(db):
    """Активная гостевая корзина с одной строкой товара (qty=2)."""
    cart = Cart.objects.create(session_key="sess-test-1")
    return cart


@pytest.fixture
def cart_with_item(cart, product):
    add_to_cart(cart, product, 2)
    return cart


def make_wholesale(product, value):
    return PriceRecord.objects.create(
        code_1c=product.code_1c,
        product=product,
        price_type="wholesale",
        value=Decimal(value),
        currency="RUB",
        is_current=True,
    )
