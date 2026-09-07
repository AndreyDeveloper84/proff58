"""Базовые фасеты поисковой выдачи (DRF-1166).

Страница поиска до этого была витриной без ручек: ни фильтров, ни сортировки, ни
пагинации — и «Найдено 24 товара» при 276 найденных. Здесь проверяется серверная
половина: три оси со счётчиками, которые считаются по ТОЙ ЖЕ выборке, что и список.
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductStatus, StockStatus

FACETS_URL = "/api/catalog/search/facets/"
LIST_URL = "/api/catalog/products/"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def catalog(db):
    root = Category.add_root(name="Электроинструмент", slug="ei")

    def product(slug, name, *, brand="", price="1000", stock=StockStatus.IN_STOCK):
        return Product.objects.create(
            category=root,
            name=name,
            slug=slug,
            brand=brand,
            price=Decimal(price),
            status=ProductStatus.PUBLISHED,
            is_active=True,
            stock_status=stock,
        )

    product("d1", "Дрель ударная", brand="Bosch", price="5000")
    product("d2", "Дрель аккумуляторная", brand="Makita", price="12000")
    # Регистр бренда намеренно другой: фильтр списка объединяет их через iexact,
    # фасет обязан вести себя так же (иначе счётчик разойдётся с выдачей).
    product("d3", "Дрель-шуруповёрт", brand="BOSCH", price="8000", stock=StockStatus.OUT_OF_STOCK)
    product("x1", "Перфоратор", brand="Bosch", price="20000")
    return root


def test_фасеты_считаются_по_поисковой_выдаче(client, catalog):
    facets = client.get(FACETS_URL, {"search": "дрель"}).json()
    listing = client.get(LIST_URL, {"search": "дрель"}).json()

    assert facets["total_products"] == listing["count"] == 3


def test_бренды_объединяются_по_регистру(client, catalog):
    data = client.get(FACETS_URL, {"search": "дрель"}).json()

    counts = {b["label"].lower(): b["count"] for b in data["brands"]}
    assert counts == {"bosch": 2, "makita": 1}


def test_цена_показывает_границы_выдачи(client, catalog):
    data = client.get(FACETS_URL, {"search": "дрель"}).json()

    assert data["price"] == {"min": 5000.0, "max": 12000.0}


def test_наличие_разложено_по_статусам(client, catalog):
    data = client.get(FACETS_URL, {"search": "дрель"}).json()

    counts = {s["value"]: s["count"] for s in data["stock"]}
    assert counts == {StockStatus.IN_STOCK: 2, StockStatus.OUT_OF_STOCK: 1}


def test_выбранный_бренд_не_схлопывает_список_брендов(client, catalog):
    """Drill-down: своя ось считается без себя, иначе выбор прячет альтернативы."""
    data = client.get(FACETS_URL, {"search": "дрель", "brand": "makita"}).json()

    labels = {b["label"].lower() for b in data["brands"]}
    assert labels == {"bosch", "makita"}
    assert [b["selected"] for b in data["brands"] if b["label"].lower() == "makita"] == [True]


def test_выбранный_бренд_сужает_остальные_оси(client, catalog):
    data = client.get(FACETS_URL, {"search": "дрель", "brand": "makita"}).json()

    assert data["total_products"] == 1
    assert data["price"] == {"min": 12000.0, "max": 12000.0}


def test_фасеты_и_список_согласованы_под_фильтром(client, catalog):
    params = {"search": "дрель", "brand": "bosch"}
    facets = client.get(FACETS_URL, params).json()
    listing = client.get(LIST_URL, params).json()

    assert facets["total_products"] == listing["count"] == 2


def test_короткий_запрос_отдаёт_пустые_фасеты(client, catalog):
    """Матчинг требует минимум двух символов — фасеты не должны показывать весь каталог."""
    data = client.get(FACETS_URL, {"search": "д"}).json()

    assert data["total_products"] == 0
    assert data["brands"] == []
    assert data["price"] == {"min": None, "max": None}


def test_неизвестный_stock_status_отклоняется(client, catalog):
    resp = client.get(FACETS_URL, {"search": "дрель", "stock_status": "нет-такого"})

    assert resp.status_code == 400


def test_мусор_в_цене_не_роняет_фасеты(client, catalog):
    resp = client.get(FACETS_URL, {"search": "дрель", "price_min": "дёшево"})

    assert resp.status_code == 200
    assert resp.json()["total_products"] == 3


# --- сортировка выдачи поиска ------------------------------------------------


def test_без_sort_поиск_ранжирует_по_релевантности(client, catalog):
    """Точное совпадение в названии должно опережать соседей по подстроке."""
    data = client.get(LIST_URL, {"search": "перфоратор"}).json()

    assert data["results"][0]["slug"] == "x1"


def test_явный_sort_уважается_при_поиске(client, catalog):
    """DRF-1166: раньше ?sort при поиске молча игнорировался — тулбар не работал бы."""
    data = client.get(LIST_URL, {"search": "дрель", "sort": "price_asc"}).json()

    prices = [p["slug"] for p in data["results"]]
    # d3 нет в наличии — сортировка идёт внутри доступных (availability_rank первым ключом).
    assert prices[:2] == ["d1", "d2"]
