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

from .. import use_cases
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


def _import_response(sync_log, result):
    return Response(
        {**result.as_dict(), "batch_uid": str(sync_log.batch_uid)}, status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
def products_import(request):
    """Создать/обновить товары (создание разрешено). Авторазбор категорий."""
    items, error = _validate_items(request, ProductImportItemSerializer)
    if error:
        return error
    sync_log, result = use_cases.import_products(items, source_file="api:products/import")
    return _import_response(sync_log, result)


@api_view(["POST"])
@permission_classes([HasOneCApiKey])
def products_update(request):
    """Обновить базовые поля СУЩЕСТВУЮЩИХ товаров (новые не создаются)."""
    items, error = _validate_items(request, ProductImportItemSerializer)
    if error:
        return error
    sync_log, result = use_cases.update_products(items, source_file="api:products/update")
    return _import_response(sync_log, result)


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
