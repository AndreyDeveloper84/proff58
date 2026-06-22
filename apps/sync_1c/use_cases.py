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
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalog import categorization
from apps.catalog.models import Product
from apps.core.events import EventSource, order_status_changed, price_changed
from apps.orders.models import (
    FulfillmentStatus,
    Order,
    PaymentStatus,
    Sync1CStatus,
)
from apps.orders.transitions import can_transition

from . import bulk_import, matching, normalizers, pricing, product_writer, stock
from .matching import MatchMaps, MatchStatus
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


def _tally_error(result: ImportResult, error_lines: list[str], ident: str, reason: str) -> None:
    """Учесть ошибку строки (для пакетного пути)."""
    result.errors += 1
    _append_error_detail(error_lines, ident, reason)


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
    maps: MatchMaps | None = None,
    rules: list | None = None,
) -> tuple[Product | None, str, NomenclatureStaging]:
    """Обработать одну строку. Вернуть (product|None, действие, staging).

    Действие: created / updated / skipped / conflict / error.

    ``maps``/``rules`` — предзагруженные карты товаров и правила категоризации
    (пакетный путь, #125A): matching и категоризация идут без per-row запросов.
    Если не переданы (одиночный путь `importer`) — работаем как раньше.
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

    # 3. matching — по картам (батч) либо запросом (одиночный путь).
    match = (
        matching.resolve_in_memory(item, maps)
        if maps is not None
        else matching.resolve_for_import(item)
    )
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
                product, categorized = product_writer.create_product(item, rules=rules)
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

    # Учесть новый товар в картах — чтобы дубль в этом же батче нашёлся (как при запросе к БД).
    if action == "created" and maps is not None:
        maps.register(product)

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
    sync_log.counters = result.as_dict()
    sync_log.result = SyncLog.SyncResult.OK if result.errors == 0 else SyncLog.SyncResult.PARTIAL
    if error_lines:
        sync_log.error_details = "\n".join(error_lines)
    sync_log.finished_at = timezone.now()
    sync_log.save()


# --- Состояние прогона (для статус-эндпоинта и фоновых задач) ---

_ZERO_COUNTERS = {"created": 0, "updated": 0, "skipped": 0, "uncategorized": 0, "errors": 0}


def is_finished(sync_log: SyncLog) -> bool:
    """Прогон завершён (любой статус, кроме RUNNING)."""
    return sync_log.result != SyncLog.SyncResult.RUNNING


def result_counters(sync_log: SyncLog) -> dict:
    """Счётчики прогона с гарантированным набором ключей (даже пока RUNNING)."""
    return {**_ZERO_COUNTERS, **(sync_log.counters or {})}


def new_import_job(*, source_file: str, sync_type: str = SyncLog.SyncType.FULL) -> SyncLog:
    """Создать прогон со статусом RUNNING (без обработки) — для async-постановки."""
    return SyncLog.objects.create(
        sync_type=sync_type, source_file=source_file, result=SyncLog.SyncResult.RUNNING
    )


def fail_import_job(sync_log: SyncLog, reason: str, *, rows_total: int = 0) -> None:
    """Пометить прогон жёстко упавшим (сбой задачи целиком, не per-row)."""
    n = sync_log.rows_total or rows_total
    sync_log.rows_total = n
    sync_log.rows_error = n
    sync_log.counters = {**_ZERO_COUNTERS, "errors": n}
    sync_log.result = SyncLog.SyncResult.ERROR
    old = (sync_log.error_details or "").strip()
    sync_log.error_details = f"{old}\n{reason}".strip()
    sync_log.finished_at = timezone.now()
    sync_log.save()


def mark_stale_imports() -> tuple[int, list[str]]:
    """Пометить зависшие RUNNING-прогоны как ERROR.

    Зависший = result=RUNNING, finished_at IS NULL, started_at старше SYNC_STALE_TIMEOUT.
    Идемпотентно: уже финализированные не трогаются (фильтр по RUNNING).
    """
    threshold = timezone.now() - timedelta(seconds=settings.SYNC_STALE_TIMEOUT)
    stale = SyncLog.objects.filter(
        result=SyncLog.SyncResult.RUNNING,
        finished_at__isnull=True,
        started_at__lt=threshold,
    )
    uids: list[str] = []
    for sync_log in stale:
        sync_log.result = SyncLog.SyncResult.ERROR
        sync_log.finished_at = timezone.now()
        note = f"Прогон отмечен зависшим (нет финализации за {settings.SYNC_STALE_TIMEOUT}s)."
        sync_log.error_details = ((sync_log.error_details or "").strip() + "\n" + note).strip()
        sync_log.save(update_fields=["result", "finished_at", "error_details"])
        uids.append(str(sync_log.batch_uid))
    return len(uids), uids


def run_import_into(
    sync_log: SyncLog,
    raw_items: list[dict],
    *,
    create_missing: bool = True,
    allow_basic_fields: bool = True,
) -> ImportResult:
    """Выполнить импорт в УЖЕ созданный прогон (sync_log) и финализировать его."""
    error_lines: list[str] = []
    result = run_rows(
        raw_items,
        sync_log=sync_log,
        source_file=sync_log.source_file,
        create_missing=create_missing,
        allow_basic_fields=allow_basic_fields,
        error_lines=error_lines,
    )
    _finalize(sync_log, result, error_lines)
    return result


def _build_maps(raw_items: list[dict]) -> MatchMaps:
    """Карты существующих товаров для батча. Нормализация чистая (без запросов к БД),
    поэтому строится 1–2 запросами вместо запроса на строку."""
    items = []
    for raw in raw_items:
        try:
            items.append(normalizers.normalize_item(raw))
        except Exception:  # noqa: BLE001
            continue  # битую строку обработает process_row (запишет ошибку в staging)
    return matching.build_match_maps(items)


def run_rows(
    raw_items: list[dict],
    *,
    sync_log: SyncLog | None = None,
    source_file: str = "",
    create_missing: bool = True,
    allow_basic_fields: bool = True,
    error_lines: list[str] | None = None,
) -> ImportResult:
    """Прогнать строки и собрать ImportResult (без finalize).

    Пакетный путь (#125B): классификация в памяти → bulk_create/bulk_update. При
    неожиданном сбое bulk-транзакции — откат на построчный путь (`_run_rows_per_row`,
    per-row savepoints), чтобы «одна плохая строка не валила батч».
    """
    lines = error_lines if error_lines is not None else []
    result = ImportResult()
    ok = bulk_import.run_rows_bulk(
        raw_items,
        sync_log=sync_log,
        source_file=source_file,
        create_missing=create_missing,
        allow_basic_fields=allow_basic_fields,
        error_lines=lines,
        result=result,
        tally_error=_tally_error,
    )
    if ok:
        return result
    # bulk-транзакция упала — построчный fallback на свежих счётчиках.
    lines.clear()
    return _run_rows_per_row(
        raw_items,
        sync_log=sync_log,
        source_file=source_file,
        create_missing=create_missing,
        allow_basic_fields=allow_basic_fields,
        error_lines=lines,
    )


def _run_rows_per_row(
    raw_items: list[dict],
    *,
    sync_log: SyncLog | None = None,
    source_file: str = "",
    create_missing: bool = True,
    allow_basic_fields: bool = True,
    error_lines: list[str] | None = None,
) -> ImportResult:
    """Построчный путь (fallback и одиночный importer): карты/правила один раз (#125A),
    запись товара построчно (per-row savepoint)."""
    result = ImportResult()
    lines = error_lines if error_lines is not None else []
    maps = _build_maps(raw_items)
    rules = categorization.load_active_rules()
    for raw in raw_items:
        product, action, staging = process_row(
            raw,
            sync_log=sync_log,
            source_file=source_file,
            create_missing=create_missing,
            allow_basic_fields=allow_basic_fields,
            maps=maps,
            rules=rules,
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
    sync_log = new_import_job(source_file=source_file, sync_type=sync_type)
    result = run_import_into(
        sync_log,
        raw_items,
        create_missing=create_missing,
        allow_basic_fields=allow_basic_fields,
    )
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
    maps = _build_maps(raw_items)
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
        match = matching.resolve_in_memory(item, maps)
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


def _apply_price(product: Product, item) -> bool:
    """set_current_price + издатель price_changed при фактическом изменении цены.

    Эмит из use-case (не из post_save), payload — идентификаторы/снимок, через
    transaction.on_commit (подписчик читает закоммиченные данные). См. events.py.
    """
    old_price = product.price
    applied = pricing.set_current_price(product, item)
    if applied and old_price != product.price:
        new_price, currency = product.price, product.currency
        transaction.on_commit(
            lambda p=product, o=old_price, n=new_price, c=currency: price_changed.send(
                sender=None,
                product_id=p.pk,
                old_price=o,
                new_price=n,
                currency=c,
                source=EventSource.ONE_C,
            )
        )
    return applied


def update_prices(raw_items: list[dict], *, source_file: str = "") -> tuple[SyncLog, ImportResult]:
    return _update_values(
        raw_items,
        apply=_apply_price,
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


def update_stocks_bulk(
    raw_items: list[dict], *, source_file: str = "", chunk: int = 2000
) -> tuple[SyncLog, ImportResult]:
    """Bulk-заливка остатков для больших выгрузок (низкая память, пачками).

    В отличие от ``update_stocks`` (построчный ``save()`` в транзакции на строку —
    тяжело и по памяти, и по числу запросов на десятках тысяч строк), грузит товары
    по ``code_1c`` ЧАНКАМИ и пишет остаток через ``stock.plan_stock`` (мутация полей
    без сохранения) + ``Product.bulk_update`` + ``stock.apply_stock_bulk``. Матчинг —
    только по ``code_1c`` (выгрузка 1С его всегда несёт); строки без ``code_1c`` или
    не найденные в БД — ``skipped``.
    """
    sync_log = SyncLog.objects.create(
        sync_type=SyncLog.SyncType.STOCK,
        source_file=source_file,
        result=SyncLog.SyncResult.RUNNING,
    )
    result = ImportResult()
    error_lines: list[str] = []

    # Нормализуем и индексируем по code_1c (last-wins при дублях) — Item'ы лёгкие.
    by_code: dict[str, normalizers.Item] = {}
    for raw in raw_items:
        try:
            item = normalizers.normalize_item(raw)
        except Exception:  # noqa: BLE001
            result.errors += 1
            _append_error_detail(error_lines, "—", "ошибка нормализации")
            continue
        if not item.code_1c:
            result.errors += 1
            _append_error_detail(error_lines, item.article or "—", "нет code_1c")
            continue
        by_code[item.code_1c] = item

    codes = list(by_code)
    try:
        for start in range(0, len(codes), chunk):
            part = codes[start : start + chunk]
            products = list(Product.objects.filter(code_1c__in=part))
            result.skipped += len(part) - len(products)  # не найдены по code_1c
            plans, to_update = [], []
            for product in products:
                plan = stock.plan_stock(product, by_code[product.code_1c])
                if plan is None:
                    result.skipped += 1  # нет полей остатка в строке
                    continue
                plans.append(plan)
                to_update.append(product)
                result.updated += 1
            with transaction.atomic():
                if to_update:
                    Product.objects.bulk_update(to_update, stock._STOCK_FIELDS, batch_size=1000)
                stock.apply_stock_bulk(plans)
    except Exception:  # noqa: BLE001
        result.errors += 1
        _append_error_detail(error_lines, "—", _short_traceback())
        _finalize(sync_log, result, error_lines)
        raise

    _finalize(sync_log, result, error_lines)
    return sync_log, result


# ---------------------------------------------------------------------------
# Заказы (#50): выгрузка в 1С и приём статусов
#
# Граница 1С живёт здесь (sync_1c импортирует apps.orders.models). Обе операции
# синхронные; журнал — SyncLog(sync_type=ORDERS). Контракт — docs/1c-api-spec.md
# §5.6, оси статусов — docs/order-lifecycle.md.
# ---------------------------------------------------------------------------


def _new_orders_sync_log() -> SyncLog:
    """Прогон ORDERS со статусом RUNNING (финализируется по итогам обработки)."""
    return SyncLog.objects.create(
        sync_type=SyncLog.SyncType.ORDERS,
        source_file="api:orders",
        result=SyncLog.SyncResult.RUNNING,
    )


def _decimal_str(value) -> str:
    """Decimal/число → строка (для JSON-ответа 1С). None → "0.00" не подставляем
    здесь — вызывающий сам решает дефолт."""
    return str(value)


def _serialize_order_for_export(order: Order) -> dict:
    """Сериализовать заказ по контракту §5.6 (GET /orders/new).

    Берём СНИМОК строк (OrderItem), а не живой товар: цена/название не «плывут».
    Доставки как суммы у Order нет (вне scope #50) → cost/delivery_total = "0.00".
    Все Decimal → str.
    """
    items = []
    for line_id, item in enumerate(order.items.all(), start=1):
        items.append(
            {
                "line_id": line_id,
                "external_id": item.code_1c,
                "sku": item.article,
                "name": item.name,
                "unit": item.unit,
                "quantity": str(item.quantity),
                "price": _decimal_str(item.price_final),
                "total": _decimal_str(item.line_total),
            }
        )
    return {
        "site_order_id": order.id,
        "order_number": order.order_number,
        "created_at": order.created_at.isoformat(),
        "fulfillment_status": order.fulfillment_status,
        "payment": {
            "method": order.payment_method,
            "status": order.payment_status,
        },
        "customer": {
            "type": order.customer_type,
            "name": order.customer_name,
            "phone": order.customer_phone,
            "email": order.customer_email,
        },
        "delivery": {
            "method": order.delivery_method,
            "address": order.delivery_address,
            "comment": order.comment,
            "cost": "0.00",
        },
        "totals": {
            "items_total": _decimal_str(order.total),
            "delivery_total": "0.00",
            "total": _decimal_str(order.total),
            "currency": order.currency,
        },
        "items": items,
    }


def export_new_orders(limit: int | None = None) -> tuple[SyncLog, list[dict]]:
    """Отдать новые заказы для 1С (GET /orders/new) и записать прогон.

    Выборка: sync_1c_status=pending, кроме отменённых (fulfillment=cancelled) и
    с истёкшей оплатой (payment=expired). payment=pending НЕ исключаем —
    B2B/наличные/онлайн-резерв ждут оплаты, но 1С их забирает.

    sync_1c_status НЕ меняем: at-least-once delivery — заказ остаётся pending и
    может быть выдан повторно, пока 1С не подтвердит приём через /orders/confirm.
    """
    if limit is None:
        limit = settings.ONEC_MAX_ITEMS

    orders = (
        Order.objects.filter(sync_1c_status=Sync1CStatus.PENDING)
        .exclude(fulfillment_status=FulfillmentStatus.CANCELLED)
        .exclude(payment_status=PaymentStatus.EXPIRED)
        .order_by("created_at", "id")
        .prefetch_related("items")[:limit]
    )
    orders = list(orders)
    items = [_serialize_order_for_export(order) for order in orders]

    sync_log = _new_orders_sync_log()
    n = len(items)
    sync_log.rows_total = n
    sync_log.rows_ok = n
    sync_log.rows_error = 0
    sync_log.counters = {"ok": n, "errors": 0}
    sync_log.result = SyncLog.SyncResult.OK
    sync_log.finished_at = timezone.now()
    sync_log.save()
    return sync_log, items


def _confirm_error(site_order_id, order_number, detail: str, order: Order | None = None) -> dict:
    """Сформировать per-item результат с ошибкой (НЕ исключение — иначе откат ack)."""
    return {
        "site_order_id": site_order_id if order is None else order.id,
        "order_number": order_number if order is None else order.order_number,
        "status": "error",
        "sync_1c_status": order.sync_1c_status if order is not None else None,
        "fulfillment_status": order.fulfillment_status if order is not None else None,
        "detail": detail,
    }


def _find_order_for_confirm(site_order_id, order_number) -> Order | None:
    """Найти заказ по site_order_id ИЛИ order_number (с блокировкой строки)."""
    qs = Order.objects.select_for_update()
    if site_order_id is not None:
        try:
            return qs.get(id=site_order_id)
        except Order.DoesNotExist:
            return None
    if order_number:
        try:
            return qs.get(order_number=order_number)
        except Order.DoesNotExist:
            return None
    return None


def _apply_sync_ack(order: Order, item: dict, reserve: dict | None) -> None:
    """sync-ack: применяется ВСЕГДА при наличии onec_order_id, независимо от
    оси обработки. Сохраняет связку с документом 1С, резерв, трек, и однократно
    проставляет exported/exported_at при первом подтверждении приёма."""
    order.external_order_id = item["onec_order_id"]
    if item.get("onec_order_number"):
        order.external_order_number = item["onec_order_number"]
    if reserve and reserve.get("ok") and reserve.get("reserved_until"):
        order.reserved_until = reserve["reserved_until"]
    if item.get("tracking"):
        order.tracking_number = item["tracking"]
    # pending→exported ставим ОДИН РАЗ; если уже exported — exported_at не трогаем.
    if order.sync_1c_status == Sync1CStatus.PENDING:
        order.sync_1c_status = Sync1CStatus.EXPORTED
        order.exported_at = timezone.now()


def _confirm_one(item: dict, error_lines: list[str]) -> dict:
    """Обработать одну строку confirm в собственной транзакции.

    Оси независимы: sync-ack фиксируется при наличии onec_order_id ДО любой
    проверки fulfillment, поэтому невалидный/недопустимый переход обработки НЕ
    откатывает подтверждение приёма (ack сохранён, ошибка — только per-item).
    """
    site_order_id = item.get("site_order_id")
    order_number = item.get("order_number")
    onec_order_id = item.get("onec_order_id")
    reserve = item.get("reserve")
    target_fulfillment = item.get("fulfillment_status")

    with transaction.atomic():
        order = _find_order_for_confirm(site_order_id, order_number)
        if order is None:
            detail = "Заказ не найден по site_order_id/order_number."
            _append_error_detail(error_lines, str(site_order_id or order_number or "—"), detail)
            return _confirm_error(site_order_id, order_number, detail)

        # Первичный ack без onec_order_id невозможен: нечем связать с документом 1С.
        if order.sync_1c_status == Sync1CStatus.PENDING and not onec_order_id:
            detail = "Для первичного подтверждения требуется onec_order_id."
            _append_error_detail(error_lines, order.order_number, detail)
            return _confirm_error(None, None, detail, order=order)

        # 1) sync-ack — независимая ось, применяется первой и не откатывается ниже.
        if onec_order_id:
            _apply_sync_ack(order, item, reserve)

        # 2) ось обработки (fulfillment) — отдельно от ack.
        fulfillment_error: str | None = None
        old_status = order.fulfillment_status
        reserve_failed = bool(reserve) and reserve.get("ok") is False

        if reserve_failed:
            # Провал резерва: обработка остаётся текущей, причину — в error_details.
            lines = reserve.get("lines")
            reason = f"Резерв не подтверждён 1С: {lines}" if lines else "Резерв не подтверждён 1С."
            _append_error_detail(error_lines, order.order_number, reason)
        elif target_fulfillment and target_fulfillment != old_status:
            if can_transition(old_status, target_fulfillment):
                order.fulfillment_status = target_fulfillment
                transaction.on_commit(
                    lambda oid=order.id, o=old_status, n=target_fulfillment: (
                        order_status_changed.send(
                            sender=Order, order_id=oid, old_status=o, new_status=n
                        )
                    )
                )
            else:
                fulfillment_error = (
                    f"Недопустимый переход обработки {old_status} → {target_fulfillment}."
                )
                _append_error_detail(error_lines, order.order_number, fulfillment_error)

        order.save()

        status = "error" if (fulfillment_error or reserve_failed) else "ok"
        detail = fulfillment_error or ("Резерв не подтверждён." if reserve_failed else "")
        return {
            "site_order_id": order.id,
            "order_number": order.order_number,
            "status": status,
            "sync_1c_status": order.sync_1c_status,
            "fulfillment_status": order.fulfillment_status,
            "detail": detail,
        }


def confirm_orders(items: list[dict]) -> tuple[SyncLog, list[dict]]:
    """Приём подтверждений 1С (POST /orders/confirm) и запись прогона.

    Каждая строка обрабатывается изолированно (своя transaction.atomic +
    select_for_update): одна плохая строка не валит батч. Ошибки — per-item
    результат, а не исключение.
    """
    sync_log = _new_orders_sync_log()
    error_lines: list[str] = []
    results: list[dict] = []
    ok = errors = 0

    for item in items:
        result = _confirm_one(item, error_lines)
        results.append(result)
        if result["status"] == "ok":
            ok += 1
        else:
            errors += 1

    sync_log.rows_total = len(items)
    sync_log.rows_ok = ok
    sync_log.rows_error = errors
    sync_log.counters = {"ok": ok, "errors": errors}
    if errors == 0:
        sync_log.result = SyncLog.SyncResult.OK
    elif ok == 0:
        sync_log.result = SyncLog.SyncResult.ERROR
    else:
        sync_log.result = SyncLog.SyncResult.PARTIAL
    if error_lines:
        sync_log.error_details = "\n".join(error_lines)
    sync_log.finished_at = timezone.now()
    sync_log.save()
    return sync_log, results
