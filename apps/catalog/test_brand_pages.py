"""Страница бренда ``/brands/<slug>`` (UX-07).

Плитки «Популярные бренды» вели в текстовый поиск: по «Metabo» приезжали чужие товары
со словом «аналог Metabo» в названии, а свои без бренда в названии терялись. Здесь
проверяется серверная половина точной брендовой выдачи.
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.brand_slugs import brand_page
from apps.catalog.models import Category, Product, ProductStatus, StockStatus

LIST_URL = "/api/catalog/products/"


def brand_url(slug):
    return f"/api/catalog/brands/{slug}/"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def catalog(db):
    root = Category.add_root(name="Электроинструмент", slug="ei")
    drills = root.add_child(name="Дрели", slug="dreli")
    discs = root.add_child(name="Круги", slug="krugi")

    def product(slug, name, category, *, brand="", price="1000", **extra):
        defaults = {
            "status": ProductStatus.PUBLISHED,
            "is_active": True,
            "stock_status": StockStatus.IN_STOCK,
        }
        defaults.update(extra)
        return Product.objects.create(
            category=category,
            name=name,
            slug=slug,
            brand=brand,
            price=Decimal(price),
            **defaults,
        )

    product("m1", "Дрель ударная SBE 650", drills, brand="Metabo", price="9000")
    # Бренда в названии нет: находится только по полю бренда.
    product("m2", "Круг отрезной 125х2,0", discs, brand="METABO", price="150")
    product(
        "m3",
        "Круг отрезной 230х2,5",
        discs,
        brand="Metabo",
        price="300",
        stock_status=StockStatus.OUT_OF_STOCK,
    )
    # Чужие товары со словом «Metabo» в названии и описании: в выдачу бренда не входят.
    product("x1", "Тарелка опорная 125 мм аналог Metabo", discs, brand="")
    product("x2", "Якорь для Metabo", drills, brand="Noname", description="Подходит к Metabo")
    # Бренд есть только у скрытого товара: известен, но на витрине пусто.
    product("h1", "Лазерный уровень", drills, brand="Hilti", status=ProductStatus.DRAFT)
    product("r1", "Стабилизатор АСН-5000", drills, brand="Ресанта")
    return {"root": root, "drills": drills, "discs": discs}


def test_выдача_бренда_точная_и_объединяет_регистр(client, catalog):
    slugs = {p["slug"] for p in client.get(LIST_URL, {"brand_slug": "metabo"}).json()["results"]}

    assert slugs == {"m1", "m2", "m3"}


def test_поиск_по_слову_даёт_другой_набор(client, catalog):
    """Контроль: текстовый поиск тащит чужие товары — поэтому плитки и переведены."""
    slugs = {p["slug"] for p in client.get(LIST_URL, {"search": "metabo"}).json()["results"]}

    assert {"x1", "x2"} <= slugs


def test_счётчик_равен_полной_выдаче(client, catalog):
    facets = client.get(brand_url("metabo")).json()
    listing = client.get(LIST_URL, {"brand_slug": "metabo", "limit": 1}).json()

    assert facets["total_products"] == listing["count"] == 3
    assert facets["brand_total_products"] == 3
    assert len(listing["results"]) == 1  # счётчик — не число товаров на странице


def test_название_бренда_берётся_из_самого_частого_написания(client, catalog):
    assert client.get(brand_url("metabo")).json()["brand"] == {"slug": "metabo", "name": "Metabo"}


def test_slug_регистронезависим_и_кириллица_транслитерируется(client, catalog):
    assert client.get(brand_url("METABO")).status_code == 200
    assert client.get(brand_url("resanta")).json()["brand"]["name"] == "Ресанта"


def test_категории_бренда_со_счётчиками(client, catalog):
    data = client.get(brand_url("metabo")).json()

    assert [(c["slug"], c["count"], c["selected"]) for c in data["categories"]] == [
        ("krugi", 2, False),
        ("dreli", 1, False),
    ]


def test_категория_сужает_выдачу_но_не_список_категорий(client, catalog):
    data = client.get(brand_url("metabo"), {"category": "krugi"}).json()
    listing = client.get(LIST_URL, {"brand_slug": "metabo", "category": "krugi"}).json()

    assert data["total_products"] == listing["count"] == 2
    assert {p["slug"] for p in listing["results"]} == {"m2", "m3"}
    # Ось категории считается без фильтра категории: из «Кругов» можно уйти в «Дрели».
    assert {c["slug"]: c["selected"] for c in data["categories"]} == {"krugi": True, "dreli": False}
    assert data["brand_total_products"] == 3


def test_родительская_категория_сужает_по_поддереву(client, catalog):
    data = client.get(brand_url("metabo"), {"category": "ei"}).json()

    assert data["total_products"] == 3


def test_наличие_и_цена_сужают_и_считаются(client, catalog):
    data = client.get(brand_url("metabo"), {"stock_status": "in_stock"}).json()

    assert data["total_products"] == 2
    assert data["price"] == {"min": 150.0, "max": 9000.0}
    assert {s["value"]: s["count"] for s in data["stock"]} == {"in_stock": 2, "out_of_stock": 1}


def test_сортировка_и_пагинация_сохраняют_бренд(client, catalog):
    params = {"brand_slug": "metabo", "sort": "price_desc", "limit": 2, "offset": 0}
    first = client.get(LIST_URL, params).json()
    second = client.get(LIST_URL, {**params, "offset": 2}).json()

    got = [p["slug"] for p in first["results"] + second["results"]]
    assert sorted(got) == ["m1", "m2", "m3"]
    assert first["count"] == second["count"] == 3


def test_неизвестный_бренд_404_и_пустой_список(client, catalog):
    assert client.get(brand_url("no-such-brand")).status_code == 404
    assert client.get(LIST_URL, {"brand_slug": "no-such-brand"}).json()["count"] == 0


def test_известный_бренд_без_видимых_товаров_отличается_от_неизвестного(client, catalog):
    data = client.get(brand_url("hilti")).json()

    assert data["brand"]["name"] == "Hilti"
    assert data["brand_total_products"] == 0
    assert data["total_products"] == 0


def test_неизвестная_категория_и_мусорный_статус_дают_400(client, catalog):
    assert client.get(brand_url("metabo"), {"category": "nope"}).status_code == 400
    assert client.get(brand_url("metabo"), {"stock_status": "nope"}).status_code == 400


def test_ссылка_стабильна_при_появлении_коллизии_slug(catalog):
    """Фасет PLP раздал бы суффиксы -2/-3; у страницы бренда slug один на все написания."""
    before = brand_page("metabo")["spellings"]
    Product.objects.create(
        category=catalog["drills"],
        name="Шуруповёрт",
        slug="m4",
        brand="MetaBo",
        price=Decimal("1"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
    )

    page = brand_page("metabo")
    assert set(before) < set(page["spellings"]) == {"METABO", "MetaBo", "Metabo"}
    assert brand_page("metabo-2") is None
