"""DEPRECATED совместимый слой.

Логика разнесена по модулям: `parsers`, `normalizers`, `matching`,
`product_writer`, `pricing`, `stock`, `use_cases`. Этот модуль оставлен для
обратной совместимости — существующий код/тесты импортируют
`apps.sync_1c.importer` напрямую. Новый код должен использовать `use_cases`.
"""

from __future__ import annotations

from apps.catalog.models import Product

from . import normalizers, pricing, stock, use_cases
from .models import SyncLog
from .use_cases import ImportResult

__all__ = [
    "ImportResult",
    "import_item",
    "import_items",
    "run_import",
    "update_price",
    "update_stock",
]


def import_item(
    item: dict,
    *,
    allow_basic_fields: bool = True,
    sync_log: SyncLog | None = None,
    source_file: str = "",
    create_missing: bool = True,
) -> tuple[Product | None, str]:
    """Импортировать один элемент. Вернуть (product|None, действие)."""
    product, action, _ = use_cases.process_row(
        item,
        sync_log=sync_log,
        source_file=source_file,
        create_missing=create_missing,
        allow_basic_fields=allow_basic_fields,
    )
    return product, action


def import_items(
    items: list[dict],
    *,
    allow_basic_fields: bool = True,
    sync_log: SyncLog | None = None,
    source_file: str = "",
    create_missing: bool = True,
) -> ImportResult:
    """Импортировать пакет элементов (без создания собственного SyncLog)."""
    return use_cases.run_rows(
        items,
        sync_log=sync_log,
        source_file=source_file,
        create_missing=create_missing,
        allow_basic_fields=allow_basic_fields,
    )


def run_import(
    items: list[dict],
    *,
    sync_type: str = SyncLog.SyncType.FULL,
    source_file: str = "",
    allow_basic_fields: bool = True,
    create_missing: bool = True,
) -> tuple[SyncLog, ImportResult]:
    """Прогон импорта: создать SyncLog, импортировать, связать строки."""
    return use_cases.import_products(
        items,
        source_file=source_file,
        create_missing=create_missing,
        allow_basic_fields=allow_basic_fields,
        sync_type=sync_type,
    )


def update_price(item: dict) -> bool:
    """Обновить только цену найденного товара (find-first)."""
    return pricing.update_price(normalizers.normalize_item(item))


def update_stock(item: dict) -> bool:
    """Обновить только остаток найденного товара (find-first)."""
    return stock.update_stock(normalizers.normalize_item(item))
