"""Тесты публичного API рекомендаций /api/ai/products/<slug>/recommendations/."""

import pytest
from rest_framework.test import APIClient

from apps.ai.services import DEFAULT_LIMIT
from apps.catalog.models import Category, Product, ProductStatus


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def category(db):
    return Category.add_root(name="Перфораторы", slug="perf")


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


@pytest.mark.django_db
def test_recommendations_ok_with_price_and_reason(client, category):
    anchor = make_product(category, "anchor", attrs={"power": 800})
    similar = make_product(category, "similar", attrs={"power": 800}, price="1500")

    resp = client.get(f"/api/ai/products/{anchor.slug}/recommendations/")

    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    item = results[0]
    assert item["id"] == similar.id
    assert item["price"] == "1500.00"
    assert "1 совпадений" in item["reason"]
    assert item["score"] > 0


@pytest.mark.django_db
def test_unknown_slug_returns_404(client, category):
    resp = client.get("/api/ai/products/no-such-slug/recommendations/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_hidden_anchor_returns_404(client, category):
    hidden = make_product(category, "hidden", attrs={"a": "x"}, is_active=False)
    resp = client.get(f"/api/ai/products/{hidden.slug}/recommendations/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_output_order_matches_recs(client, category):
    anchor = make_product(category, "anchor", attrs={"a": "x", "b": "y", "c": "z"})
    three = make_product(category, "three", attrs={"a": "x", "b": "y", "c": "z"})
    one = make_product(category, "one", attrs={"a": "x"})

    resp = client.get(f"/api/ai/products/{anchor.slug}/recommendations/")

    ids = [r["id"] for r in resp.json()["results"]]
    assert ids == [three.id, one.id]


@pytest.mark.django_db
def test_limit_query_param(client, category):
    anchor = make_product(category, "anchor", attrs={"a": "x"})
    for i in range(5):
        make_product(category, f"c{i}", attrs={"a": "x"})

    resp = client.get(f"/api/ai/products/{anchor.slug}/recommendations/?limit=2")

    assert len(resp.json()["results"]) == 2


@pytest.mark.django_db
def test_no_n_plus_one_on_price(client, category, django_assert_max_num_queries):
    anchor = make_product(category, "anchor", attrs={"a": "x"})
    for i in range(10):
        make_product(category, f"c{i}", attrs={"a": "x"}, brand="Bosch")

    # Запросы: якорь, recommend(candidates), гидрация (+prefetch images),
    # bulk price_map. Число фиксированное и не растёт с числом рекомендаций.
    with django_assert_max_num_queries(10):
        resp = client.get(f"/api/ai/products/{anchor.slug}/recommendations/")
    assert resp.status_code == 200
    # 10 кандидатов с overlap, но дефолтный limit ограничивает выдачу.
    assert len(resp.json()["results"]) == DEFAULT_LIMIT
