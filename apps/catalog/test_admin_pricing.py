"""Тесты «ценоосознанной» админки товара (#103, поверх #60)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.catalog.models import Product
from apps.pricing.models import PriceRecord

User = get_user_model()


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_superuser(phone="+79990000099", password="pw")
    c = Client()
    c.force_login(admin)
    return c


@pytest.mark.django_db
def test_product_changelist_shows_wholesale(admin_client):
    p = Product.objects.create(name="Дрель", code_1c="1c-adm", slug="adm", price=Decimal("1000.00"))
    PriceRecord.objects.create(
        code_1c="1c-adm",
        product=p,
        price_type="wholesale",
        value=Decimal("800.00"),
        currency="RUB",
        is_current=True,
    )
    resp = admin_client.get("/admin/catalog/product/")
    assert resp.status_code == 200
    assert b"800" in resp.content  # колонка «Опт»


@pytest.mark.django_db
def test_product_change_form_shows_pricing_summary(admin_client):
    p = Product.objects.create(
        name="Дрель", code_1c="1c-adm2", slug="adm2", price=Decimal("1000.00")
    )
    PriceRecord.objects.create(
        code_1c="1c-adm2",
        product=p,
        price_type="wholesale",
        value=Decimal("800.00"),
        currency="RUB",
        is_current=True,
    )
    resp = admin_client.get(f"/admin/catalog/product/{p.pk}/change/")
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "розница: 1000.00 RUB" in content
    assert "опт (B2B): 800.00 RUB" in content
