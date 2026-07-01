"""Тесты единого контракта ценообразования price_for (#60)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductStatus
from apps.pricing.models import PriceRecord
from apps.pricing.services import RETAIL, WHOLESALE, price_for, price_for_id

User = get_user_model()


@pytest.fixture
def product(db):
    return Product.objects.create(
        name="Дрель",
        code_1c="1c-pr-1",
        slug="pr-1",
        price=Decimal("1000.00"),
        old_price=Decimal("1200.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
    )


@pytest.fixture
def b2b_user(db):
    from apps.accounts.models import Profile

    user = User.objects.create_user(phone="+79990000002", customer_type="b2b")
    Profile.objects.create(user=user, is_b2b_verified=True)
    return user


@pytest.fixture
def b2c_user(db):
    return User.objects.create_user(phone="+79990000003", customer_type="b2c")


def _wholesale(product, value):
    return PriceRecord.objects.create(
        code_1c=product.code_1c,
        product=product,
        price_type=WHOLESALE,
        value=Decimal(value),
        currency="RUB",
        is_current=True,
    )


@pytest.mark.django_db
def test_retail_for_anonymous(product):
    r = price_for(product)
    assert r.final == Decimal("1000.00")
    assert r.price_type == RETAIL
    assert r.discount == Decimal("200.00")  # old_price 1200 − 1000
    assert r.currency == "RUB"
    assert r.has_price is True


@pytest.mark.django_db
def test_retail_for_b2c_user(product, b2c_user):
    assert price_for(product, b2c_user).price_type == RETAIL


@pytest.mark.django_db
def test_wholesale_for_b2b_when_record_exists(product, b2b_user):
    _wholesale(product, "800.00")
    r = price_for(product, b2b_user)
    assert r.final == Decimal("800.00")
    assert r.price_type == WHOLESALE
    assert r.discount is None  # опт-скидку от розничного old_price не считаем


@pytest.mark.django_db
def test_b2b_without_wholesale_falls_back_to_retail(product, b2b_user):
    r = price_for(product, b2b_user)
    assert r.final == Decimal("1000.00")
    assert r.price_type == RETAIL


@override_settings(FEATURES={"b2b": False})
@pytest.mark.django_db
def test_b2b_flag_off_returns_retail(product, b2b_user):
    _wholesale(product, "800.00")
    r = price_for(product, b2b_user)
    assert r.price_type == RETAIL  # флаг выключен → опт не отдаём
    assert r.final == Decimal("1000.00")


@pytest.mark.django_db
def test_no_price_returns_final_none(b2c_user):
    p = Product.objects.create(name="Без цены", code_1c="1c-np", slug="np", price=None)
    r = price_for(p, b2c_user)
    assert r.final is None and r.base is None
    assert r.has_price is False


@pytest.mark.django_db
def test_retail_no_discount_when_old_not_greater(db):
    p = Product.objects.create(
        name="Т", slug="t-nd", price=Decimal("500.00"), old_price=Decimal("500.00")
    )
    assert price_for(p).discount == Decimal("0")


@pytest.mark.django_db
def test_qty_accepted(product):
    assert price_for(product, qty=5).final == Decimal("1000.00")


@pytest.mark.django_db
def test_price_for_id_matches_instance(product, b2b_user):
    _wholesale(product, "800.00")
    assert price_for_id(product.pk, b2b_user).final == price_for(product, b2b_user).final


@override_settings(ONEC_API_KEY="t-key")
@pytest.mark.django_db
def test_catalog_api_returns_wholesale_for_b2b(product, b2b_user):
    _wholesale(product, "800.00")
    client = APIClient()
    client.force_authenticate(user=b2b_user)
    resp = client.get(f"/api/catalog/products/{product.slug}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["price"] == "800.00"
    assert body["price_type"] == WHOLESALE


@pytest.mark.django_db
def test_catalog_api_returns_retail_for_anonymous(product):
    resp = APIClient().get(f"/api/catalog/products/{product.slug}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["price"] == "1000.00"
    assert body["old_price"] == "1200.00"
    assert body["price_type"] == RETAIL
