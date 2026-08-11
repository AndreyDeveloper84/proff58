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


def link(category, attribute, sort_order=0, group=None):
    kwargs = {"category": category, "attribute": attribute, "sort_order": sort_order}
    if group is not None:
        kwargs["group"] = group
    return CategoryAttribute.objects.create(**kwargs)


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

    with django_assert_max_num_queries(12):
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

    with django_assert_max_num_queries(12):
        client.get("/api/catalog/categories/dreli/facets/")


@pytest.mark.django_db
def test_facets_attr_range_drilldown(client, tree):
    """Числовой range-фильтр в фасетах: total согласован со списком, drill-down считает
    остальные фасеты в пределах диапазона, а сам числовой фасет НЕ схлопывается к выбору."""
    _, leaf = tree
    link(leaf, make_attr("diameter", "Диаметр", AttributeType.DECIMAL, unit="мм"))
    link(leaf, make_attr("chuck", "Патрон", AttributeType.SELECT), sort_order=1)
    make_product(leaf, "d10", {"diameter": 10, "chuck": "A"})
    make_product(leaf, "d20", {"diameter": 20, "chuck": "B"})
    make_product(leaf, "d30", {"diameter": 30, "chuck": "A"})
    make_product(leaf, "nod", {"chuck": "B"})  # без diameter — должен выпадать из диапазона

    qs = "attr_diameter_min=5&attr_diameter_max=25"
    data = client.get(f"/api/catalog/categories/dreli/facets/?{qs}").json()
    # total: diameter∈[5,25] → d10,d20 (nod исключён, d30 вне); совпадает со списком товаров
    assert data["total_products"] == 2
    list_count = client.get(f"/api/catalog/products/?category=dreli&{qs}").json()["count"]
    assert list_count == 2
    # chuck-фасет считается в пределах диапазона: A(d10)=1, B(d20)=1
    assert values_count(get_facet(data, "chuck")) == {"A": 1, "B": 1}
    # diameter-фасет НЕ схлопнут к [5,25] — показывает все значения (own-axis исключён),
    # иначе пользователь не смог бы расширить диапазон обратно
    assert set(values_count(get_facet(data, "diameter"))) == {10.0, 20.0, 30.0}


@pytest.mark.django_db
def test_facets_attr_range_ignores_nonnumeric_cache(client, tree):
    """Нечисловая строка в attrs_cache под числовым атрибутом НЕ роняет фасеты (guarded cast,
    P2-4): эндпоинт отдаёт 200, мусорный товар выпадает (как без значения), числовые считаются.
    Без гарда был бы DataError в SQL-касте диапазона и ValueError в Python-касте значения фасета."""
    _, leaf = tree
    link(leaf, make_attr("diameter", "Диаметр", AttributeType.DECIMAL, unit="мм"))
    make_product(leaf, "d10", {"diameter": 10})
    make_product(leaf, "d20", {"diameter": 20})
    make_product(leaf, "bad", {"diameter": "н/д"})  # нечисловой мусор под числовым атрибутом

    qs = "attr_diameter_min=5&attr_diameter_max=25"
    resp = client.get(f"/api/catalog/categories/dreli/facets/?{qs}")
    assert resp.status_code == 200  # без guarded cast здесь был бы 500
    data = resp.json()
    # diameter∈[5,25] → d10,d20; "bad" исключён (нечисловое = как отсутствие значения)
    assert data["total_products"] == 2
    # список товаров согласован с фасетами тем же (защищённым) механизмом
    list_count = client.get(f"/api/catalog/products/?category=dreli&{qs}").json()["count"]
    assert list_count == 2
    # diameter-фасет (own-axis, без диапазона) считает только валидные числа; "н/д" пропущен
    assert set(values_count(get_facet(data, "diameter"))) == {10.0, 20.0}


# --- B1 (#222, §10.2/§22.3): per-category CategoryAttribute.is_filter гейтит состав фасетов ---


@pytest.mark.django_db
def test_is_filter_false_excludes_facet(client, tree):
    """Атрибут, привязанный к категории с is_filter=False, НЕ попадает в facets,
    хотя глобально is_filterable=True и значения у товаров есть."""
    _, leaf = tree
    power = make_attr("power", "Мощность", AttributeType.INTEGER)
    chuck = make_attr("chuck", "Патрон", AttributeType.SELECT)
    # power выключен как фильтр для ЭТОЙ категории; chuck — оставлен
    CategoryAttribute.objects.create(category=leaf, attribute=power, is_filter=False)
    CategoryAttribute.objects.create(category=leaf, attribute=chuck, is_filter=True, sort_order=1)
    make_product(leaf, "p1", {"power": 500, "chuck": "Быстрозажимной"})
    make_product(leaf, "p2", {"power": 650, "chuck": "Ключевой"})

    data = client.get("/api/catalog/categories/dreli/facets/").json()
    slugs = {f["slug"] for f in data["facets"]}
    assert "power" not in slugs  # отключён per-category
    assert "chuck" in slugs  # остался
    # total и прочие фасеты считаются как обычно (гейт только про состав)
    assert data["total_products"] == 2


