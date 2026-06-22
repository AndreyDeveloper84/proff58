"""Тесты EAV-фильтрации списка товаров через ?attr_<slug>= (фильтр сайдбара PLP).

Список товаров и счётчики фасетов фильтруются одним механизмом (apply_product_attr_filters /
build_facets) — поэтому здесь проверяем именно products-эндпоинт: раньше attr_-фасеты в него
не доходили и сайдбар «не работал» (выдача не менялась).
"""

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductStatus,
    StockStatus,
)


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tree(db):
    root = Category.add_root(name="Оснастка", slug="osnastka")
    leaf = root.add_child(name="Оснастка и расходники", slug="osnastka-i-rashodniki")
    return root, leaf


def make_attr(slug, name, atype, *, filterable=True):
    return Attribute.objects.create(
        slug=slug, name=name, attribute_type=atype, is_filterable=filterable
    )


def make_product(category, slug, attrs):
    return Product.objects.create(
        category=category,
        name=slug,
        slug=slug,
        attrs_cache=attrs,
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_status=StockStatus.IN_STOCK,
    )


def make_drills_and_crowns(leaf):
    """3 «Коронки», 2 «Буры», 1 «Сверла» — для проверки фильтра по tool_type."""
    tool_type = make_attr("tool_type", "Тип инструмента", AttributeType.SELECT)
    CategoryAttribute.objects.create(category=leaf, attribute=tool_type)
    for i in range(3):
        make_product(leaf, f"crown-{i}", {"tool_type": "Коронки"})
    for i in range(2):
        make_product(leaf, f"bur-{i}", {"tool_type": "Буры"})
    make_product(leaf, "drill-0", {"tool_type": "Сверла"})


def count(client, qs):
    return client.get(f"/api/catalog/products/?{qs}").json()["count"]


@pytest.mark.django_db
def test_attr_filter_narrows_list(client, tree):
    _, leaf = tree
    make_drills_and_crowns(leaf)
    # без фильтра — все 6
    assert count(client, "category=osnastka-i-rashodniki") == 6
    # attr_tool_type=Коронки → только 3
    assert count(client, "category=osnastka-i-rashodniki&attr_tool_type=Коронки") == 3


@pytest.mark.django_db
def test_attr_filter_or_within_attribute(client, tree):
    _, leaf = tree
    make_drills_and_crowns(leaf)
    # повторяющийся параметр = OR значений одного атрибута: Коронки(3) OR Буры(2) = 5
    qs = "category=osnastka-i-rashodniki&attr_tool_type=Коронки&attr_tool_type=Буры"
    assert count(client, qs) == 5


@pytest.mark.django_db
def test_unknown_attr_ignored(client, tree):
    _, leaf = tree
    make_drills_and_crowns(leaf)
    # неизвестный атрибут не валит запрос и не фильтрует
    assert count(client, "category=osnastka-i-rashodniki&attr_unknown=xxx") == 6


@pytest.mark.django_db
def test_empty_attr_value_ignored(client, tree):
    _, leaf = tree
    make_drills_and_crowns(leaf)
    # пустое значение игнорируется (а не «ноль товаров»)
    assert count(client, "category=osnastka-i-rashodniki&attr_tool_type=") == 6


@pytest.mark.django_db
def test_non_filterable_attr_ignored(client, tree):
    _, leaf = tree
    nf = make_attr("secret", "Служебное", AttributeType.SELECT, filterable=False)
    CategoryAttribute.objects.create(category=leaf, attribute=nf)
    make_product(leaf, "x1", {"secret": "a"})
    make_product(leaf, "x2", {"secret": "b"})
    # нефильтруемый атрибут не применяется
    assert count(client, "category=osnastka-i-rashodniki&attr_secret=a") == 2
