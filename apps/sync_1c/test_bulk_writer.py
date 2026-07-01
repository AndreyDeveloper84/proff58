"""PR #125B: пакетная запись (bulk_create/bulk_update) и события только при изменениях."""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.utils import IntegrityError
from django.test.utils import CaptureQueriesContext
from unittest.mock import patch

from apps.catalog.models import Product
from apps.core.events import product_updated
from apps.pricing.models import PriceRecord
from apps.sync_1c import bulk_import, use_cases
from apps.sync_1c.models import NomenclatureStaging, StockRecord, StagingStatus
from apps.sync_1c.use_cases import ImportResult, _tally_error


@pytest.mark.django_db
def test_import_batch_is_bulk_not_per_row():
    """Импорт N новых строк = пачки запросов, не O(N) (число запросов почти не растёт с N)."""
    rows = [
        {"external_id": f"b{i}", "name": f"Товар {i}", "price": "100", "stock": "5"}
        for i in range(50)
    ]
    with CaptureQueriesContext(connection) as ctx:
        use_cases.import_products(rows)
    # O(N) на 50 строках дало бы ~500 запросов; bulk укладывается в десятки.
    assert len(ctx.captured_queries) < 30
    assert Product.objects.count() == 50
    assert PriceRecord.objects.filter(is_current=True).count() == 50
    assert StockRecord.objects.count() == 50


@pytest.mark.django_db
def test_reimport_unchanged_emits_no_product_updated(django_capture_on_commit_callbacks):
    """Повторный импорт без изменений полей → product_updated НЕ эмитится (не шумим)."""
    use_cases.import_products(
        [{"external_id": "u1", "name": "Дрель", "price": "100", "stock": "3"}]
    )

    received = []
    product_updated.connect(lambda **kw: received.append(kw), weak=False)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            _, result = use_cases.import_products(
                [{"external_id": "u1", "name": "Дрель", "price": "100", "stock": "3"}]
            )
    finally:
        product_updated.disconnect(None)

    assert result.updated == 1  # строка matched (как и раньше)
    assert received == []  # но события нет — поля не изменились
    assert PriceRecord.objects.filter(code_1c="u1", is_current=True).count() == 1  # не плодим цены


@pytest.mark.django_db
def test_reimport_changed_price_flips_current_and_emits(django_capture_on_commit_callbacks):
    """Изменение цены при реимпорте: ровно одна актуальная PriceRecord, событие есть."""
    use_cases.import_products([{"external_id": "p1", "name": "Дрель", "price": "100"}])

    received = []
    product_updated.connect(lambda **kw: received.append(kw), weak=False)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            use_cases.import_products([{"external_id": "p1", "name": "Дрель", "price": "150"}])
    finally:
        product_updated.disconnect(None)

    assert PriceRecord.objects.filter(code_1c="p1", is_current=True).count() == 1
    assert PriceRecord.objects.get(code_1c="p1", is_current=True).value == 150
    assert PriceRecord.objects.filter(code_1c="p1").count() == 2  # история сохранена
    assert len(received) == 1
    assert "price" in received[0]["changed_fields"]


@pytest.mark.django_db
def test_staging_saved_before_product_transaction():
    """Инвариант #131: raw staging сохраняется ДО записи товаров.

    Если product-транзакция падает (имитируем через patch), staging-записи уже в БД.
    """
    rows = [{"external_id": "s131", "name": "Тест инварианта #131", "price": "500"}]

    # Имитируем падение bulk-транзакции записи товаров
    with patch.object(bulk_import, "_update_staging", side_effect=IntegrityError("mock")):
        ok = bulk_import.run_rows_bulk(
            rows,
            sync_log=None,
            source_file="test",
            create_missing=True,
            allow_basic_fields=True,
            error_lines=[],
            result=ImportResult(),
            tally_error=_tally_error,
        )

    # bulk упал → fallback-сигнал
    assert ok is False
    # Staging уже был сохранён ДО падения product-транзакции (инвариант #131)
    assert NomenclatureStaging.objects.filter(source_file="test").exists()
    staging = NomenclatureStaging.objects.get(source_file="test")
    assert staging.raw_payload == rows[0]
    # Статус остался PENDING (product-транзакция не дошла до bulk_update)
    assert staging.status == StagingStatus.PENDING
