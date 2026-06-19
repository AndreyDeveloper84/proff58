"""API для 1С 7.7 (1С сама стучится к сайту).

Эндпоинты:
  GET  /api/1c/snapshot/         — снимок актуальных позиций (1С забирает и сравнивает у себя)
  POST /api/1c/products/import   — первичная/массовая загрузка номенклатуры
  POST /api/1c/products/update   — обновление базовых полей (без категорий/SEO)
  POST /api/1c/prices/update     — обновление цен
  POST /api/1c/stocks/update     — обновление остатков
  GET  /api/1c/orders/new        — забор новых заказов (заглушка, M4)
  POST /api/1c/orders/confirm    — подтверждение заказа из 1С (заглушка, M4)

Авторизация — заголовок X-Api-Key (см. permissions.HasOneCApiKey).
"""

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.response import Response

from apps.catalog.models import Product

from .. import tasks, use_cases
from ..models import SyncLog
from .parsers import OneCJSONParser
from .permissions import HasOneCApiKey
from .serializers import (
    PriceItemSerializer,
    ProductImportItemSerializer,
    StockItemSerializer,
    envelope_for,
)


def _validate_items(request, item_cls):
    """Провалидировать конверт {"items": [...]} и вернуть (items, error_response)."""
    serializer = envelope_for(item_cls)(data=request.data)
    if not serializer.is_valid():
        return None, Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return serializer.validated_data["items"], None


def _raw_items_from_request(request) -> list:
    """Сырые items как прислала 1С (JSON-safe, без Decimal) — после валидации."""
    return list(request.data.get("items", []))


def _import_response(sync_log, result):
    return Response(
        {**result.as_dict(), "batch_uid": str(sync_log.batch_uid)}, status=status.HTTP_200_OK
    )


def _enqueue_import(request, *, source_file, create_missing):
    """Поставить тяжёлый импорт товаров в фон. Вернуть 202 + batch_uid."""
    sync_log = use_cases.new_import_job(source_file=source_file)
    raw_items = _raw_items_from_request(request)
    try:
        tasks.import_products_task.delay(sync_log.id, raw_items, create_missing)
    except Exception as exc:  # noqa: BLE001 — любой сбой брокера/сериализации
        # Техпричину — в лог, наружу 1С — без деталей брокера.
        use_cases.fail_import_job(
            sync_log, f"Не удалось поставить задачу в очередь: {exc}", rows_total=len(raw_items)
        )
        return Response(
            {
                "batch_uid": str(sync_log.batch_uid),
                "status": "error",
                "detail": "Не удалось поставить задачу импорта в очередь. Повторите запрос позже.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response(
        {"batch_uid": str(sync_log.batch_uid), "status": "accepted", "accepted": len(raw_items)},
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
@parser_classes([OneCJSONParser])
def products_import(request):
    """Создать/обновить товары (создание разрешено). Тяжёлая операция → в фон."""
    _items, error = _validate_items(request, ProductImportItemSerializer)
    if error:
        return error
    return _enqueue_import(request, source_file="api:products/import", create_missing=True)


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
@parser_classes([OneCJSONParser])
def products_update(request):
    """Обновить базовые поля СУЩЕСТВУЮЩИХ товаров (новые не создаются). В фон."""
    _items, error = _validate_items(request, ProductImportItemSerializer)
    if error:
        return error
    return _enqueue_import(request, source_file="api:products/update", create_missing=False)


@api_view(["GET"])
@permission_classes([HasOneCApiKey])
def sync_status(request, batch_uid):
    """Статус прогона импорта по batch_uid (1С опрашивает фоновую задачу)."""
    try:
        sync_log = SyncLog.objects.get(batch_uid=batch_uid)
    except SyncLog.DoesNotExist:
        return Response({"detail": "Прогон не найден."}, status=status.HTTP_404_NOT_FOUND)
    return Response(
        {
            "batch_uid": str(sync_log.batch_uid),
            "status": sync_log.result,
            "finished": use_cases.is_finished(sync_log),
            "rows_total": sync_log.rows_total,
            "rows_ok": sync_log.rows_ok,
            "rows_error": sync_log.rows_error,
            **use_cases.result_counters(sync_log),
            "finished_at": sync_log.finished_at,
            "error_details": sync_log.error_details,
        }
    )


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
@parser_classes([OneCJSONParser])
def prices_update(request):
    items, error = _validate_items(request, PriceItemSerializer)
    if error:
        return error
    sync_log, result = use_cases.update_prices(items, source_file="api:prices/update")
    return _import_response(sync_log, result)


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
@parser_classes([OneCJSONParser])
def stocks_update(request):
    items, error = _validate_items(request, StockItemSerializer)
    if error:
        return error
    sync_log, result = use_cases.update_stocks(items, source_file="api:stocks/update")
    return _import_response(sync_log, result)


# --- Заказы: контракт зафиксирован, реализация — в M4 (EPIC-CHECKOUT) ---

_ORDERS_PENDING = {
    "detail": "Модуль заказов будет реализован в M4 (EPIC-CHECKOUT). Контракт зафиксирован."
}


@api_view(["GET"])
@permission_classes([HasOneCApiKey])
def orders_new(_request):
    return Response(_ORDERS_PENDING, status=status.HTTP_501_NOT_IMPLEMENTED)


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
def orders_confirm(_request):
    return Response(_ORDERS_PENDING, status=status.HTTP_501_NOT_IMPLEMENTED)


# --- Снимок позиций: 1С забирает актуальные цены/остатки и сравнивает у себя ---


def _parse_int_param(raw, *, default):
    """Разобрать целочисленный query-параметр. Вернуть (value, error_detail)."""
    if raw is None or raw == "":
        return default, None
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, "Параметр должен быть целым числом."


def _decimal_to_str(value):
    return None if value is None else str(value)


@api_view(["GET"])
@permission_classes([HasOneCApiKey])
def snapshot(request):
    """Снимок актуальных позиций для 1С: code_1c + цена + остатки, постранично.

    1С забирает снимок, сравнивает у себя и шлёт обратно ТОЛЬКО изменения
    (price → prices/update, физический stock → stocks/update). reserved/available
    ведёт сайт, 1С их не присылает. В снимок попадают все позиции с code_1c
    (включая скрытые на витрине) — видимость на обмен не влияет.
    """
    max_items = settings.ONEC_MAX_ITEMS

    limit, error = _parse_int_param(request.query_params.get("limit"), default=max_items)
    if error:
        return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
    if limit <= 0:
        return Response(
            {"detail": "limit должен быть положительным числом."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    limit = min(limit, max_items)

    offset, error = _parse_int_param(request.query_params.get("offset"), default=0)
    if error:
        return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
    if offset < 0:
        return Response(
            {"detail": "offset не может быть отрицательным."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = Product.objects.exclude(code_1c__isnull=True).exclude(code_1c="").order_by("code_1c", "id")
    count = qs.count()
    rows = qs[offset : offset + limit].values(
        "code_1c",
        "price",
        "currency",
        "stock_quantity",
        "reserved_quantity",
        "available_quantity",
    )

    results = [
        {
            "code_1c": row["code_1c"],
            "price": _decimal_to_str(row["price"]),
            "currency": row["currency"] or "RUB",
            "stock": _decimal_to_str(row["stock_quantity"]),
            "reserved": _decimal_to_str(row["reserved_quantity"]),
            "available": _decimal_to_str(row["available_quantity"]),
        }
        for row in rows
    ]

    next_offset = offset + limit if offset + limit < count else None

    return Response(
        {
            "count": count,
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset,
            "results": results,
        }
    )
