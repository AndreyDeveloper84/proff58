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

from .. import importer
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


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
def products_import(request):
    """Создать/обновить товары (создание разрешено). Авторазбор категорий."""
    items, error = _validate_items(request, ProductImportItemSerializer)
    if error:
        return error
    sync_log, result = importer.run_import(
        items, sync_type=SyncLog.SyncType.FULL, source_file="api:products/import"
    )
    return Response(
        {**result.as_dict(), "batch_uid": str(sync_log.batch_uid)}, status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
def products_update(request):
    """Обновить базовые поля существующих товаров (без создания нового контента)."""
    items, error = _validate_items(request, ProductImportItemSerializer)
    if error:
        return error
    sync_log, result = importer.run_import(
        items, sync_type=SyncLog.SyncType.FULL, source_file="api:products/update"
    )
    return Response(
        {**result.as_dict(), "batch_uid": str(sync_log.batch_uid)}, status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
def prices_update(request):
    items, error = _validate_items(request, PriceItemSerializer)
    if error:
        return error
    updated = sum(1 for item in items if importer.update_price(item))
    SyncLog.objects.create(
        sync_type=SyncLog.SyncType.PRICES,
        result=SyncLog.SyncResult.OK,
        rows_total=len(items),
        rows_ok=updated,
        rows_error=len(items) - updated,
    )
    return Response({"updated": updated, "not_found": len(items) - updated})


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
def stocks_update(request):
    items, error = _validate_items(request, StockItemSerializer)
    if error:
        return error
    updated = sum(1 for item in items if importer.update_stock(item))
    SyncLog.objects.create(
        sync_type=SyncLog.SyncType.STOCK,
        result=SyncLog.SyncResult.OK,
        rows_total=len(items),
        rows_ok=updated,
        rows_error=len(items) - updated,
    )
    return Response({"updated": updated, "not_found": len(items) - updated})


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