@pytest.mark.django_db
def test_is_filter_true_includes_facet(client, tree):
    """Тот же атрибут с is_filter=True попадает в facets (контроль к предыдущему тесту)."""
    _, leaf = tree
    power = make_attr("power", "Мощность", AttributeType.INTEGER)
    CategoryAttribute.objects.create(category=leaf, attribute=power, is_filter=True)
    make_product(leaf, "p1", {"power": 500})
    make_product(leaf, "p2", {"power": 650})

    data = client.get("/api/catalog/categories/dreli/facets/").json()
    assert "power" in {f["slug"] for f in data["facets"]}
    assert values_count(get_facet(data, "power")) == {500: 1, 650: 1}


@pytest.mark.django_db
def test_is_filter_false_inherited_from_ancestor(client, tree):
    """Гейт наследуется: атрибут привязан только к ПРЕДКУ с is_filter=False (у листа своей
    привязки нет) → у листа он тоже не показывается. Двойной гейт применяется по всей цепочке."""
    root, leaf = tree
    power = make_attr("power", "Мощность", AttributeType.INTEGER)
    chuck = make_attr("chuck", "Патрон", AttributeType.SELECT)
    CategoryAttribute.objects.create(category=root, attribute=power, is_filter=False)
    CategoryAttribute.objects.create(category=root, attribute=chuck, is_filter=True)
    make_product(leaf, "p1", {"power": 500, "chuck": "A"})

    data = client.get("/api/catalog/categories/dreli/facets/").json()
    slugs = {f["slug"] for f in data["facets"]}
    assert "power" not in slugs  # унаследованное исключение с предка
    assert "chuck" in slugs  # унаследованный включённый фильтр


# --- D1: группа фасета (§22.4) ---


@pytest.mark.django_db
def test_facet_group_default_main(client, tree):
    """Без указания группы фасет отдаёт group=main (дефолт, поведение до D1 не меняется)."""
    _, leaf = tree
    link(leaf, make_attr("power", "Мощность", AttributeType.INTEGER))
    make_product(leaf, "p1", {"power": 500})

    data = client.get("/api/catalog/categories/dreli/facets/").json()
    assert get_facet(data, "power")["group"] == "main"


@pytest.mark.django_db
def test_facet_group_extra_emitted(client, tree):
    """CategoryAttribute.group=extra → фасет помечается group=extra (раздел «Дополнительные»)."""
    _, leaf = tree
    from apps.catalog.models import FacetGroup

    link(leaf, make_attr("power", "Мощность", AttributeType.INTEGER), group=FacetGroup.MAIN)
    link(leaf, make_attr("weight", "Вес", AttributeType.DECIMAL, unit="кг"), group=FacetGroup.EXTRA)
    make_product(leaf, "p1", {"power": 500, "weight": 2.5})

    data = client.get("/api/catalog/categories/dreli/facets/").json()
    assert get_facet(data, "power")["group"] == "main"
    assert get_facet(data, "weight")["group"] == "extra"


@pytest.mark.django_db
def test_facet_group_closest_wins(client, tree):
    """Группа берётся из той же ближайшей строки CategoryAttribute, что выигрывает
    closest-wins: у листа group=extra перекрывает group=main предка для того же атрибута."""
    root, leaf = tree
    from apps.catalog.models import FacetGroup

    power = make_attr("power", "Мощность", AttributeType.INTEGER)
    link(root, power, sort_order=5, group=FacetGroup.MAIN)
    link(leaf, power, sort_order=1, group=FacetGroup.EXTRA)  # ближайшая категория
    make_product(leaf, "p1", {"power": 500})

    data = client.get("/api/catalog/categories/dreli/facets/").json()
    assert get_facet(data, "power")["group"] == "extra"


# --- D3: сортировка значений (§22.4) ---


@pytest.mark.django_db
def test_select_values_sorted_by_count_when_uncurated(client, tree):
    """SELECT без ручного порядка опций (sort_order=0 у всех) → значения по убыванию count,
    а не по алфавиту: популярные сверху."""
    _, leaf = tree
    chuck = make_attr("chuck", "Патрон", AttributeType.SELECT)
    link(leaf, chuck)
    # Опции с дефолтным sort_order=0 (порядок не курирован). «Ключевой» < «Я-патрон» по
    # алфавиту, но реже по count — должен оказаться НИЖЕ.
    AttributeOption.objects.create(attribute=chuck, value="Ключевой", sort_order=0)
    AttributeOption.objects.create(attribute=chuck, value="Я-патрон", sort_order=0)
    make_product(leaf, "p1", {"chuck": "Я-патрон"})
    make_product(leaf, "p2", {"chuck": "Я-патрон"})
    make_product(leaf, "p3", {"chuck": "Ключевой"})

    facet = get_facet(client.get("/api/catalog/categories/dreli/facets/").json(), "chuck")
    assert [v["value"] for v in facet["values"]] == ["Я-патрон", "Ключевой"]


