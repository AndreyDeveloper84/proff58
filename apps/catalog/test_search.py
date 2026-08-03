"""Тесты поиска по каталогу и подсказок автодополнения (#52, trigram V1)."""

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductStatus, StockStatus


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tree(db):
    root = Category.add_root(name="Электроинструмент", slug="ei")
    leaf = root.add_child(name="Перфораторы", slug="perf")
    return root, leaf


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


def _slugs(resp):
    return {r["slug"] for r in resp.json()["results"]}


# --- Базовый матчинг по разным полям -----------------------------------------


@pytest.mark.django_db
def test_search_by_name_word(client, tree):
    _, leaf = tree
    make_product(leaf, "Перфоратор Bosch GBH 2-26", "p-bosch")
    make_product(leaf, "Дрель Makita HP1631", "d-makita")
    assert _slugs(client.get("/api/catalog/products/?search=перфоратор")) == {"p-bosch"}


@pytest.mark.django_db
def test_search_by_article_partial(client, tree):
    _, leaf = tree
    make_product(leaf, "Перфоратор A", "art-a", article="GBH22600")
    make_product(leaf, "Перфоратор B", "art-b", article="HP1631")
    assert _slugs(client.get("/api/catalog/products/?search=GBH226")) == {"art-a"}


@pytest.mark.django_db
def test_search_by_code_1c_exact_and_prefix(client, tree):
    _, leaf = tree
    make_product(leaf, "Товар по коду", "code-x", code_1c="00-0001234")
    make_product(leaf, "Другой", "code-y", code_1c="00-0009999")
    # точное
    assert _slugs(client.get("/api/catalog/products/?search=00-0001234")) == {"code-x"}
    # префикс
    assert _slugs(client.get("/api/catalog/products/?search=00-00012")) == {"code-x"}


@pytest.mark.django_db
def test_search_by_brand(client, tree):
    _, leaf = tree
    make_product(leaf, "Инструмент 1", "br-1", brand="Bosch")
    make_product(leaf, "Инструмент 2", "br-2", brand="Makita")
    assert _slugs(client.get("/api/catalog/products/?search=Bosch")) == {"br-1"}


# --- Взвешенный ранг ----------------------------------------------------------


@pytest.mark.django_db
def test_weighted_rank_exact_article_above_name_match(client, tree):
    """Товар с точным совпадением артикула ранжируется ВЫШЕ совпавшего по имени."""
    _, leaf = tree
    # совпадает по имени (вхождение слова "drill")
    make_product(leaf, "Машина drill для всего", "by-name", article="ZZZ-1")
    # совпадает по точному артикулу
    make_product(leaf, "Совсем другое имя", "by-article", article="DRILL")
    results = client.get("/api/catalog/products/?search=DRILL").json()["results"]
    slugs = [r["slug"] for r in results]
    assert slugs.index("by-article") < slugs.index("by-name")


@pytest.mark.django_db
def test_weighted_rank_code_1c_exact_above_name(client, tree):
    _, leaf = tree
    make_product(leaf, "Содержит ABC123 в имени", "name-hit", code_1c="ZZZ")
    make_product(leaf, "Имя без совпадения", "code-hit", code_1c="ABC123")
    results = client.get("/api/catalog/products/?search=ABC123").json()["results"]
    slugs = [r["slug"] for r in results]
    assert slugs.index("code-hit") < slugs.index("name-hit")


# --- Typo-tolerance / регистр -------------------------------------------------


@pytest.mark.django_db
def test_search_typo_tolerance(client, tree):
    """Опечатка в длинном слове ловится через trigram_similar (порог 0.3)."""
    _, leaf = tree
    make_product(leaf, "Перфоратор Bosch GBH 2-26", "typo-perf")
    # "перфоратр" — пропущена буква
    assert _slugs(client.get("/api/catalog/products/?search=перфоратр")) == {"typo-perf"}


