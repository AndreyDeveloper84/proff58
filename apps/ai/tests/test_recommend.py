"""Тесты детерминированного EAV-движка recommend() (#73, V1, без LLM)."""

import pytest

from apps.ai.services import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    Recommendation,
    recommend,
)
from apps.catalog.models import Category, Product, ProductStatus


@pytest.fixture
def category(db):
    return Category.add_root(name="Перфораторы", slug="perf")


@pytest.fixture
def other_category(db):
    return Category.add_root(name="Дрели", slug="dreli")


def make_product(category, slug, *, attrs=None, brand="", **kw):
    data = {
        "category": category,
        "name": slug,
        "slug": slug,
        "status": ProductStatus.PUBLISHED,
        "is_active": True,
        "price": "1000",
        "brand": brand,
        "attrs_cache": attrs or {},
    }
    data.update(kw)
    return Product.objects.create(**data)


# --- Контракт ----------------------------------------------------------------


@pytest.mark.django_db
def test_returns_list_of_recommendations(category):
    anchor = make_product(category, "anchor", attrs={"power": 800})
    similar = make_product(category, "similar", attrs={"power": 800})

    recs = recommend(context={"product_id": anchor.id})

    assert isinstance(recs, list)
    assert all(isinstance(r, Recommendation) for r in recs)
    assert {r.product_id for r in recs} == {similar.id}


@pytest.mark.django_db
def test_empty_or_invalid_context_returns_empty():
    assert recommend(context=None) == []
    assert recommend(context={}) == []
    assert recommend(context={"product_id": None}) == []
    assert recommend(context={"product_id": 999999}) == []


@pytest.mark.django_db
def test_query_reserved_not_used(category):
    anchor = make_product(category, "anchor", attrs={"power": 800})
    make_product(category, "similar", attrs={"power": 800})
    # query задан, но не влияет: якорь всё равно из context.
    recs = recommend(query="что угодно", context={"product_id": anchor.id})
    assert len(recs) == 1


# --- Ранжирование ------------------------------------------------------------


@pytest.mark.django_db
def test_more_overlap_ranks_higher(category):
    anchor = make_product(category, "anchor", attrs={"a": "x", "b": "y", "c": "z"})
    three = make_product(category, "three", attrs={"a": "x", "b": "y", "c": "z"})
    one = make_product(category, "one", attrs={"a": "x"})

    recs = recommend(context={"product_id": anchor.id})

    assert [r.product_id for r in recs] == [three.id, one.id]
    assert recs[0].score > recs[1].score


@pytest.mark.django_db
def test_brand_is_tiebreaker_not_dominant(category):
    """3 overlap (без бренда) выше 2 overlap + тот же бренд: 30 > 20+3."""
    anchor = make_product(category, "anchor", brand="Bosch", attrs={"a": "x", "b": "y", "c": "z"})
    high_overlap = make_product(
        category, "high", brand="Makita", attrs={"a": "x", "b": "y", "c": "z"}
    )
    brand_match = make_product(category, "brand", brand="Bosch", attrs={"a": "x", "b": "y"})

    recs = recommend(context={"product_id": anchor.id})

    assert [r.product_id for r in recs] == [high_overlap.id, brand_match.id]
    # 3 overlap, не тот же бренд, in_stock(остаток 0) → 30
    assert recs[0].score == pytest.approx(30.0)
    # 2 overlap + тот же бренд → 20 + 3 = 23
    assert recs[1].score == pytest.approx(23.0)


@pytest.mark.django_db
def test_score_includes_stock_bonus(category):
    anchor = make_product(category, "anchor", attrs={"a": "x"})
    make_product(category, "instock", attrs={"a": "x"}, stock_quantity=5)

    recs = recommend(context={"product_id": anchor.id})
    # overlap 1*10 + in_stock 1 = 11
    assert recs[0].score == pytest.approx(11.0)


# --- Нормализация значений ---------------------------------------------------


@pytest.mark.django_db
def test_boolean_false_counts_as_match(category):
    anchor = make_product(category, "anchor", attrs={"reverse": False})
    match = make_product(category, "match", attrs={"reverse": False})
    make_product(category, "mismatch", attrs={"reverse": True})

    recs = recommend(context={"product_id": anchor.id})

    assert [r.product_id for r in recs] == [match.id]


@pytest.mark.django_db
def test_string_normalization_whitespace_and_case(category):
    anchor = make_product(category, "anchor", attrs={"voltage": "220 В"})
    match = make_product(category, "match", attrs={"voltage": " 220 в "})

    recs = recommend(context={"product_id": anchor.id})

    assert [r.product_id for r in recs] == [match.id]
    assert "1 совпадений" in recs[0].reason


@pytest.mark.django_db
def test_brand_normalization_case_insensitive(category):
    anchor = make_product(category, "anchor", brand="Bosch")
    match = make_product(category, "match", brand="BOSCH")

    recs = recommend(context={"product_id": anchor.id})

    assert [r.product_id for r in recs] == [match.id]
    assert recs[0].reason == "Та же категория, тот же бренд"


