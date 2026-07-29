"""Тесты публичного API каталога (#19)."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    ProductImage,
    ProductStatus,
)
from apps.pricing.models import PriceRecord
from apps.pricing.services import RETAIL, WHOLESALE, price_for, price_map_for_products

User = get_user_model()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tree(db):
    root = Category.add_root(name="Электроинструмент", slug="ei")
    mid = root.add_child(name="Дрели и шуруповёрты", slug="dreli-grp")
    leaf = mid.add_child(name="Дрели", slug="dreli")
    return root, mid, leaf


def make_product(category, name, slug, **kw):
    data = {
        "category": category,
        "name": name,
        "slug": slug,
        "status": ProductStatus.PUBLISHED,
        "is_active": True,
        "price": "1000",
    }
    data.update(kw)
    return Product.objects.create(**data)


@pytest.mark.django_db
def test_categories_tree_three_levels(client, tree):
    resp = client.get("/api/catalog/categories/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["slug"] == "ei"
    assert data[0]["children"][0]["slug"] == "dreli-grp"
    assert data[0]["children"][0]["children"][0]["slug"] == "dreli"


@pytest.mark.django_db
def test_categories_only_active(client, tree):
    Category.add_root(name="Скрытая", slug="hidden", is_active=False)
    slugs = [c["slug"] for c in client.get("/api/catalog/categories/").json()]
    assert "hidden" not in slugs


@pytest.mark.django_db
def test_products_only_visible(client, tree):
    _, _, leaf = tree
    make_product(leaf, "Видимый", "vis")
    make_product(leaf, "Черновик", "draft", status=ProductStatus.DRAFT)
    make_product(leaf, "Выключен", "off", is_active=False)
    results = client.get("/api/catalog/products/").json()["results"]
    assert {r["slug"] for r in results} == {"vis"}


@pytest.mark.django_db
def test_products_filter_category_includes_descendants(client, tree):
    _, _, leaf = tree
    make_product(leaf, "Дрель в листе", "drel-leaf")
    results = client.get("/api/catalog/products/?category=ei").json()["results"]
    assert "drel-leaf" in {r["slug"] for r in results}


@pytest.mark.django_db
def test_product_detail_card(client, tree):
    _, _, leaf = tree
    p = make_product(leaf, "Дрель Bosch", "bosch", brand="Bosch", description="Описание")
    a = Attribute.objects.create(
        slug="power", name="Мощность", attribute_type=AttributeType.INTEGER, unit="Вт"
    )
    ProductAttributeValue.objects.create(product=p, attribute=a, value_integer=650)
    ProductImage.objects.create(product=p, image="products/x.jpg", is_main=True)

    data = client.get("/api/catalog/products/bosch/").json()
    assert data["brand"] == "Bosch"
    assert data["description"] == "Описание"
    assert {"name": "Мощность", "slug": "power", "unit": "Вт", "value": 650} in data["attributes"]
    assert [c["slug"] for c in data["breadcrumb"]] == ["ei", "dreli-grp", "dreli"]
    assert data["main_image"] is not None


@pytest.mark.django_db
def test_product_detail_hidden_404(client, tree):
    _, _, leaf = tree
    make_product(leaf, "Черновик", "draft-x", status=ProductStatus.DRAFT)
    make_product(leaf, "Выключен", "off-x", is_active=False)
    assert client.get("/api/catalog/products/draft-x/").status_code == 404
    assert client.get("/api/catalog/products/off-x/").status_code == 404


@pytest.mark.django_db
def test_main_image_selection(client, tree):
    _, _, leaf = tree
    p = make_product(leaf, "Т", "img-test")
    ProductImage.objects.create(product=p, image="products/a.jpg", is_main=False, sort_order=1)
    ProductImage.objects.create(product=p, image="products/b.jpg", is_main=True, sort_order=2)
    data = client.get("/api/catalog/products/img-test/").json()
    assert data["main_image"].endswith("b.jpg")


@pytest.mark.django_db
def test_image_url_is_relative_regardless_of_request_host(client, tree):
    """URL картинки не зависит от того, кто спросил.

    Next.js рендерит витрину на сервере и ходит в Django по внутреннему адресу
    (Host «web:8000»). Пока URL строился через build_absolute_uri, этот хост
    уезжал в HTML — браузер такой адрес не резолвит, и фото были битыми во всём
    каталоге. Проверяем оба входа: внутренний и публичный дают одинаковый путь.
    """
    _, _, leaf = tree
    p = make_product(leaf, "Т", "img-host")
    ProductImage.objects.create(product=p, image="products/a.jpg", is_main=True)

    internal = client.get("/api/catalog/products/img-host/", HTTP_HOST="web:8000").json()
    public = client.get("/api/catalog/products/img-host/", HTTP_HOST="testserver").json()

    assert internal["main_image"] == "/media/products/a.jpg"
    assert internal["main_image"] == public["main_image"]
    assert [i["url"] for i in internal["images"]] == ["/media/products/a.jpg"]


@pytest.mark.django_db
def test_products_no_nplus1(client, tree, django_assert_max_num_queries):
    _, _, leaf = tree
    for i in range(5):
        p = make_product(leaf, f"Товар {i}", f"t-{i}", brand="B")
        ProductImage.objects.create(product=p, image=f"products/{i}.jpg", is_main=True)
    with django_assert_max_num_queries(8):
        client.get("/api/catalog/products/")


@pytest.mark.django_db
def test_products_b2b_no_nplus1(client, tree, django_assert_max_num_queries):
    """B2B-листинг не делает по запросу на опт-цену каждого товара (bulk-резолвер).

    До фазы 2 это было бы ~N запросов к PriceRecord (по одному на товар). Лимит
    фиксированный и НЕ растёт с числом товаров.
    """
    _, _, leaf = tree
    b2b = User.objects.create_user(phone="+79991110000", customer_type="b2b")
    Profile.objects.create(user=b2b, is_b2b_verified=True)
    for i in range(20):
        p = make_product(
            leaf, f"Опт {i}", f"w-{i}", code_1c=f"1c-w-{i}", currency="RUB", price="1000"
        )
        ProductImage.objects.create(product=p, image=f"products/w{i}.jpg", is_main=True)
        PriceRecord.objects.create(
            code_1c=p.code_1c,
            product=p,
            price_type=WHOLESALE,
            value=Decimal("800.00"),
            currency="RUB",
            is_current=True,
        )

    client.force_authenticate(user=b2b)
    with django_assert_max_num_queries(10):
        resp = client.get("/api/catalog/products/")

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 20
    # #430 (M-06): единый ценник — B2B видит ту же розничную цену (без опта).
    for r in results:
        assert r["price"] == "1000.00"
        assert r["price_type"] == RETAIL


@pytest.mark.django_db
def test_price_map_equivalent_to_price_for_b2b(tree):
    """price_map_for_products[p.id] поэлементно == price_for(p, b2b) для смеси товаров."""
    _, _, leaf = tree
    b2b = User.objects.create_user(phone="+79991110001", customer_type="b2b")
    Profile.objects.create(user=b2b, is_b2b_verified=True)

    # с опт-ценой
    with_wholesale = make_product(
        leaf, "С опт", "eq-w", code_1c="1c-eq-w", currency="RUB", price="1000"
    )
    PriceRecord.objects.create(
        code_1c=with_wholesale.code_1c,
        product=with_wholesale,
        price_type=WHOLESALE,
        value=Decimal("800.00"),
        currency="RUB",
        is_current=True,
    )
    # с code_1c, но без опт-цены → розница
    no_wholesale = make_product(
        leaf,
        "Без опт",
        "eq-nw",
        code_1c="1c-eq-nw",
        currency="RUB",
        price="1500",
        old_price="1700",
    )
    # без code_1c → розница
    no_code = make_product(leaf, "Без кода", "eq-nc", code_1c="", currency="RUB", price="900")

    # перечитываем из БД (как делает queryset во view): price/old_price → Decimal
    ids = [with_wholesale.id, no_wholesale.id, no_code.id]
    products = list(Product.objects.filter(id__in=ids))
    price_map = price_map_for_products(products, b2b)

    for p in products:
        expected = price_for(p, b2b)
        got = price_map[p.id]
        assert got.base == expected.base
        assert got.final == expected.final
        assert got.currency == expected.currency
        assert got.discount == expected.discount
        assert got.price_type == expected.price_type


@pytest.mark.django_db
def test_products_b2c_no_pricerecord_queries(client, tree):
    """B2C-листинг не трогает PriceRecord и выдача не изменилась."""
    _, _, leaf = tree
    for i in range(5):
        p = make_product(leaf, f"Розн {i}", f"r-{i}", price="1000", old_price="1200")
        ProductImage.objects.create(product=p, image=f"products/r{i}.jpg", is_main=True)

    with CaptureQueriesContext(connection) as ctx:
        resp = client.get("/api/catalog/products/")

    assert resp.status_code == 200
    # Ни одного запроса к таблице PriceRecord (B2C считает розницу в памяти).
    pr_table = PriceRecord._meta.db_table
    assert not any(pr_table in q["sql"] for q in ctx.captured_queries)

    for r in resp.json()["results"]:
        assert r["price"] == "1000.00"
        assert r["old_price"] == "1200.00"
        assert r["price_type"] == RETAIL


@pytest.mark.django_db
def test_public_access_no_key(client, tree):
    assert client.get("/api/catalog/products/").status_code == 200


def _flatten_slugs(tree):
    out = []
    for node in tree:
        out.append(node["slug"])
        out += _flatten_slugs(node["children"])
    return out


@pytest.mark.django_db
def test_tree_excludes_orphans_of_inactive_parent(client):
    active_root = Category.add_root(name="Активный", slug="ar")
    active_root.add_child(name="Видимый ребёнок", slug="ac-vis")
    inactive_root = Category.add_root(name="Скрытый", slug="ir", is_active=False)
    hidden_child = inactive_root.add_child(name="Активный под скрытым", slug="ac-hidden")
    hidden_child.add_child(name="Активный внук", slug="ag-hidden")

    data = client.get("/api/catalog/categories/").json()
    all_slugs = _flatten_slugs(data)
    assert "ar" in all_slugs and "ac-vis" in all_slugs
    for orphan in ("ir", "ac-hidden", "ag-hidden"):
        assert orphan not in all_slugs
    assert [n["slug"] for n in data] == ["ar"]  # активный потомок не всплыл в корни
