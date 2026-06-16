"""API для 1С 7.7 (1С сама стучится к сайту).

Эндпоинты:
  POST /api/1c/products/import   — первичная/массовая загрузка номенклатуры
  POST /api/1c/products/update   — обновление базовых полей (без категорий/SEO)
  POST /api/1c/prices/update     — обновление цен
  POST /api/1c/stocks/update     — обновление остатков
  GET  /api/1c/orders/new        — забор новых заказов (заглушка, M4)
  POST /api/1c/orders/confirm    — подтверждение заказа из 1С (заглушка, M4)

Авторизация — заголовок X-Api-Key (см. permissions.HasOneCApiKey).
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .. import tasks, use_cases
from ..models import SyncLog
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
    tasks.import_products_task.delay(sync_log.id, raw_items, create_missing)
    return Response(
        {"batch_uid": str(sync_log.batch_uid), "status": "accepted", "accepted": len(raw_items)},
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
def products_import(request):
    """Создать/обновить товары (создание разрешено). Тяжёлая операция → в фон."""
    _items, error = _validate_items(request, ProductImportItemSerializer)
    if error:
        return error
    return _enqueue_import(request, source_file="api:products/import", create_missing=True)


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
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
def prices_update(request):
    items, error = _validate_items(request, PriceItemSerializer)
    if error:
        return error
    sync_log, result = use_cases.update_prices(items, source_file="api:prices/update")
    return _import_response(sync_log, result)


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
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