@pytest.mark.django_db
def test_search_case_insensitive(client, tree):
    _, leaf = tree
    make_product(leaf, "Перфоратор Bosch", "ci-perf")
    upper = _slugs(client.get("/api/catalog/products/?search=ПЕРФОРАТОР"))
    lower = _slugs(client.get("/api/catalog/products/?search=перфоратор"))
    assert upper == lower == {"ci-perf"}


# --- Видимость ----------------------------------------------------------------


@pytest.mark.django_db
def test_search_excludes_invisible(client, tree):
    _, leaf = tree
    make_product(leaf, "Перфоратор видимый", "vis-perf")
    make_product(leaf, "Перфоратор черновик", "draft-perf", status=ProductStatus.DRAFT)
    make_product(leaf, "Перфоратор выключен", "off-perf", is_active=False)
    assert _slugs(client.get("/api/catalog/products/?search=перфоратор")) == {"vis-perf"}


# --- Короткий запрос / комбинация фильтров ------------------------------------


@pytest.mark.django_db
def test_search_too_short_no_filter(client, tree):
    """Запрос короче 2 символов не сужает выдачу (поиск не применяется)."""
    _, leaf = tree
    make_product(leaf, "Перфоратор", "short-1")
    make_product(leaf, "Дрель", "short-2")
    assert _slugs(client.get("/api/catalog/products/?search=п")) == {"short-1", "short-2"}


@pytest.mark.django_db
def test_search_combined_with_brand(client, tree):
    _, leaf = tree
    make_product(leaf, "Перфоратор Bosch", "comb-bosch", brand="Bosch")
    make_product(leaf, "Перфоратор Makita", "comb-makita", brand="Makita")
    resp = client.get("/api/catalog/products/?search=перфоратор&brand=Bosch")
    assert _slugs(resp) == {"comb-bosch"}


@pytest.mark.django_db
def test_search_response_is_listing_shape(client, tree):
    """Ответ поиска — стандартный листинг (LimitOffsetPagination: count/results)."""
    _, leaf = tree
    make_product(leaf, "Перфоратор один", "shape-1")
    data = client.get("/api/catalog/products/?search=перфоратор").json()
    assert "count" in data and "results" in data
    assert data["count"] == 1
    assert data["results"][0]["slug"] == "shape-1"


# --- N+1 ----------------------------------------------------------------------


@pytest.mark.django_db
def test_search_no_nplus1(client, tree, django_assert_max_num_queries):
    _, leaf = tree
    from apps.catalog.models import ProductImage

    for i in range(15):
        p = make_product(leaf, f"Перфоратор {i}", f"n-{i}", brand="Bosch")
        ProductImage.objects.create(product=p, image=f"products/{i}.jpg", is_main=True)
    with django_assert_max_num_queries(12):
        resp = client.get("/api/catalog/products/?search=перфоратор")
    assert resp.status_code == 200


# --- Подсказки ----------------------------------------------------------------


@pytest.mark.django_db
def test_suggest_shape_and_limit(client, tree):
    _, leaf = tree
    for i in range(15):
        make_product(leaf, f"Перфоратор {i:02d}", f"sg-{i}")
    rows = client.get("/api/catalog/search/suggest/?q=перфоратор").json()
    assert len(rows) == 10  # SUGGEST_LIMIT
    assert set(rows[0].keys()) == {"id", "name", "slug"}


@pytest.mark.django_db
def test_suggest_short_query_empty(client, tree):
    _, leaf = tree
    make_product(leaf, "Перфоратор", "sg-short")
    assert client.get("/api/catalog/search/suggest/?q=п").json() == []
    assert client.get("/api/catalog/search/suggest/").json() == []


@pytest.mark.django_db
def test_suggest_only_visible(client, tree):
    _, leaf = tree
    make_product(leaf, "Перфоратор видимый", "sgv-1")
    make_product(leaf, "Перфоратор черновик", "sgv-2", status=ProductStatus.DRAFT)
    make_product(leaf, "Перфоратор выключен", "sgv-3", is_active=False)
    slugs = {r["slug"] for r in client.get("/api/catalog/search/suggest/?q=перфоратор").json()}
    assert slugs == {"sgv-1"}


