"""Остатки: денормализация в Product + запись StockRecord по складу."""

from __future__ import annotations

from django.utils import timezone

from apps.catalog.models import Product

from . import matching
from .models import StockRecord
from .normalizers import Item

_STOCK_FIELDS = [
    "stock_quantity",
    "reserved_quantity",
    "available_quantity",
    "stock_status",
    "stock_updated_at",
]


def set_current_stock(product: Product, item: Item) -> bool:
    """Записать остаток в Product и StockRecord по складу. Не сохраняет Product."""
    if item.stock is None and item.reserved is None and item.available_stock is None:
        return False

    warehouse = item.warehouse or "main"

    if item.stock is not None:
        product.stock_quantity = item.stock
    if item.reserved is not None:
        product.reserved_quantity = item.reserved
    if item.available_stock is not None:
        product.available_quantity = item.available_stock
    elif item.stock is not None:
        product.available_quantity = item.stock - (item.reserved or product.reserved_quantity or 0)

    product.recalc_stock_status()
    product.stock_updated_at = timezone.now()

    if product.code_1c and item.stock is not None:
        StockRecord.objects.update_or_create(
            code_1c=product.code_1c,
            warehouse=warehouse,
            defaults={"product": product, "quantity": item.stock},
        )
    return True


def update_stock(item: Item) -> bool:
    """Точечно применить остаток к найденному товару (find-first). Используется shim'ом."""
    product = matching.find_product(item)
    if product is None:
        return False
    if not set_current_stock(product, item):
        return False
    product.save(update_fields=_STOCK_FIELDS)
    return True
