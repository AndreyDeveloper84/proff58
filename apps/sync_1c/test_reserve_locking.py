"""DRF-2737: обмен остатками действительно ждёт незакоммиченный чекаут.

Тесты `test_reserve_safety.py` имитируют гонку записью, которая коммитится до
свежего чтения, — они прошли бы и без замка строки. Здесь настоящая конкуренция:
второй поток держит открытую транзакцию чекаута (замок товара и удержание через
`F()`), а обмен в это время пишет остаток. Он обязан дождаться чекаута и посчитать
свободный остаток уже с его удержанием.

Тест транзакционный (нужны настоящие коммиты), поэтому он один и короткий.
"""

from __future__ import annotations

import threading
import time
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection, transaction
from django.db.models import F

from apps.catalog.models import Product, ProductStatus
from apps.sync_1c import bulk_import, use_cases

HOLD_SECONDS = 0.7


def _checkout_in_flight(pk: int) -> threading.Thread:
    """Чекаут в другом соединении: взял замок товара, удержал 2 штуки и ещё не закоммитил."""
    started = threading.Event()

    def run():
        try:
            with transaction.atomic():
                list(Product.objects.select_for_update().filter(pk=pk))
                Product.objects.filter(pk=pk).update(
                    available_quantity=F("available_quantity") - 2,
                    reserved_quantity=F("reserved_quantity") + 2,
                )
                started.set()
                time.sleep(HOLD_SECONDS)
        finally:
            connection.close()

    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(5), "чекаут во втором соединении не стартовал"
    return thread


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("path", ["stocks/update", "update_stocks_bulk", "import", "fallback"])
def test_stock_writers_wait_for_uncommitted_checkout(path):
    product = Product.objects.create(
        name="Перфоратор",
        code_1c="1c-lock",
        slug="perf-lock",
        price=Decimal("100.00"),
        status=ProductStatus.DRAFT,
        stock_quantity=Decimal("5"),
        available_quantity=Decimal("5"),
    )
    rows = [{"external_id": "1c-lock", "stock": "10", "name": "Перфоратор"}]
    checkout = _checkout_in_flight(product.pk)
    started_at = time.monotonic()
    try:
        if path == "stocks/update":
            use_cases.update_stocks(rows)
        elif path == "update_stocks_bulk":
            use_cases.update_stocks_bulk(rows)
        elif path == "import":
            use_cases.import_products(rows)
        else:
            with mock.patch.object(bulk_import, "run_rows_bulk", return_value=False):
                use_cases.import_products(rows)
        waited = time.monotonic() - started_at
    finally:
        checkout.join()

    product.refresh_from_db()
    assert waited >= HOLD_SECONDS * 0.6, "обмен не ждал чекаут — замка строки нет"
    assert product.reserved_quantity == Decimal("2")
    assert product.available_quantity == Decimal("8")  # 10 физически − 2 удержано
