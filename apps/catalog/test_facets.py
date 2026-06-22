"""Тесты фасетных фильтров каталога (#25)."""

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
    root = Category.add_root(name="Электроинструмент", slug="ei")
    leaf = root.add_child(name="Дрели", slug="dreli")
    return root, leaf


def make_attr(slug, name, atype, *, filterable=True, unit=""):
    return Attribute.objects.create(
        slug=slug, name=name, attribute_type=atype, is_filterable=filterable, unit=unit
    )


def link(category, attribute, sort_order=0):
    return CategoryAttribute.objects.create(
        category=category, attribute=attribute, sort_order=sort_order
    )


def make_product(
    category,
    slug,
    attrs,
    *,
    brand="",
    status=ProductStatus.PUBLISHED,
    is_active=True,
    stock_status=StockStatus.IN_STOCK,
):
    return Product.objects.create(
        category=category,
        name=slug,
        slug=slug,
        attrs_cache=attrs,
        brand=brand,
        status=status,
        is_active=is_active,
        stock_status=stock_status,
    )


def get_facet(data, slug):
    return next(f for f in data["facets"] if f["slug"] == slug)


def values_count(facet):
    return {v["value"]: v["count"] for v in facet["values"]}


@pytest.mark.django_db
def test_basic_facets(client, tree):
    _, leaf = tree
    power = make_attr("power", "Мощность", AttributeType.INTEGER, unit="Вт")
    chuck = make_attr("chuck", "Патрон", AttributeType.SELECT)
    link(leaf, power)
    link(leaf, chuck, sort_order=1)
    make_product(leaf, "p1", {"power": 500, "chuck": "Быстрозажимной"})
    make_product(leaf, "p2", {"power": 650, "chuck": "Быстрозажимной"})
    make_product(leaf, "p3", {"power": 650, "chuck": "Ключевой"})

    data = client.get("/api/catalog/categories/dreli/facets/").json()
    assert data["total_products"] == 3
    assert {f["slug"] for f in data["facets"]} == {"power", "chuck"}
    assert values_count(get_facet(data, "power")) == {500: 1, 650: 2}
    assert values_count(get_facet(data, "chuck")) == {"Быстрозажимной": 2, "Ключевой": 1}


@pytest.mark.django_db
def test_drill_down_and_selected(client, tree):
    _, leaf = tree
    power = make_attr("power", "Мощность", AttributeType.INTEGER)
    chuck = make_attr("chuck", "Патрон", AttributeType.SELECT)
    link(leaf, power)
    link(leaf, chuck)
    make_product(leaf, "p1", {"power": 500, "chuck": "Быстрозажимной"})
    make_product(leaf, "p2", {"power": 650, "chuck": "Быстрозажимной"})
    make_product(leaf, "p3", {"power": 650, "chuck": "Ключевой"})

    data = client.get("/api/catalog/categories/dreli/facets/?attr_power=650").json()
    # total — с учётом фильтра power=650
    assert data["total_products"] == 2
    # chuck пересчитан под power=650
    assert values_count(get_facet(data, "chuck")) == {"Быстрозажимной": 1, "Ключевой": 1}
    # power показывает все варианты (свой фильтр исключён из подсчёта)
    assert values_count(get_facet(data, "power")) == {500: 1, 650: 2}
    # значение 650 помечено selected
    pf = get_facet(data, "power")
    assert next(v for v in pf["values"] if v["value"] == 650)["selected"] is True
    assert next(v for v in pf["values"] if v["value"] == 500)["selected"] is False
    assert data["applied_filters"]["attrs"] == {"power": [650]}


@pytest.mark.django_db
def test_or_within_attribute(client, tree):
    _, leaf = tree
    power = make_attr("power", "Мощность", AttributeType.INTEGER)
    link(leaf, power)
    for i, p in enumerate([500, 650, 800]):
        make_product(leaf, f"p{i}", {"power": p})

    data = client.get("/api/catalog/categories/dreli/facets/?attr_power=500&attr_power=650").json()
    assert data["total_products"] == 2  # 500 OR 650


@pytest.mark.django_db
def test_multi_brand_or(client, tree):
    _, leaf = tree
    power = make_attr("power", "Мощность", AttributeType.INTEGER)
    link(leaf, power)
    make_product(leaf, "p1", {"power": 500}, brand="Bosch")
    make_product(leaf, "p2", {"power": 650}, brand="Makita")
    make_product(leaf, "p3", {"power": 800}, brand="DeWalt")

    data = client.get("/api/catalog/categories/dreli/facets/?brand=Bosch&brand=Makita").json()
    assert data["total_products"] == 2
    assert data["applied_filters"]["brands"] == ["Bosch", "Makita"]