@pytest.mark.django_db
def test_suggest_ranked_exact_prefix_first(client, tree):
    """Точное/префиксное совпадение имени стоит выше частичного."""
    _, leaf = tree
    make_product(leaf, "Большой перфоратор для бетона", "sgr-partial")
    make_product(leaf, "Перфоратор", "sgr-exact")
    rows = client.get("/api/catalog/search/suggest/?q=перфоратор").json()
    slugs = [r["slug"] for r in rows]
    assert slugs.index("sgr-exact") < slugs.index("sgr-partial")


# --- Порядок выдачи: сначала то, что есть в наличии ----------------------------


@pytest.mark.django_db
def test_search_available_first_even_if_less_relevant(client, tree):
    """Наличие важнее релевантности: точное совпадение без остатка уступает.

    Раньше поиск сортировал по чистой релевантности, и первые экраны состояли из
    «Нет в наличии», хотя по тому же запросу доступный товар существовал.
    """
    _, leaf = tree
    make_product(leaf, "Перфоратор", "sa-exact-out", stock_status=StockStatus.OUT_OF_STOCK)
    make_product(
        leaf,
        "Большой перфоратор для бетона",
        "sa-partial-in",
        stock_status=StockStatus.IN_STOCK,
        stock_quantity=5,
    )
    slugs = [
        r["slug"] for r in client.get("/api/catalog/products/?search=перфоратор").json()["results"]
    ]
    assert slugs == ["sa-partial-in", "sa-exact-out"]


@pytest.mark.django_db
def test_search_on_order_between_in_stock_and_out(client, tree):
    _, leaf = tree
    make_product(leaf, "Перфоратор A", "so-out", stock_status=StockStatus.OUT_OF_STOCK)
    make_product(leaf, "Перфоратор B", "so-order", stock_status=StockStatus.ON_ORDER)
    make_product(leaf, "Перфоратор C", "so-in", stock_status=StockStatus.IN_STOCK)
    slugs = [
        r["slug"] for r in client.get("/api/catalog/products/?search=перфоратор").json()["results"]
    ]
    assert slugs == ["so-in", "so-order", "so-out"]


@pytest.mark.django_db
def test_suggest_available_first(client, tree):
    _, leaf = tree
    make_product(leaf, "Перфоратор", "sga-exact-out", stock_status=StockStatus.OUT_OF_STOCK)
    make_product(
        leaf, "Большой перфоратор для бетона", "sga-partial-in", stock_status=StockStatus.IN_STOCK
    )
    slugs = [r["slug"] for r in client.get("/api/catalog/search/suggest/?q=перфоратор").json()]
    assert slugs == ["sga-partial-in", "sga-exact-out"]


# --- Точечная выборка по id (карточки избранного) ------------------------------


@pytest.mark.django_db
def test_ids_filter_returns_exactly_requested(client, tree):
    _, leaf = tree
    a = make_product(leaf, "Товар А", "ids-a")
    b = make_product(leaf, "Товар Б", "ids-b")
    make_product(leaf, "Товар В", "ids-c")
    assert _slugs(client.get(f"/api/catalog/products/?ids={a.id},{b.id}")) == {"ids-a", "ids-b"}


@pytest.mark.django_db
def test_ids_filter_skips_invisible(client, tree):
    """Выключенный товар не всплывает даже по прямому запросу id."""
    _, leaf = tree
    visible = make_product(leaf, "Товар видимый", "idsv-1")
    hidden = make_product(leaf, "Товар выключен", "idsv-2", is_active=False)
    assert _slugs(client.get(f"/api/catalog/products/?ids={visible.id},{hidden.id}")) == {"idsv-1"}


@pytest.mark.django_db
def test_ids_filter_garbage_returns_nothing(client, tree):
    """Явный фильтр, который ничего не выбрал, отдаёт пустоту, а не весь каталог."""
    _, leaf = tree
    make_product(leaf, "Товар А", "idsg-a")
    assert client.get("/api/catalog/products/?ids=abc,,").json()["count"] == 0
