"""stock_qty в каталог-API (#488): сигнал «мало осталось» без утечки больших остатков."""

from __future__ import annotations

from decimal import Decimal

from django.test import override_settings

from apps.catalog.api.serializers import ProductListSerializer
from apps.catalog.models import Product, StockStatus


def _qty(stock_status, available):
    p = Product(stock_status=stock_status, available_quantity=Decimal(str(available)))
    return ProductListSerializer().get_stock_qty(p)


@override_settings(CATALOG_LOW_STOCK_THRESHOLD=5)
def test_stock_qty_low_returns_number():
    assert _qty(StockStatus.IN_STOCK, "3") == 3
    assert _qty(StockStatus.IN_STOCK, "5") == 5  # ровно порог


@override_settings(CATALOG_LOW_STOCK_THRESHOLD=5)
def test_stock_qty_high_is_hidden():
    assert _qty(StockStatus.IN_STOCK, "50") is None  # выше порога — не раскрываем


@override_settings(CATALOG_LOW_STOCK_THRESHOLD=5)
def test_stock_qty_zero_or_not_in_stock_is_none():
    assert _qty(StockStatus.IN_STOCK, "0") is None
    assert _qty(StockStatus.OUT_OF_STOCK, "3") is None