@pytest.mark.django_db
def test_descendants_counted_for_parent(client, tree):
    root, leaf = tree
    power = make_attr("power", "Мощность", AttributeType.INTEGER)
    link(root, power)  # атрибут на родителе
    make_product(leaf, "p1", {"power": 500})  # товар в подкатегории

    data = client.get("/api/catalog/categories/ei/facets/").json()
    assert data["total_products"] == 1
    assert values_count(get_facet(data, "power")) == {500: 1}


@pytest.mark.django_db
def test_visibility_and_filterable(client, tree):
    _, leaf = tree
    power = make_attr("power", "Мощность", AttributeType.INTEGER)
    hidden = make_attr("secret", "Секрет", AttributeType.INTEGER, filterable=False)
    link(leaf, power)
    link(leaf, hidden)
    make_product(leaf, "vis", {"power": 500, "secret": 1})
    make_product(leaf, "draft", {"power": 500}, status=ProductStatus.DRAFT)
    make_product(leaf, "off", {"power": 500}, is_active=False)

    data = client.get("/api/catalog/categories/dreli/facets/").json()
    assert data["total_products"] == 1  # только видимый
    assert {f["slug"] for f in data["facets"]} == {"power"}  # secret не фильтруемый


@pytest.mark.django_db
def test_unknown_attr_ignored(client, tree):
    _, leaf = tree
    power = make_attr("power", "Мощность", AttributeType.INTEGER)
    link(leaf, power)
    make_product(leaf, "p1", {"power": 500})

    resp = client.get("/api/catalog/categories/dreli/facets/?attr_unknown=x")
    assert resp.status_code == 200
    assert resp.json()["applied_filters"]["attrs"] == {}


@pytest.mark.django_db
def test_invalid_known_value_400(client, tree):
    _, leaf = tree
    link(leaf, make_attr("power", "Мощность", AttributeType.INTEGER))
    make_product(leaf, "p1", {"power": 500})

    resp = client.get("/api/catalog/categories/dreli/facets/?attr_power=abc")
    assert resp.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    "raw,expected_total",
    [("true", 1), ("1", 1), ("yes", 1), ("да", 1), ("false", 1), ("0", 1), ("нет", 1)],
)
def test_boolean_parsing(client, tree, raw, expected_total):
    _, leaf = tree
    link(leaf, make_attr("reverse", "Реверс", AttributeType.BOOLEAN))
    make_product(leaf, "yes", {"reverse": True})
    make_product(leaf, "no", {"reverse": False})

    data = client.get(f"/api/catalog/categories/dreli/facets/?attr_reverse={raw}").json()
    assert data["total_products"] == expected_total


@pytest.mark.django_db
def test_invalid_boolean_400(client, tree):
    _, leaf = tree
    link(leaf, make_attr("reverse", "Реверс", AttributeType.BOOLEAN))
    make_product(leaf, "p1", {"reverse": True})

    resp = client.get("/api/catalog/categories/dreli/facets/?attr_reverse=maybe")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_parent_child_same_attribute_deduped(client, tree):
    root, leaf = tree
    power = make_attr("power", "Мощность", AttributeType.INTEGER)
    link(root, power, sort_order=5)
    link(leaf, power, sort_order=1)  # ближайшая категория
    make_product(leaf, "p1", {"power": 500})

    data = client.get("/api/catalog/categories/dreli/facets/").json()
    power_facets = [f for f in data["facets"] if f["slug"] == "power"]
    assert len(power_facets) == 1  # атрибут не задвоился


@pytest.mark.django_db
def test_unknown_select_option_does_not_crash(client, tree):
    _, leaf = tree
    chuck = make_attr("chuck", "Патрон", AttributeType.SELECT)
    link(leaf, chuck)
    AttributeOption.objects.create(attribute=chuck, value="Быстрозажимной", sort_order=0)
    make_product(leaf, "p1", {"chuck": "Быстрозажимной"})
    make_product(leaf, "p2", {"chuck": "Древний"})  # нет такой опции

    data = client.get("/api/catalog/categories/dreli/facets/").json()
    vals = [v["value"] for v in get_facet(data, "chuck")["values"]]
    assert vals == ["Быстрозажимной", "Древний"]  # неизвестная опция — в конец


