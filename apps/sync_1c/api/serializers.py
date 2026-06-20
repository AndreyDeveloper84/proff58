"""Сериализаторы входных данных от 1С.

Намеренно «мягкие»: 1С может присылать разный набор полей, поэтому
обязателен только идентификатор (external_id или sku). Остальное опционально
и валидируется по типам.
"""

from django.conf import settings
from rest_framework import serializers

from apps.orders.models import FulfillmentStatus


class _IdentifiedItem(serializers.Serializer):
    """Базовый элемент с идентификатором товара."""

    external_id = serializers.CharField(required=False, allow_blank=True)
    code_1c = serializers.CharField(required=False, allow_blank=True)
    sku = serializers.CharField(required=False, allow_blank=True)
    article = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not any(attrs.get(k) for k in ("external_id", "code_1c", "sku", "article")):
            raise serializers.ValidationError(
                "Нужен хотя бы один идентификатор: external_id / code_1c / sku / article."
            )
        return attrs


class ProductImportItemSerializer(_IdentifiedItem):
    name = serializers.CharField(required=False, allow_blank=True)
    brand = serializers.CharField(required=False, allow_blank=True)
    barcode = serializers.CharField(required=False, allow_blank=True)
    unit = serializers.CharField(required=False, allow_blank=True)
    source_group = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    price = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    old_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True
    )
    currency = serializers.CharField(required=False, allow_blank=True)
    price_type = serializers.CharField(required=False, allow_blank=True)
    stock = serializers.DecimalField(max_digits=14, decimal_places=3, required=False)


class PriceItemSerializer(_IdentifiedItem):
    price = serializers.DecimalField(max_digits=14, decimal_places=2)
    old_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True
    )
    currency = serializers.CharField(required=False, allow_blank=True)
    price_type = serializers.CharField(required=False, allow_blank=True)


class StockItemSerializer(_IdentifiedItem):
    stock = serializers.DecimalField(max_digits=14, decimal_places=3, required=False)
    reserved = serializers.DecimalField(max_digits=14, decimal_places=3, required=False)
    available_stock = serializers.DecimalField(max_digits=14, decimal_places=3, required=False)
    warehouse = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)  # идентификатор обязателен
        # is None, а не «truthy»: stock="0" (нулевой остаток) — валиден.
        if all(attrs.get(k) is None for k in ("stock", "reserved", "available_stock")):
            raise serializers.ValidationError(
                "Нужно хотя бы одно поле остатка: stock / reserved / available_stock."
            )
        return attrs


class OrderConfirmItemSerializer(serializers.Serializer):
    """Строка подтверждения заказа из 1С (POST /orders/confirm), контракт §5.6.

    1С присылает только ось обработки (`fulfillment_status`) и результат резерва;
    `payment_status`/`sync_1c_status` 1С не передаёт. Идентификатор заказа —
    `site_order_id` ИЛИ `order_number` (обязателен один).
    """

    site_order_id = serializers.IntegerField(required=False)
    order_number = serializers.CharField(required=False, allow_blank=True)
    onec_order_id = serializers.CharField(required=False, allow_blank=True)
    onec_order_number = serializers.CharField(required=False, allow_blank=True)
    tracking = serializers.CharField(required=False, allow_blank=True)
    comment = serializers.CharField(required=False, allow_blank=True)
    fulfillment_status = serializers.ChoiceField(choices=FulfillmentStatus.choices, required=False)
    reserve = serializers.JSONField(required=False)

    def validate(self, attrs):
        if attrs.get("site_order_id") is None and not attrs.get("order_number"):
            raise serializers.ValidationError(
                "Нужен идентификатор заказа: site_order_id или order_number."
            )
        return attrs


class ItemsEnvelopeSerializer(serializers.Serializer):
    """Конверт `{"items": [...]}`. item_serializer задаётся во вьюхе."""

    item_serializer_class = None

    def get_fields(self):
        fields = super().get_fields()
        fields["items"] = serializers.ListField(
            child=self.item_serializer_class(),
            allow_empty=False,
            max_length=settings.ONEC_MAX_ITEMS,
        )
        return fields


def envelope_for(item_cls):
    """Фабрика конверта под нужный тип элемента."""
    return type(
        f"{item_cls.__name__}Envelope",
        (ItemsEnvelopeSerializer,),
        {"item_serializer_class": item_cls},
    )
