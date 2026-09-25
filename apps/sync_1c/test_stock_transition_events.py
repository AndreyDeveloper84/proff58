"""Тесты продукции сигнала product_stock_became_available (#518, ADR-0010):
row-wise (update_stocks) и bulk (update_stocks_bulk) пути дают одинаковый
результат — эмит только на реальный переход 0→positive."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import transaction

from apps.catalog.models import Product
from apps.core.events import product_stock_became_available
from apps.sync_1c import use_cases


@pytest.fixture
def _capture():
    received: list[dict] = []

    def handler(sender, **kw):
        received.append(kw)

    product_stock_became_available.connect(handler)
    yield received
    product_stock_became_available.disconnect(handler)


def _product(**kwargs):
    defaults = dict(name="Т", slug=f"stk-{kwargs.get('code_1c', 'x')}")
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


# ═══════════════════════════════════════════════════════════════════════
# Row-wise (update_stocks)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_row_wise_zero_to_positive_emits(_capture, django_capture_on_commit_callbacks):
    _product(code_1c="rw-1", available_quantity=Decimal("0"))
    with django_capture_on_commit_callbacks(execute=True):
        use_cases.update_stocks([{"external_id": "rw-1", "available_stock": "5"}])
    assert len(_capture) == 1
    assert _capture[0]["product_id"]
    assert _capture[0]["old_available"] == "0"
    assert _capture[0]["new_available"] == "5"
    assert _capture[0]["source"] == "1c"
    assert _capture[0]["transition_id"]


@pytest.mark.django_db
def test_row_wise_positive_to_positive_does_not_emit(_capture, django_capture_on_commit_callbacks):
    _product(code_1c="rw-2", available_quantity=Decimal("3"))
    with django_capture_on_commit_callbacks(execute=True):
        use_cases.update_stocks([{"external_id": "rw-2", "available_stock": "8"}])
    assert _capture == []


@pytest.mark.django_db
def test_row_wise_zero_to_zero_does_not_emit(_capture, django_capture_on_commit_callbacks):
    _product(code_1c="rw-3", available_quantity=Decimal("0"))
    with django_capture_on_commit_callbacks(execute=True):
        use_cases.update_stocks([{"external_id": "rw-3", "available_stock": "0"}])
    assert _capture == []


@pytest.mark.django_db
def test_row_wise_repeated_positive_import_does_not_reemit(
    _capture, django_capture_on_commit_callbacks
):
    """Повторная выгрузка тех же (уже положительных) остатков не уведомляет —
    AC #518. Второй импорт видит old_available уже положительным."""
    _product(code_1c="rw-4", available_quantity=Decimal("0"))
    with django_capture_on_commit_callbacks(execute=True):
        use_cases.update_stocks([{"external_id": "rw-4", "available_stock": "5"}])
    assert len(_capture) == 1

    with django_capture_on_commit_callbacks(execute=True):
        use_cases.update_stocks([{"external_id": "rw-4", "available_stock": "5"}])
    assert len(_capture) == 1  # не выросло


@pytest.mark.django_db
def test_row_wise_transaction_rollback_discards_signal(_capture):
    """AC #518: откат транзакции не создаёт уведомление — on_commit callback,
    зарегистрированный внутри откатившегося atomic-блока, Django отбрасывает."""
    product = _product(code_1c="rw-5", available_quantity=Decimal("0"))
    from apps.sync_1c.normalizers import normalize_item

    item = normalize_item({"external_id": "rw-5", "available_stock": "5"})

    try:
        with transaction.atomic():
            use_cases._apply_stock(product, item)
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert _capture == []


# ═══════════════════════════════════════════════════════════════════════
# Bulk (update_stocks_bulk) — тот же контракт
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_bulk_zero_to_positive_emits(_capture, django_capture_on_commit_callbacks):
    _product(code_1c="bk-1", available_quantity=Decimal("0"))
    with django_capture_on_commit_callbacks(execute=True):
        # #518: как в реальном контракте 1С (§5.5 docs/1c-api-spec.md) — stock
        # идёт вместе с available_stock; plan_stock() пишет StockRecord только
        # когда есть raw stock (см. apps.sync_1c.stock.plan_stock).
        use_cases.update_stocks_bulk(
            [{"external_id": "bk-1", "stock": "5", "available_stock": "5"}]
        )
    assert len(_capture) == 1
    assert _capture[0]["old_available"] == "0"
    assert _capture[0]["new_available"] == "5"


@pytest.mark.django_db
def test_bulk_positive_to_positive_does_not_emit(_capture, django_capture_on_commit_callbacks):
    _product(code_1c="bk-2", available_quantity=Decimal("3"))
    with django_capture_on_commit_callbacks(execute=True):
        use_cases.update_stocks_bulk(
            [{"external_id": "bk-2", "stock": "8", "available_stock": "8"}]
        )
    assert _capture == []


@pytest.mark.django_db
def test_bulk_zero_to_zero_does_not_emit(_capture, django_capture_on_commit_callbacks):
    _product(code_1c="bk-3", available_quantity=Decimal("0"))
    with django_capture_on_commit_callbacks(execute=True):
        use_cases.update_stocks_bulk(
            [{"external_id": "bk-3", "stock": "0", "available_stock": "0"}]
        )
    assert _capture == []


@pytest.mark.django_db
def test_bulk_and_row_wise_give_same_result_for_same_transition(
    _capture, django_capture_on_commit_callbacks
):
    """AC #518: обычный и bulk import дают одинаковый результат."""
    _product(code_1c="cmp-row", available_quantity=Decimal("0"))
    _product(code_1c="cmp-bulk", available_quantity=Decimal("0"))

    with django_capture_on_commit_callbacks(execute=True):
        use_cases.update_stocks([{"external_id": "cmp-row", "stock": "5", "available_stock": "5"}])
    with django_capture_on_commit_callbacks(execute=True):
        use_cases.update_stocks_bulk(
            [{"external_id": "cmp-bulk", "stock": "5", "available_stock": "5"}]
        )

    assert len(_capture) == 2
    assert {c["old_available"] for c in _capture} == {"0"}
    assert {c["new_available"] for c in _capture} == {"5"}


@pytest.mark.django_db
def test_bulk_multi_chunk_transitions_all_emit(_capture, django_capture_on_commit_callbacks):
    """Переходы в разных чанках bulk-импорта эмитятся все, не только первый чанк."""
    for i in range(3):
        _product(code_1c=f"bk-chunk-{i}", available_quantity=Decimal("0"))
    items = [
        {"external_id": f"bk-chunk-{i}", "stock": "1", "available_stock": "1"} for i in range(3)
    ]

    with django_capture_on_commit_callbacks(execute=True):
        use_cases.update_stocks_bulk(items, chunk=1)  # заставляем 3 чанка по 1 товару

    assert len(_capture) == 3