@pytest.mark.django_db
def test_too_many_attr_filters_400(client, tree):
    _, leaf = tree
    link(leaf, make_attr("power", "Мощность", AttributeType.INTEGER))
    make_product(leaf, "p1", {"power": 500})

    qs = "&".join(f"attr_x{i}=1" for i in range(21))
    resp = client.get(f"/api/catalog/categories/dreli/facets/?{qs}")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_empty_facet_not_returned(client, tree):
    _, leaf = tree
    link(leaf, make_attr("power", "Мощность", AttributeType.INTEGER))
    # товар без значения power → фасет power пустой и не отдаётся
    make_product(leaf, "p1", {})

    data = client.get("/api/catalog/categories/dreli/facets/").json()
    assert data["facets"] == []


@pytest.mark.django_db
def test_invalid_stock_status_400(client, tree):
    _, leaf = tree
    link(leaf, make_attr("power", "Мощность", AttributeType.INTEGER))
    make_product(leaf, "p1", {"power": 500})

    resp = client.get("/api/catalog/categories/dreli/facets/?stock_status=bad")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_no_nplus1(client, tree, django_assert_max_num_queries):
    _, leaf = tree
    power = make_attr("power", "Мощность", AttributeType.INTEGER)
    chuck = make_attr("chuck", "Патрон", AttributeType.SELECT)
    link(leaf, power)
    link(leaf, chuck)
    for i in range(10):
        make_product(leaf, f"p{i}", {"power": 500 + i, "chuck": "Быстрозажимной"})

    with django_assert_max_num_queries(8):
        client.get("/api/catalog/categories/dreli/facets/")


def test_services_does_not_import_api():
    """Архитектурная развязка: сервисный слой не зависит от HTTP-слоя."""
    import apps.catalog.services as services_module

    src = open(services_module.__file__, encoding="utf-8").read()
    assert "catalog.api" not in src
    assert "from .api" not in src


# --- Типизация JSONB-containment (SQL-агрегация фасетов) ---


@pytest.mark.django_db
def test_jsonb_integer_match_typed(client, tree):
    """attr_power=18 матчит JSON-число 18, а не строку «18» (containment по типу)."""
    _, leaf = tree
    link(leaf, make_attr("power", "Мощность", AttributeType.INTEGER))
    make_product(leaf, "a", {"power": 18})
    make_product(leaf, "b", {"power": 20})

    data = client.get("/api/catalog/categories/dreli/facets/?attr_power=18").json()
    assert data["total_products"] == 1  # только товар с power=18
    facet = get_facet(data, "power")
    assert values_count(facet) == {18: 1, 20: 1}  # drill-down: оба значения, int-ключи


@pytest.mark.django_db
def test_jsonb_boolean_aggregation_is_bool(client, tree):
    """Значения boolean-фасета — Python bool True/False, не строки «true»/«false»."""
    _, leaf = tree
    link(leaf, make_attr("reverse", "Реверс", AttributeType.BOOLEAN))
    make_product(leaf, "a", {"reverse": True})
    make_product(leaf, "b", {"reverse": True})
    make_product(leaf, "c", {"reverse": False})

    facet = get_facet(client.get("/api/catalog/categories/dreli/facets/").json(), "reverse")
    counts = values_count(facet)
    assert counts == {True: 2, False: 1}
    assert all(isinstance(k, bool) for k in counts)


@pytest.mark.django_db
def test_jsonb_decimal_match_normalized(client, tree):
    """Decimal: 18.0 в JSONB и фильтр 18 совпадают (float-хранение)."""
    _, leaf = tree
    link(leaf, make_attr("weight", "Вес", AttributeType.DECIMAL, unit="кг"))
    make_product(leaf, "a", {"weight": 18.0})
    make_product(leaf, "b", {"weight": 2.5})

    data = client.get("/api/catalog/categories/dreli/facets/?attr_weight=18").json()
    assert data["total_products"] == 1
    facet = get_facet(data, "weight")
    assert values_count(facet) == {18.0: 1, 2.5: 1}


# --- slug-URL для select-значений (P2) ---


@pytest.mark.django_db
def test_select_slug_emitted_only_when_present(client, tree):
    """slug отдаём только при заполненном AttributeOption.slug; пустой → поля slug нет."""
    _, leaf = tree
    chuck = make_attr("chuck", "Патрон", AttributeType.SELECT)
    link(leaf, chuck)
    AttributeOption.objects.create(
        attribute=chuck, value="Быстрозажимной", slug="bystrozazhimnoy", sort_order=0
    )
    AttributeOption.objects.create(attribute=chuck, value="Ключевой", slug="", sort_order=1)
    make_product(leaf, "p1", {"chuck": "Быстрозажимной"})
    make_product(leaf, "p2", {"chuck": "Ключевой"})

    facet = get_facet(client.get("/api/catalog/categories/dreli/facets/").json(), "chuck")
    by_val = {v["value"]: v for v in facet["values"]}
    assert by_val["Быстрозажимной"]["slug"] == "bystrozazhimnoy"
    assert "slug" not in by_val["Ключевой"]  # пустой slug → поле не отдаём (fallback на value)


