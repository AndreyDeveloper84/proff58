"""Тесты EAV-фильтрации списка товаров через ?attr_<slug>= (фильтр сайдбара PLP).

Список товаров и счётчики фасетов фильтруются одним механизмом (apply_product_attr_filters /
build_facets) — поэтому здесь проверяем именно products-эндпоинт: раньше attr_-фасеты в него
не доходили и сайдбар «не работал» (выдача не менялась).
"""

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import (
    Attribute,
    AttributeOption,
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
def test_attr_filter_by_slug_and_legacy_raw(client, tree):
    """Список товаров фильтруется и по slug опции (canonical URL), и по сырому значению (legacy)."""
    _, leaf = tree
    make_drills_and_crowns(leaf)
    tt = Attribute.objects.get(slug="tool_type")
    AttributeOption.objects.create(attribute=tt, value="Коронки", slug="coronki", sort_order=0)
    # canonical slug-URL
    assert count(client, "category=osnastka-i-rashodniki&attr_tool_type=coronki") == 3
    # legacy сырое значение
    assert count(client, "category=osnastka-i-rashodniki&attr_tool_type=Коронки") == 3


@pytest.mark.django_db
def test_attr_filter_unknown_slug_zero(client, tree):
    """Неизвестный slug-токен → 0 товаров, без падения листинга."""
    _, leaf = tree
    make_drills_and_crowns(leaf)
    tt = Attribute.objects.get(slug="tool_type")
    AttributeOption.objects.create(attribute=tt, value="Коронки", slug="coronki", sort_order=0)
    assert count(client, "category=osnastka-i-rashodniki&attr_tool_type=unknown-token") == 0


@pytest.mark.django_db
def test_non_filterable_attr_ignored(client, tree):
    _, leaf = tree
    nf = make_attr("secret", "Служебное", AttributeType.SELECT, filterable=False)
    CategoryAttribute.objects.create(category=leaf, attribute=nf)
    make_product(leaf, "x1", {"secret": "a"})
    make_product(leaf, "x2", {"secret": "b"})
    # нефильтруемый атрибут не применяется
    assert count(client, "category=osnastka-i-rashodniki&attr_secret=a") == 2


# --- Числовые диапазоны (attr_<slug>_min / _max) ---------------------------------


def make_diameter_products(leaf):
    """3 товара с diameter (10.5/15/25) + 2 БЕЗ diameter — для проверки range-фильтра."""
    make_attr("diameter", "Диаметр", AttributeType.DECIMAL)
    make_product(leaf, "d-10", {"diameter": 10.5})
    make_product(leaf, "d-15", {"diameter": 15})
    make_product(leaf, "d-25", {"diameter": 25})
    make_product(leaf, "no-d-1", {"tool_type": "Буры"})  # есть другой атрибут, diameter нет
    make_product(leaf, "no-d-2", {})  # вообще без атрибутов


@pytest.mark.django_db
def test_attr_range_filters_and_excludes_attrless(client, tree):
    """Ключевой кейс бага B: диапазон по diameter сужает выдачу И исключает товары без diameter."""
    _, leaf = tree
    make_diameter_products(leaf)
    assert count(client, "category=osnastka-i-rashodniki") == 5  # без фильтра — все
    # [10,20]: подходят 10.5 и 15; 25 — вне диапазона; оба «no-d» исключены (нет атрибута)
    qs = "category=osnastka-i-rashodniki&attr_diameter_min=10&attr_diameter_max=20"
    assert count(client, qs) == 2


@pytest.mark.django_db
def test_attr_range_min_only(client, tree):
    _, leaf = tree
    make_diameter_products(leaf)
    assert count(client, "category=osnastka-i-rashodniki&attr_diameter_min=15") == 2  # 15, 25


@pytest.mark.django_db
def test_attr_range_max_only(client, tree):
    _, leaf = tree
    make_diameter_products(leaf)
    assert count(client, "category=osnastka-i-rashodniki&attr_diameter_max=15") == 2  # 10.5, 15


@pytest.mark.django_db
def test_attr_range_garbage_ignored(client, tree):
    _, leaf = tree
    make_diameter_products(leaf)
    # мусор в границе → фильтр не применяется, листинг не падает
    assert count(client, "category=osnastka-i-rashodniki&attr_diameter_min=abc") == 5


@pytest.mark.django_db
def test_attr_range_with_checkbox_and(client, tree):
    """Диапазон + чекбокс одновременно: AND между разными атрибутами."""
    _, leaf = tree
    make_diameter_products(leaf)
    make_attr("tool_type", "Тип инструмента", AttributeType.SELECT)
    make_product(leaf, "d-bur", {"diameter": 12, "tool_type": "Буры"})
    qs = (
        "category=osnastka-i-rashodniki"
        "&attr_diameter_min=10&attr_diameter_max=20&attr_tool_type=Буры"
    )
    # diameter∈[10,20] И tool_type=Буры → только d-bur (no-d-1 без diameter исключён)
    assert count(client, qs) == 1
