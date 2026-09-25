"""Фикстуры тестов заявок."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductStatus


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def product(db):
    """Опубликованный товар в наличии с ценой."""
    return Product.objects.create(
        name="Дрель",
        code_1c="1c-lead-1",
        article="ART-LEAD-1",
        slug="drel-lead-1",
        unit="шт",
        price=Decimal("1000.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("10"),
    )
