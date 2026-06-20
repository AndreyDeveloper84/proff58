"""PR #125A: пакетный matching + предзагрузка правил категоризации.

Доказываем, что matching и категоризация больше НЕ делают запросов на каждую строку
(карты строятся 1–2 запросами, правила читаются один раз). Запись товара пока построчная —
это #125B, поэтому общий импорт здесь O(N) по запросам не проверяем.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.models import Category, CategoryMappingRule, MappingRuleType, Product
from apps.sync_1c import matching, normalizers, use_cases


def _items(n: int):
    return [
        normalizers.normalize_item({"external_id": f"c{i}", "sku": f"art{i}", "name": "X"})
        for i in range(n)
    ]


@pytest.mark.django_db
def test_build_match_maps_is_constant_queries():
    """Карты строятся ≤2 запросами независимо от размера батча; резолв — 0 запросов."""
    Product.objects.create(name="A", code_1c="c1", article="art1", slug="a")
    Product.objects.create(name="B", code_1c="c2", article="art2", slug="b")

    items = _items(50)
    with CaptureQueriesContext(connection) as ctx:
        maps = matching.build_match_maps(items)
    assert len(ctx.captured_queries) <= 2  # by_code + by_article, не зависит от 50 строк

    with CaptureQueriesContext(connection) as ctx2:
        for it in items:
            matching.resolve_in_memory(it, maps)
    assert len(ctx2.captured_queries) == 0  # резолв по картам не ходит в БД


@pytest.mark.django_db
def test_resolve_in_memory_matches_resolve_for_import():
    """Семантика in-memory совпадает с построчной: matched / conflict / new."""
    p = Product.objects.create(name="A", code_1c="c1", article="uniq", slug="a")
    Product.objects.create(name="D1", article="dup", slug="d1")
    Product.objects.create(name="D2", article="dup", slug="d2")
    maps = matching.build_match_maps(
        _items(0)
        + [
            normalizers.normalize_item({"external_id": "c1"}),
            normalizers.normalize_item({"sku": "dup"}),
            normalizers.normalize_item({"sku": "uniq"}),
            normalizers.normalize_item({"external_id": "new-1"}),
        ]
    )
    assert (
        matching.resolve_in_memory(normalizers.normalize_item({"external_id": "c1"}), maps).product
        == p
    )
    assert (
        matching.resolve_in_memory(normalizers.normalize_item({"sku": "dup"}), maps).status
        == matching.MatchStatus.CONFLICT
    )
    assert (
        matching.resolve_in_memory(normalizers.normalize_item({"sku": "uniq"}), maps).product == p
    )
    assert (
        matching.resolve_in_memory(
            normalizers.normalize_item({"external_id": "new-1"}), maps
        ).status
        == matching.MatchStatus.NEW
    )


@pytest.mark.django_db
def test_import_batch_no_per_row_matching_queries():
    """Импорт батча: правила читаются один раз, нет per-row COUNT по товарам."""
    root = Category.add_root(name="Электроинструмент", slug="ei")
    CategoryMappingRule.objects.create(
        rule_type=MappingRuleType.NAME_CONTAINS, pattern="дрель", target_category=root
    )
    rows = [{"external_id": f"x{i}", "name": f"Дрель {i}", "price": "100"} for i in range(20)]

    with CaptureQueriesContext(connection) as ctx:
        use_cases.import_products(rows)

    sqls = [q["sql"].lower() for q in ctx.captured_queries]
    rule_reads = [s for s in sqls if "categorymappingrule" in s]
    assert len(rule_reads) <= 1  # правила загружены один раз, не на строку
    count_reads = [s for s in sqls if "count(" in s and "catalog_product" in s]
    assert count_reads == []  # ушёл per-row .count() из matching


@pytest.mark.django_db
def test_in_batch_duplicate_code_updates_not_errors():
    """Два ряда с одним code_1c в одном батче: второй обновляет (как при запросе к БД)."""
    sync_log, result = use_cases.import_products(
        [
            {"external_id": "same", "name": "Дрель", "price": "100"},
            {"external_id": "same", "name": "Дрель", "price": "150"},
        ]
    )
    assert result.created == 1
    assert result.updated == 1
    assert result.errors == 0
    assert Product.objects.filter(code_1c="same").count() == 1
