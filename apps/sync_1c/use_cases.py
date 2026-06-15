"""Use-case слой импорта 1С: оркестрация поверх parsers/normalizers/matching/
product_writer/pricing/stock.

Здесь живут бизнес-операции, которые дёргают API, команда и Celery-задача:
  * import_products  — создание разрешено (create_missing=True);
  * update_products  — только обновление существующих (create_missing=False);
  * update_prices / update_stocks — точечные обновления с детекцией конфликтов.

Гарантии:
  * staging-строка создаётся из raw ДО нормализации и ВНЕ atomic записи товара —
    поэтому переживает любой сбой и хранит причину для расследования;
  * причины ошибок/конфликтов агрегируются в SyncLog.error_details (capped);
  * сбой одной строки не валит весь прогон (partial failure).
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product

from . import matching, normalizers, pricing, product_writer, stock
from .matching import MatchStatus
from .models import NomenclatureStaging, StagingStatus, SyncLog

_MAX_ERROR_LINES = 50


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    uncategorized: int = 0
    errors: int = 0

    @property
    def total(self) -> int:
        return self.created + self.updated + self.skipped + self.errors

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "uncategorized": self.uncategorized,
            "errors": self.errors,
        }


def _short_traceback() -> str:
    lines = traceback.format_exc().strip().splitlines()
    return (lines[-1] if lines else "Неизвестная ошибка")[:500]


def _append_error_detail(error_lines: list[str], ident: str, reason: str) -> None:
    if len(error_lines) < _MAX_ERROR_LINES:
        error_lines.append(f"{ident}: {reason}")


def _mark_error(staging: NomenclatureStaging, reason: str) -> None:
    staging.status = StagingStatus.ERROR
    staging.error_message = reason
    staging.processed_at = timezone.now()
    staging.save()


def process_row(
    raw: dict,
    *,
    sync_log: SyncLog | None,
    source_file: str,
    create_missing: bool,
    allow_basic_fields: bool,
) -> tuple[Product | None, str, NomenclatureStaging]:
    """Обработать одну строку. Вернуть (product|None, действие, staging).

    Действие: created / updated / skipped / conflict / error.
    """
    # 1. staging из raw — ДО нормализации и ВНЕ atomic записи товара.
    staging = NomenclatureStaging.objects.create(
        raw_payload=raw,
        row_hash=normalizers.row_hash(raw),
        sync_log=sync_log,
        source_file=source_file or (sync_log.source_file if sync_log else ""),
    )

    # 2. нормализация (её ошибки тоже не теряем).
    try:
        item = normalizers.normalize_item(raw)
    except Exception:  # noqa: BLE001
        _mark_error(staging, "Ошибка нормализации строки: " + _short_traceback())
        return None, "error", staging

    staging.code_1c = item.code_1c
    staging.article = item.article
    staging.name_1c = item.name
    staging.unit = item.unit
    staging.price = item.price
    staging.stock = item.stock
    staging.is_active_1c = item.is_active

    if not item.has_identifier:
        _mark_error(staging, "Нет идентификатора (code_1c / article).")
        return None, "error", staging

    # 3. matching.
    match = matching.resolve_for_import(item)
    if match.status == MatchStatus.CONFLICT:
        _mark_error(staging, match.reason)
        return None, "conflict", staging
    if match.status == MatchStatus.NEW and not create_missing:
        staging.status = StagingStatus.SKIPPED
        staging.processed_at = timezone.now()
        staging.save()
        return None, "skipped", staging

    # 4. запись товара — в savepoint; сбой не сносит staging.
    try:
        with transaction.atomic():
            if match.status == MatchStatus.NEW:
                product, categorized = product_writer.create_product(item)
                staging.status = StagingStatus.MATCHED if categorized else StagingStatus.NEW
                action = "created"
            else:
                product = match.product
                product_writer.update_existing(product, item, allow_basic_fields=allow_basic_fields)
                staging.status = StagingStatus.MATCHED
                action = "updated"
    except Exception:  # noqa: BLE001
        _mark_error(staging, _short_traceback())
        return None, "error", staging

    staging.product = product
    staging.processed_at = timezone.now()
    staging.save()
    return product, action, staging


def _tally(result: ImportResult, action: str, product, staging, error_lines: list[str]) -> None:
    if action == "created":
        result.created += 1
        if product is not None and product.category_id is None:
            result.uncategorized += 1
    elif action == "updated":
        result.updated += 1
    elif action == "skipped":
        result.skipped += 1
    else:  # conflict / error
        result.errors += 1
        ident = staging.code_1c or staging.article or "—"
        _append_error_detail(error_lines, ident, staging.error_message)


def _finalize(sync_log: SyncLog, result: ImportResult, error_lines: list[str]) -> None:
    sync_log.rows_total = result.total
    sync_log.rows_ok = result.created + result.updated + result.skipped
    sync_log.rows_error = result.errors
    sync_log.result = SyncLog.SyncResult.OK if result.errors == 0 else SyncLog.SyncResult.PARTIAL
    if error_lines:
        sync_log.error_details = "\n".join(error_lines)
    sync_log.finished_at = timezone.now()
    sync_log.save()


def run_rows(
    raw_items: list[dict],
    *,
    sync_log: SyncLog | None = None,
    source_file: str = "",
    create_missing: bool = True,
    allow_basic_fields: bool = True,
    error_lines: list[str] | None = None,
) -> ImportResult:
    """Прогнать строки через process_row и собрать ImportResult (без finalize)."""
    result = ImportResult()
    lines = error_lines if error_lines is not None else []
    for raw in raw_items:
        product, action, staging = process_row(
            raw,
            sync_log=sync_log,
            source_file=source_file,
            create_missing=create_missing,
            allow_basic_fields=allow_basic_fields,
        )
        _tally(result, action, product, staging, lines)
    return result


def import_products(
    raw_items: list[dict],
    *,
    source_file: str = "",
    create_missing: bool = True,
    allow_basic_fields: bool = True,
    sync_type: str = SyncLog.SyncType.FULL,
) -> tuple[SyncLog, ImportResult]:
    """Импорт/обновление товаров (создание разрешено по умолчанию)."""
    sync_log = SyncLog.objects.create(
        sync_type=sync_type, source_file=source_file, result=SyncLog.SyncResult.OK
    )
    error_lines: list[str] = []
    result = run_rows(
        raw_items,
        sync_log=sync_log,
        source_file=source_file,
        create_missing=create_missing,
        allow_basic_fields=allow_basic_fields,
        error_lines=error_lines,
    )
    _finalize(sync_log, result, error_lines)
    return sync_log, result


def update_products(raw_items: list[dict], **kwargs) -> tuple[SyncLog, ImportResult]:
    """Только обновление существующих товаров (новые не создаются)."""
    kwargs["create_missing"] = False
    return import_products(raw_items, **kwargs)


def _update_values(
    raw_items: list[dict],
    *,
    apply,
    sync_type: str,
    source_file: str,
) -> tuple[SyncLog, ImportResult]:
    """Конфликт-aware точечное обновление цены/остатка (без staging на каждую строку)."""
    sync_log = SyncLog.objects.create(
        sync_type=sync_type, source_file=source_file, result=SyncLog.SyncResult.OK
    )
    result = ImportResult()
    error_lines: list[str] = []
    for raw in raw_items:
        try:
            item = normalizers.normalize_item(raw)
        except Exception:  # noqa: BLE001
            result.errors += 1
            _append_error_detail(error_lines, "—", "ошибка нормализации")
            continue
        ident = item.code_1c or item.article or "—"
        if not item.has_identifier:
            result.errors += 1
            _append_error_detail(error_lines, ident, "нет идентификатора")
            continue
        match = matching.resolve_for_import(item)
        if match.status == MatchStatus.CONFLICT:
            result.errors += 1
            _append_error_detail(error_lines, ident, match.reason)
            continue
        if match.status == MatchStatus.NEW:
            result.skipped += 1
            continue
        try:
            with transaction.atomic():
                applied = apply(match.product, item)
                if applied:
                    match.product.save()
        except Exception:  # noqa: BLE001
            result.errors += 1
            _append_error_detail(error_lines, ident, _short_traceback())
            continue
        if applied:
            result.updated += 1
        else:
            result.skipped += 1  # в строке нет цены/остатка — нечего обновлять
    _finalize(sync_log, result, error_lines)
    return sync_log, result


def update_prices(raw_items: list[dict], *, source_file: str = "") -> tuple[SyncLog, ImportResult]:
    return _update_values(
        raw_items,
        apply=pricing.set_current_price,
        sync_type=SyncLog.SyncType.PRICES,
        source_file=source_file,
    )


def update_stocks(raw_items: list[dict], *, source_file: str = "") -> tuple[SyncLog, ImportResult]:
    return _update_values(
        raw_items,
        apply=stock.set_current_stock,
        sync_type=SyncLog.SyncType.STOCK,
        source_file=source_file,
    )