@pytest.mark.django_db
def test_filter_by_slug_and_legacy_raw(client, tree):
    """Фильтр принимает slug (canonical) и сырое значение (legacy); selected — после резолва."""
    _, leaf = tree
    chuck = make_attr("chuck", "Патрон", AttributeType.SELECT)
    link(leaf, chuck)
    AttributeOption.objects.create(
        attribute=chuck, value="Быстрозажимной", slug="bystro", sort_order=0
    )
    make_product(leaf, "p1", {"chuck": "Быстрозажимной"})
    make_product(leaf, "p2", {"chuck": "Ключевой"})

    data = client.get("/api/catalog/categories/dreli/facets/?attr_chuck=bystro").json()
    assert data["total_products"] == 1
    assert data["applied_filters"]["attrs"] == {"chuck": ["Быстрозажимной"]}  # резолв slug→value
    sel = {v["value"]: v["selected"] for v in get_facet(data, "chuck")["values"]}
    assert sel["Быстрозажимной"] is True  # selected отмечается при URL по slug
    assert sel["Ключевой"] is False

    # legacy сырое значение тоже фильтрует
    data2 = client.get("/api/catalog/categories/dreli/facets/?attr_chuck=Быстрозажимной").json()
    assert data2["total_products"] == 1


@pytest.mark.django_db
def test_unknown_slug_token_does_not_crash(client, tree):
    """Неизвестный токен: facets-эндпоинт не падает, ничего не находит, selected пуст."""
    _, leaf = tree
    chuck = make_attr("chuck", "Патрон", AttributeType.SELECT)
    link(leaf, chuck)
    AttributeOption.objects.create(
        attribute=chuck, value="Быстрозажимной", slug="bystro", sort_order=0
    )
    make_product(leaf, "p1", {"chuck": "Быстрозажимной"})

    resp = client.get("/api/catalog/categories/dreli/facets/?attr_chuck=nonexistent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_products"] == 0
    assert all(v["selected"] is False for v in get_facet(data, "chuck")["values"])


@pytest.mark.django_db
def test_slug_does_not_change_value_order(client, tree):
    """Добавление slug не влияет на порядок значений (сортировка по sort_order)."""
    _, leaf = tree
    chuck = make_attr("chuck", "Патрон", AttributeType.SELECT)
    link(leaf, chuck)
    AttributeOption.objects.create(attribute=chuck, value="Быстрозажимной", slug="b", sort_order=0)
    AttributeOption.objects.create(attribute=chuck, value="Ключевой", slug="k", sort_order=1)
    make_product(leaf, "p1", {"chuck": "Ключевой"})
    make_product(leaf, "p2", {"chuck": "Быстрозажимной"})

    facet = get_facet(client.get("/api/catalog/categories/dreli/facets/").json(), "chuck")
    assert [v["value"] for v in facet["values"]] == ["Быстрозажимной", "Ключевой"]


@pytest.mark.django_db
def test_resolve_attr_tokens_dedupes_slug_and_raw(tree):
    """resolve_attr_tokens: slug и сырое значение схлопываются в один canonical value."""
    from apps.catalog.facets import resolve_attr_tokens

    _, leaf = tree
    chuck = make_attr("chuck", "Патрон", AttributeType.SELECT)
    AttributeOption.objects.create(
        attribute=chuck, value="Быстрозажимной", slug="bystro", sort_order=0
    )

    assert resolve_attr_tokens(chuck, ["bystro", "Быстрозажимной"]) == ["Быстрозажимной"]
    assert resolve_attr_tokens(chuck, ["unknown"]) == ["unknown"]  # неизвестный токен — как есть


@pytest.mark.django_db
def test_facet_queries_scale_with_attrs_not_products(client, tree, django_assert_max_num_queries):
    """Число запросов задаётся числом фасетов, а не товаров (100 товаров ≤ тот же лимит)."""
    _, leaf = tree
    link(leaf, make_attr("power", "Мощность", AttributeType.INTEGER))
    link(leaf, make_attr("chuck", "Патрон", AttributeType.SELECT))
    for i in range(100):
        make_product(leaf, f"p{i}", {"power": 500 + (i % 5), "chuck": "Быстрозажимной"})

    with django_assert_max_num_queries(8):
        client.get("/api/catalog/categories/dreli/facets/")
