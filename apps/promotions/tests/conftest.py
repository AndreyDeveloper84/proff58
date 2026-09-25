"""Фикстуры тестов promotions: дерево категорий + товары."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.models import Category, Product, ProductStatus


@pytest.fixture
def tree(db):
    """Категория «Инструмент» → подкатегория «Перфораторы» (проверка поддерева)."""
    root = Category.add_root(name="Инструмент", slug="instrument")
    child = root.add_child(name="Перфораторы", slug="perforatory")
    return {"root": root, "child": child}


def _product(slug, category, price="1000.00"):
    return Product.objects.create(
        category=category,
        name=slug,
        slug=slug,
        unit="шт",
        price=Decimal(price),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("10"),
    )


@pytest.fixture
def drill(tree):
    """Товар в подкатегории (10 000 ₽ строка не нужна — цена 1000)."""
    return _product("drill", tree["child"])


@pytest.fixture
def saw(tree):
    """Товар в корневой категории."""
    return _product("saw", tree["root"], price="500.00")
