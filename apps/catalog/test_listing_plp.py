"""PLP API: specs в листинге, серверная сортировка, фасеты price/brand/stock + category-блок.

Проверяем контракт, который потребляет фронт (frontend/lib/adapters.ts): list отдаёт
`attributes`, facets-эндпоинт — price/brands/stock/category/subcategories, и работает
серверная сортировка (?sort=) ДО пагинации.
"""

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    ProductStatus,
    StockStatus,
)


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tree(db):
    root = Category.add_root(name="Электроинструмент", slug="ei")
    leaf = root.add_child(name="Перфораторы", slug="perforatory", description="SEO-текст категории")
    return root, leaf


def make_product(category, slug, *, brand="", price=None, stock=StockStatus.IN_STOCK):
    return Product.objects.create(
        category=category,
        name=slug,
        slug=slug,
        brand=brand,
        price=price,
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_status=stock,
    )


def results(client, qs):
    return client.get(f"/api/catalog/products/?{qs}").json()["results"]


def facets(client, slug, qs=""):
    return client.get(f"/api/catalog/categories/{slug}/facets/?{qs}").json()


# --- specs в list-сериализаторе ---


@pytest.mark.django_db
def test_list_returns_bounded_attributes(client, tree):
    _, leaf = tree
    power = Attribute.objects.create(
        slug="power",
        name="Мощность",
        attribute_type=AttributeType.INTEGER,
        is_filterable=True,
        unit="Вт",
    )
    secret = Attribute.objects.create(
        slug="secret", name="Служебное", attribute_type=AttributeType.INTEGER, is_filterable=False
    )
    p = make_product(leaf, "p1", price=1000)
    ProductAttributeValue.objects.create(product=p, attribute=power, value_integer=800)
    ProductAttributeValue.objects.create(product=p, attribute=secret, value_integer=42)

    attrs = results(client, "category=perforatory")[0]["attributes"]
    by_slug = {a["slug"]: a for a in attrs}
    assert by_slug["power"] == {"name": "Мощность", "slug": "power", "unit": "Вт", "value": 800}
    assert "secret" not in by_slug  # не filterable/comparable → не в карточке


@pytest.mark.django_db
def test_list_specs_no_nplus1(client, tree, django_assert_max_num_queries):
    _, leaf = tree
    power = Attribute.objects.create(
        slug="power", name="Мощность", attribute_type=AttributeType.INTEGER, is_filterable=True
    )
    for i in range(20):
        p = make_product(leaf, f"p{i}", price=100 + i)
        ProductAttributeValue.objects.create(product=p, attribute=power, value_integer=500 + i)

    # Число запросов задаётся конвейером (count/page/price/prefetch), не числом товаров.
    with django_assert_max_num_queries(10):
        client.get("/api/catalog/products/?category=perforatory")


# --- серверная сортировка ---


@pytest.mark.django_db
def test_sort_price_asc_desc_nulls_last(client, tree):
    _, leaf = tree
    make_product(leaf, "a", price=300)
    make_product(leaf, "b", price=100)
    make_product(leaf, "c", price=200)
    make_product(leaf, "noprice", price=None)

    asc = [r["slug"] for r in results(client, "category=perforatory&sort=price_asc")]
    assert asc == ["b", "c", "a", "noprice"]  # дешёвые первыми, без цены — в конец
    desc = [r["slug"] for r in results(client, "category=perforatory&sort=price_desc")]
    assert desc == ["a", "c", "b", "noprice"]  # дорогие первыми, без цены — в конец


@pytest.mark.django_db
def test_sort_new_by_created_at(client, tree):
    _, leaf = tree
    make_product(leaf, "old", price=1)
    make_product(leaf, "mid", price=1)
    make_product(leaf, "new", price=1)

    order = [r["slug"] for r in results(client, "category=perforatory&sort=new")]
    assert order == ["new", "mid", "old"]  # -created_at


@pytest.mark.django_db
def test_sort_before_pagination(client, tree):
    _, leaf = tree
    for slug, price in [("a", 5), ("b", 4), ("c", 3), ("d", 2), ("e", 1)]:
        make_product(leaf, slug, price=price)

    first_two = [
        r["slug"] for r in results(client, "category=perforatory&sort=price_asc&limit=2&offset=0")
    ]
    assert first_two == ["e", "d"]  # самые дешёвые ИЗ ВСЕЙ выборки, не дефолтной страницы


@pytest.mark.django_db
def test_invalid_sort_falls_back_to_name(client, tree):
    _, leaf = tree
    make_product(leaf, "b", price=1)
    make_product(leaf, "a", price=2)
    order = [r["slug"] for r in results(client, "category=perforatory&sort=bogus")]
    assert order == ["a", "b"]  # дефолт — по name


# --- фасеты price/brand/stock + category-блок ---


@pytest.mark.django_db
def test_price_facet_min_max_and_drilldown(client, tree):
    _, leaf = tree
    make_product(leaf, "p1", brand="Bosch", price=100)
    make_product(leaf, "p2", brand="Makita", price=500)
    make_product(leaf, "p3", brand="Bosch", price=900)
    make_product(leaf, "p4", price=None)  # без цены — не влияет на min/max

    data = facets(client, "perforatory")
    assert data["price"] == {"min": 100.0, "max": 900.0}
    # drill-down: Makita — единственная цена 500
    makita = facets(client, "perforatory", "brand=Makita")
    assert makita["price"] == {"min": 500.0, "max": 500.0}


@pytest.mark.django_db
def test_brand_facet_drilldown_keeps_others_and_marks_selected(client, tree):
    _, leaf = tree
    make_product(leaf, "p1", brand="Bosch", price=100)
    make_product(leaf, "p2", brand="Makita", price=200)
    make_product(leaf, "p3", brand="Bosch", price=300)

    data = facets(client, "perforatory", "brand=Bosch")
    brands = {b["value"]: b for b in data["brands"]}
    # бренды НЕ схлопываются при выбранном Bosch (counts по базе без brand)
    assert brands["Bosch"]["count"] == 2
    assert brands["Makita"]["count"] == 1
    assert brands["Bosch"]["selected"] is True
    assert brands["Makita"]["selected"] is False
    assert brands["Bosch"]["label"] == "Bosch"


@pytest.mark.django_db
def test_stock_facet_counts_and_labels(client, tree):
    _, leaf = tree
    make_product(leaf, "a", price=1, stock=StockStatus.IN_STOCK)
    make_product(leaf, "b", price=1, stock=StockStatus.IN_STOCK)
    make_product(leaf, "c", price=1, stock=StockStatus.ON_ORDER)

    data = facets(client, "perforatory")
    stock = {s["value"]: s for s in data["stock"]}
    assert stock["in_stock"]["count"] == 2
    assert stock["in_stock"]["label"] == "В наличии"
    assert stock["on_order"]["count"] == 1
    assert stock["on_order"]["label"] == "Под заказ"


@pytest.mark.django_db
def test_category_block_and_subcategories(client, tree):
    root, leaf = tree
    leaf.add_child(name="SDS-Plus", slug="sds-plus")
    leaf.add_child(name="Скрытая", slug="hidden", is_active=False)
    make_product(leaf, "p1", price=1)

    data = facets(client, "perforatory")
    assert data["category"]["name"] == "Перфораторы"
    assert data["category"]["description"] == "SEO-текст категории"
    crumbs = [c["slug"] for c in data["category"]["breadcrumb"]]
    assert crumbs == ["ei", "perforatory"]  # предки + сама
    subs = [s["slug"] for s in data["subcategories"]]
    assert subs == ["sds-plus"]  # неактивная подкатегория не попадает