@pytest.mark.django_db
def test_curated_sort_order_beats_count(client, tree):
    """Кураторский sort_order — главный ключ: опция с меньшим sort_order выше, даже если её
    count меньше (count лишь тайбрейк при равном sort_order)."""
    _, leaf = tree
    chuck = make_attr("chuck", "Патрон", AttributeType.SELECT)
    link(leaf, chuck)
    AttributeOption.objects.create(attribute=chuck, value="Первый", sort_order=0)  # реже
    AttributeOption.objects.create(attribute=chuck, value="Второй", sort_order=1)  # чаще
    make_product(leaf, "p1", {"chuck": "Первый"})
    make_product(leaf, "p2", {"chuck": "Второй"})
    make_product(leaf, "p3", {"chuck": "Второй"})

    facet = get_facet(client.get("/api/catalog/categories/dreli/facets/").json(), "chuck")
    assert [v["value"] for v in facet["values"]] == ["Первый", "Второй"]


@pytest.mark.django_db
def test_brand_facet_case_insensitive_grouping(client, tree):
    """«Bosch» и «BOSCH» должны объединяться в один пункт фасета (#281)."""
    _, leaf = tree
    make_product(leaf, "p1", {}, brand="Bosch")
    make_product(leaf, "p2", {}, brand="BOSCH")
    make_product(leaf, "p3", {}, brand="bosch")

    data = client.get("/api/catalog/categories/dreli/facets/").json()
    brands = data["brands"]
    assert len(brands) == 1, f"Ожидался 1 пункт бренда, получено: {brands}"
    assert brands[0]["count"] == 3


@pytest.mark.django_db
def test_brand_filter_case_insensitive(client, tree):
    """Фильтр ?brand=bosch находит товары с brand='Bosch' и 'BOSCH' (#281)."""
    _, leaf = tree
    make_product(leaf, "p1", {}, brand="Bosch")
    make_product(leaf, "p2", {}, brand="BOSCH")
    make_product(leaf, "p3", {}, brand="Makita")

    data = client.get("/api/catalog/categories/dreli/facets/?brand=bosch").json()
    assert data["total_products"] == 2


@pytest.mark.django_db
def test_display_name_override(client, tree):
    """Пер-категорийная подпись (CAT-03): display_name переопределяет name, slug не меняется."""
    _, leaf = tree
    size = make_attr("size", "Размер «под ключ»", AttributeType.INTEGER, unit="мм")
    CategoryAttribute.objects.create(category=leaf, attribute=size, display_name="Размер")
    make_product(leaf, "p1", {"size": 150})

    facet = get_facet(client.get("/api/catalog/categories/dreli/facets/").json(), "size")
    assert facet["name"] == "Размер"
    assert facet["slug"] == "size"  # ключ фильтра не изменился — сохранённые ссылки живы
    assert facet["unit"] == "мм"


@pytest.mark.django_db
def test_display_name_fallback_to_attribute_name(client, tree):
    """Пустой display_name — поведение как раньше: подпись = имя атрибута."""
    _, leaf = tree
    size = make_attr("size", "Размер «под ключ»", AttributeType.INTEGER, unit="мм")
    link(leaf, size)
    make_product(leaf, "p1", {"size": 150})

    facet = get_facet(client.get("/api/catalog/categories/dreli/facets/").json(), "size")
    assert facet["name"] == "Размер «под ключ»"
    assert facet["slug"] == "size"


@pytest.mark.django_db
def test_display_name_closest_wins(client, tree):
    """Общий атрибут: переопределение листа не трогает родителя (closest-wins)."""
    root, leaf = tree
    size = make_attr("size", "Размер «под ключ»", AttributeType.INTEGER, unit="мм")
    link(root, size)  # у родителя — без переопределения
    CategoryAttribute.objects.create(category=leaf, attribute=size, display_name="Размер")
    make_product(leaf, "p1", {"size": 150})

    leaf_facet = get_facet(client.get("/api/catalog/categories/dreli/facets/").json(), "size")
    root_facet = get_facet(client.get("/api/catalog/categories/ei/facets/").json(), "size")
    assert leaf_facet["name"] == "Размер"
    assert root_facet["name"] == "Размер «под ключ»"
    assert leaf_facet["slug"] == root_facet["slug"] == "size"
