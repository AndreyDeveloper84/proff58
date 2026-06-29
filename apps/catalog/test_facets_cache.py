"""Тесты кэша фасетов (#222, P1-2): кэш-хит экономит запросы, запись инвалидирует версию,
выключенный по умолчанию кэш всегда отдаёт свежее."""

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductStatus, StockStatus

FACETS_URL = "/api/catalog/categories/dreli/facets/"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def _isolate_cache():
    # LocMemCache живёт между тестами в одном процессе, а ключи (category+params) у тестов
    # совпадают — чистим до и после, чтобы кэш фасетов одного теста не протекал в другой.
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def leaf(db):
    root = Category.add_root(name="Электроинструмент", slug="ei")
    return root.add_child(name="Дрели", slug="dreli")


def _product(category, slug, price):
    return Product.objects.create(
        category=category,
        name=slug,
        slug=slug,
        price=price,
        attrs_cache={},
        status=ProductStatus.PUBLISHED,
        is_active=True,
        stock_status=StockStatus.IN_STOCK,
    )


@pytest.mark.django_db
def test_cache_hit_skips_recompute(client, leaf, settings):
    """Второй идентичный запрос обслуживается из кэша: ответ тот же, а запросов к БД
    кратно меньше (на miss — пересчёт фасетов, на hit — только поиск категории)."""
    settings.FACETS_CACHE_TTL = 300
    _product(leaf, "p1", "100")

    with CaptureQueriesContext(connection) as miss:
        first = client.get(FACETS_URL).json()
    with CaptureQueriesContext(connection) as hit:
        second = client.get(FACETS_URL).json()

    assert first == second
    assert len(hit.captured_queries) < len(miss.captured_queries)
    assert len(hit.captured_queries) <= 3  # cache-hit не пересобирает фасеты


@pytest.mark.django_db
def test_write_invalidates_cache(client, leaf, settings):
    """Создание товара (post_save) bump-ит версию кэша → следующий запрос отдаёт свежее."""
    settings.FACETS_CACHE_TTL = 300
    _product(leaf, "p1", "100")
    assert client.get(FACETS_URL).json()["total_products"] == 1  # закэшировано

    _product(leaf, "p2", "200")  # версионная инвалидация
    assert client.get(FACETS_URL).json()["total_products"] == 2  # свежие данные


@pytest.mark.django_db
def test_disabled_by_default_always_fresh(client, leaf, settings):
    """По умолчанию (TTL=0, dev/CI) кэш выключен — каждый запрос пересобирается."""
    assert settings.FACETS_CACHE_TTL == 0
    _product(leaf, "p1", "100")
    assert client.get(FACETS_URL).json()["total_products"] == 1
    _product(leaf, "p2", "200")
    assert client.get(FACETS_URL).json()["total_products"] == 2