@pytest.mark.django_db
def test_list_overlap_counts_intersection(category):
    anchor = make_product(category, "anchor", attrs={"modes": ["сверление", "удар", "долбление"]})
    make_product(category, "two", attrs={"modes": ["Сверление", " удар "]})

    recs = recommend(context={"product_id": anchor.id})
    # пересечение нормализованных = 2 → overlap 2
    assert recs[0].score == pytest.approx(20.0)


# --- Фильтрация / отсечение шума ---------------------------------------------


@pytest.mark.django_db
def test_anchor_itself_excluded(category):
    anchor = make_product(category, "anchor", attrs={"a": "x"})
    make_product(category, "similar", attrs={"a": "x"})

    recs = recommend(context={"product_id": anchor.id})

    assert anchor.id not in {r.product_id for r in recs}


@pytest.mark.django_db
def test_other_category_excluded(category, other_category):
    anchor = make_product(category, "anchor", attrs={"a": "x"})
    make_product(other_category, "foreign", attrs={"a": "x"})

    recs = recommend(context={"product_id": anchor.id})

    assert recs == []


@pytest.mark.django_db
def test_hidden_and_draft_candidates_excluded(category):
    anchor = make_product(category, "anchor", attrs={"a": "x"})
    make_product(category, "draft", attrs={"a": "x"}, status=ProductStatus.DRAFT)
    make_product(category, "inactive", attrs={"a": "x"}, is_active=False)

    recs = recommend(context={"product_id": anchor.id})

    assert recs == []


@pytest.mark.django_db
def test_hidden_anchor_returns_empty(category):
    hidden = make_product(category, "hidden", attrs={"a": "x"}, is_active=False)
    make_product(category, "similar", attrs={"a": "x"})

    recs = recommend(context={"product_id": hidden.id})

    assert recs == []


@pytest.mark.django_db
def test_empty_anchor_attrs_matches_by_brand(category):
    anchor = make_product(category, "anchor", brand="Bosch", attrs={})
    same_brand = make_product(category, "same", brand="Bosch", attrs={"a": "x"})

    recs = recommend(context={"product_id": anchor.id})

    assert [r.product_id for r in recs] == [same_brand.id]
    assert recs[0].reason == "Та же категория, тот же бренд"


@pytest.mark.django_db
def test_no_signal_returns_empty(category):
    """Нет ни overlap, ни общего бренда — только категория → отсекается как шум."""
    anchor = make_product(category, "anchor", brand="Bosch", attrs={"a": "x"})
    make_product(category, "noise", brand="Makita", attrs={"b": "y"})

    recs = recommend(context={"product_id": anchor.id})

    assert recs == []


# --- limit -------------------------------------------------------------------


@pytest.mark.django_db
def test_limit_respected(category):
    anchor = make_product(category, "anchor", attrs={"a": "x"})
    for i in range(5):
        make_product(category, f"c{i}", attrs={"a": "x"})

    recs = recommend(context={"product_id": anchor.id}, limit=3)

    assert len(recs) == 3


@pytest.mark.django_db
def test_limit_non_positive_returns_empty(category):
    anchor = make_product(category, "anchor", attrs={"a": "x"})
    make_product(category, "similar", attrs={"a": "x"})

    assert recommend(context={"product_id": anchor.id}, limit=0) == []
    assert recommend(context={"product_id": anchor.id}, limit=-5) == []


@pytest.mark.django_db
def test_limit_capped_at_max(category):
    anchor = make_product(category, "anchor", attrs={"a": "x"})
    for i in range(MAX_LIMIT + 5):
        make_product(category, f"c{i}", attrs={"a": "x"})

    recs = recommend(context={"product_id": anchor.id}, limit=10000)

    assert len(recs) == MAX_LIMIT


@pytest.mark.django_db
def test_default_limit(category):
    anchor = make_product(category, "anchor", attrs={"a": "x"})
    for i in range(DEFAULT_LIMIT + 3):
        make_product(category, f"c{i}", attrs={"a": "x"})

    recs = recommend(context={"product_id": anchor.id})

    assert len(recs) == DEFAULT_LIMIT


# --- Детерминизм -------------------------------------------------------------


@pytest.mark.django_db
def test_stable_order_on_equal_score(category):
    """При равном score меньший id выше — устойчивый детерминированный порядок."""
    anchor = make_product(category, "anchor", attrs={"a": "x"})
    c1 = make_product(category, "c1", attrs={"a": "x"})
    c2 = make_product(category, "c2", attrs={"a": "x"})
    c3 = make_product(category, "c3", attrs={"a": "x"})

    recs = recommend(context={"product_id": anchor.id})

    ids = [r.product_id for r in recs]
    assert ids == sorted([c1.id, c2.id, c3.id])
    # повторный вызов даёт тот же порядок
    assert [r.product_id for r in recommend(context={"product_id": anchor.id})] == ids
