"""TypePanel — навигационная панель типов инструмента (A1, #223).

`tool_type` — это НАВИГАЦИЯ (панель над выдачей), а не обычный фасет сайдбара.
Контракт (docs/plans/plp-filter-architecture.md §10.1, §13, §22.1–22.2, §26):

* `tool_type` приходит отдельной панелью с ``is_nav=True`` (прочие фасеты — False);
* `?tool_type=<slug>` сужает СПИСОК и ФАСЕТЫ одинаково (relational-механизм, как у
  `ProductFilter.filter_tool_type`, а не attrs_cache-containment);
* own-axis exclude: при выбранном типе панель показывает ВСЕ типы со счётчиками
  (свою ось не фильтрует), но учитывает brand/stock/price/attr;
* counts панели — один GROUP BY-запрос (без N+1).
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
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
    leaf = root.add_child(name="Инструмент", slug="inst")
    return root, leaf


def _make_attr(slug, name, atype, *, filterable=True, unit=""):
    return Attribute.objects.create(
        slug=slug, name=name, attribute_type=atype, is_filterable=filterable, unit=unit
    )


def _link(category, attribute, *, is_filter=True, is_seo_facet=False, sort_order=0):
    return CategoryAttribute.objects.create(
        category=category,
        attribute=attribute,
        is_filter=is_filter,
        is_seo_facet=is_seo_facet,
        sort_order=sort_order,
    )


def _product(
    category, slug, *, tool_type_option, attrs, brand="", stock=StockStatus.IN_STOCK, price=None
):
    """Товар с relational tool_type (value_option) и attrs_cache для прочих характеристик."""
    p = Product.objects.create(
        category=category,
        name=slug,
        slug=slug,
        attrs_cache={**attrs, "tool_type": tool_type_option.value},
        brand=brand,
        price=price,
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_status=stock,
    )
    ProductAttributeValue.objects.create(
        product=p, attribute=tool_type_option.attribute, value_option=tool_type_option
    )
    return p


@pytest.fixture
def shop(tree):
    """5 товаров, 3 типа: perforatory×2, ushm×2, dreli×1; бренды/наличие/мощность вразброс."""
    _, leaf = tree
    tool_type = _make_attr("tool_type", "Тип инструмента", AttributeType.SELECT)
    power = _make_attr("power", "Мощность", AttributeType.INTEGER, unit="Вт")
    chuck = _make_attr("chuck", "Патрон", AttributeType.SELECT)
    _link(leaf, tool_type, is_seo_facet=True, sort_order=0)
    _link(leaf, power, sort_order=1)
    _link(leaf, chuck, sort_order=2)

    perf = AttributeOption.objects.create(
        attribute=tool_type, value="Перфораторы", slug="perforatory", sort_order=0
    )
    ushm = AttributeOption.objects.create(
        attribute=tool_type, value="УШМ", slug="ushm", sort_order=1
    )
    dreli = AttributeOption.objects.create(
        attribute=tool_type, value="Дрели", slug="dreli", sort_order=2
    )

    _product(leaf, "p1", tool_type_option=perf, attrs={"power": 800}, brand="Bosch", price=10000)
    _product(leaf, "p2", tool_type_option=perf, attrs={"power": 500}, brand="Makita", price=5000)
    _product(leaf, "p3", tool_type_option=ushm, attrs={"power": 1000}, brand="Bosch", price=8000)
    _product(
        leaf,
        "p4",
        tool_type_option=ushm,
        attrs={"power": 1200},
        brand="Makita",
        stock=StockStatus.OUT_OF_STOCK,
        price=12000,
    )
    _product(leaf, "p5", tool_type_option=dreli, attrs={"power": 600}, brand="Bosch", price=6000)
    return {"leaf": leaf, "perf": perf, "ushm": ushm, "dreli": dreli}


def _facets(client, query=""):
    return client.get(f"/api/catalog/categories/inst/facets/{query}").json()


def _get_facet(data, slug):
    return next((f for f in data["facets"] if f["slug"] == slug), None)


def _panel_counts(data):
    panel = _get_facet(data, "tool_type")
    return {v["slug"]: v["count"] for v in panel["values"]}


def _list_count(client, query):
    return client.get(f"/api/catalog/products/{query}").json()["count"]


# --- is_nav placement ---------------------------------------------------------


@pytest.mark.django_db
def test_tool_type_is_nav_true_others_false(client, shop):
    data = _facets(client)
    panel = _get_facet(data, "tool_type")
    assert panel is not None, "панель tool_type должна присутствовать в facets"
    assert panel["is_nav"] is True
    # прочие фасеты — обычные, is_nav=False
    for slug in ("power", "chuck"):
        f = _get_facet(data, slug)
        if f is not None:
            assert f["is_nav"] is False


@pytest.mark.django_db
def test_tool_type_not_emitted_as_attrs_cache_facet(client, shop):
    # tool_type есть ровно один раз — как nav-панель, а не как обычный select-фасет.
    data = _facets(client)
    tool_type_facets = [f for f in data["facets"] if f["slug"] == "tool_type"]
    assert len(tool_type_facets) == 1
    assert tool_type_facets[0]["is_nav"] is True


@pytest.mark.django_db
def test_panel_values_slug_and_order(client, shop):
    data = _facets(client)
    panel = _get_facet(data, "tool_type")
    # порядок — по value_option.sort_order: perforatory, ushm, dreli
    assert [v["slug"] for v in panel["values"]] == ["perforatory", "ushm", "dreli"]
    assert _panel_counts(data) == {"perforatory": 2, "ushm": 2, "dreli": 1}
    # каждое значение несёт value (label) и slug
    first = panel["values"][0]
    assert first["value"] == "Перфораторы"
    assert first["slug"] == "perforatory"
    assert first["selected"] is False


# --- drill-down: list и facets сужаются одинаково ------------------------------


@pytest.mark.django_db
def test_tool_type_narrows_list_and_facets_equally(client, shop):
    q = "?category=inst&tool_type=perforatory"
    list_count = _list_count(client, q)
    facets = _facets(client, "?tool_type=perforatory")
    assert list_count == 2
    assert facets["total_products"] == 2
    assert facets["total_products"] == list_count


@pytest.mark.django_db
def test_applied_filters_carries_tool_type(client, shop):
    assert (
        _facets(client, "?tool_type=perforatory")["applied_filters"]["tool_type"] == "perforatory"
    )
    assert _facets(client)["applied_filters"]["tool_type"] is None


# --- own-axis exclude ---------------------------------------------------------


@pytest.mark.django_db
def test_own_axis_exclude_keeps_all_types_with_selected(client, shop):
    data = _facets(client, "?tool_type=perforatory")
    # панель по-прежнему показывает ВСЕ типы со счётчиками (своя ось не фильтруется)
    assert _panel_counts(data) == {"perforatory": 2, "ushm": 2, "dreli": 1}
    panel = _get_facet(data, "tool_type")
    selected = {v["slug"]: v["selected"] for v in panel["values"]}
    assert selected == {"perforatory": True, "ushm": False, "dreli": False}


@pytest.mark.django_db
def test_selected_type_narrows_other_facets(client, shop):
    # при выбранном типе сами фасеты (power) считаются только по этому типу
    data = _facets(client, "?tool_type=perforatory")
    power = _get_facet(data, "power")
    assert {v["value"]: v["count"] for v in power["values"]} == {800: 1, 500: 1}


# --- counts панели учитывают brand/stock/price --------------------------------


@pytest.mark.django_db
def test_panel_counts_respect_brand(client, shop):
    data = _facets(client, "?brand=Bosch")
    # Bosch: p1 perforatory, p3 ushm, p5 dreli → по 1
    assert _panel_counts(data) == {"perforatory": 1, "ushm": 1, "dreli": 1}


@pytest.mark.django_db
def test_panel_counts_respect_stock(client, shop):
    data = _facets(client, "?stock_status=in_stock")
    # p4 (ushm) — out_of_stock → ushm падает до 1
    assert _panel_counts(data) == {"perforatory": 2, "ushm": 1, "dreli": 1}


@pytest.mark.django_db
def test_panel_counts_respect_price(client, shop):
    # реальная цена: price>=8000 → p1(10000 perf), p3(8000 ushm), p4(12000 ushm) → perf1, ushm2
    data = _facets(client, "?price_min=8000")
    assert _panel_counts(data) == {"perforatory": 1, "ushm": 2}
    # верхняя граница: price<=6000 → p2(5000 perf), p5(6000 dreli)
    data = _facets(client, "?price_max=6000")
    assert _panel_counts(data) == {"perforatory": 1, "dreli": 1}


@pytest.mark.django_db
def test_panel_counts_respect_attr_filter(client, shop):
    # числовой attr-фильтр power>=700: p1(800 perf), p3(1000 ushm), p4(1200 ushm) → perf1, ushm2
    data = _facets(client, "?attr_power_min=700")
    assert _panel_counts(data) == {"perforatory": 1, "ushm": 2}


# --- регрессия: старый pipeline не сломан -------------------------------------


@pytest.mark.django_db
def test_regression_brand_stock_facets_still_work(client, shop):
    data = _facets(client)
    brands = {b["value"]: b["count"] for b in data["brands"]}
    assert brands == {"bosch": 3, "makita": 2}
    stock = {s["value"]: s["count"] for s in data["stock"]}
    assert stock[StockStatus.IN_STOCK] == 4
    assert stock[StockStatus.OUT_OF_STOCK] == 1


@pytest.mark.django_db
def test_regression_numeric_range_excludes_missing(client, shop):
    # числовой диапазон #219: power>=1000 → только p3,p4 (обе ushm)
    list_count = _list_count(client, "?category=inst&attr_power_min=1000")
    data = _facets(client, "?attr_power_min=1000")
    assert data["total_products"] == 2
    assert list_count == 2
    assert _panel_counts(data) == {"ushm": 2}


@pytest.mark.django_db
def test_regression_attr_checkbox_filter_still_works(client, shop):
    # обычный attr_* чекбокс по числовому значению — list и facets совпадают
    list_count = _list_count(client, "?category=inst&attr_power=800")
    data = _facets(client, "?attr_power=800")
    assert data["total_products"] == 1
    assert list_count == 1


# --- performance: нет N+1 (counts через group-by, не per-product) -------------


@pytest.mark.django_db
def test_no_n_plus_1_query_count_independent_of_product_count(
    client, shop, django_assert_max_num_queries
):
    """Число SQL-запросов фасетного эндпоинта НЕ растёт с числом товаров.

    TypePanel считается одним GROUP BY value_option; attr/brand/stock/price — по
    одному индексируемому запросу на фасет. Удваиваем товары — число запросов
    остаётся прежним (иначе был бы per-product N+1).
    """
    leaf = shop["leaf"]
    opts = [shop["perf"], shop["ushm"], shop["dreli"]]

    def hit():
        # факт ~13 запросов; порог 20 даёт небольшой запас и ловит рост константной стоимости.
        with django_assert_max_num_queries(20) as ctx:
            r = client.get("/api/catalog/categories/inst/facets/?tool_type=perforatory")
            assert r.status_code == 200
        return len(ctx.captured_queries)

    before = hit()
    # кратно увеличиваем товары — счётчики считаются в SQL, число запросов не должно расти
    for i in range(40):
        _product(
            leaf, f"extra{i}", tool_type_option=opts[i % 3], attrs={"power": 700 + i}, brand="Bosch"
        )
    after = hit()
    assert after == before, f"N+1: запросов было {before}, стало {after} (растёт с товарами)"


# --- инфляция счётчиков: товар с несколькими EAV-строками ---------------------


@pytest.mark.django_db
def test_multiple_eav_rows_do_not_inflate_counts(client, shop):
    """Лишние EAV-строки товара (другой атрибут) не должны удваивать total/brand/stock.

    Корректность держится на ``unique_together(product, attribute)`` + сужении JOIN до
    одной tool_type-строки. Фиксируем это контрактом: добавляем p1 вторую relational-строку
    (power как value_integer) — счётчики обязаны остаться прежними.
    """
    power = Attribute.objects.get(slug="power")
    p1 = Product.objects.get(slug="p1")
    ProductAttributeValue.objects.create(product=p1, attribute=power, value_integer=800)

    data = _facets(client)
    assert data["total_products"] == 5  # не 6 — p1 не задвоился
    assert {b["value"]: b["count"] for b in data["brands"]} == {"bosch": 3, "makita": 2}
    assert _panel_counts(data) == {"perforatory": 2, "ushm": 2, "dreli": 1}
    # с выбранным типом тоже без инфляции
    sel = _facets(client, "?tool_type=perforatory")
    assert sel["total_products"] == 2
    assert _list_count(client, "?category=inst&tool_type=perforatory") == 2


# --- отказоустойчивость: пустой/несуществующий tool_type ----------------------


@pytest.mark.django_db
def test_empty_tool_type_is_no_filter(client, shop):
    # ?tool_type= (пусто) эквивалентно отсутствию фильтра
    data = _facets(client, "?tool_type=")
    assert data["total_products"] == 5
    assert data["applied_filters"]["tool_type"] is None
    assert _panel_counts(data) == {"perforatory": 2, "ushm": 2, "dreli": 1}


@pytest.mark.django_db
def test_nonexistent_tool_type_yields_empty_list_but_full_panel(client, shop):
    # несуществующий slug: список и total = 0, но панель (own-axis) показывает реальные типы
    data = _facets(client, "?tool_type=nonexistent")
    assert data["total_products"] == 0
    assert _list_count(client, "?category=inst&tool_type=nonexistent") == 0
    assert data["applied_filters"]["tool_type"] == "nonexistent"
    # панель не схлопывается — пользователь может выбрать реальный тип
    assert _panel_counts(data) == {"perforatory": 2, "ushm": 2, "dreli": 1}
    panel = _get_facet(data, "tool_type")
    assert all(v["selected"] is False for v in panel["values"])
