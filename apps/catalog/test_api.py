"""Тесты публичного API каталога (#19)."""

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    ProductImage,
    ProductStatus,
)


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
def test_products_no_nplus1(client, tree, django_assert_max_num_queries):
    _, _, leaf = tree
    for i in range(5):
        p = make_product(leaf, f"Товар {i}", f"t-{i}", brand="B")
        ProductImage.objects.create(product=p, image=f"products/{i}.jpg", is_main=True)
    with django_assert_max_num_queries(8):
        client.get("/api/catalog/products/")


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
