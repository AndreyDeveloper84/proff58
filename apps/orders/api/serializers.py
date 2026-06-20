"""Сериализаторы API заказов и корзины.

Снимки заказа отдаются read-only. Цена НИКОГДА не принимается из тела запроса —
для заказа используется серверный расчёт (см. services.place_order).
"""

from __future__ import annotations

from rest_framework import serializers

from ..models import Order, OrderItem


def _money(value):
    """Decimal → строка (как DRF рендерит DecimalField), либо None."""
    return None if value is None else str(value)


# ---------------------------------------------------------------------------
# Корзина (вывод собирается из services.CartView)
# ---------------------------------------------------------------------------
class CartLineSerializer(serializers.Serializer):
    """Строка корзины с актуальной серверной ценой."""

    id = serializers.IntegerField(source="item.id")
    product_id = serializers.IntegerField(source="product.id")
    name = serializers.CharField(source="product.name")
    slug = serializers.CharField(source="product.slug")
    quantity = serializers.IntegerField()
    price_final = serializers.SerializerMethodField()
    price_base = serializers.SerializerMethodField()
    discount = serializers.SerializerMethodField()
    price_type = serializers.CharField()
    currency = serializers.CharField()
    line_total = serializers.SerializerMethodField()

    def get_price_final(self, obj):
        return _money(obj.price_final)

    def get_price_base(self, obj):
        return _money(obj.price_base)

    def get_discount(self, obj):
        return _money(obj.discount)

    def get_line_total(self, obj):
        return _money(obj.line_total)


class CartViewSerializer(serializers.Serializer):
    """Корзина целиком: строки + итог."""

    id = serializers.IntegerField(source="cart.id")
    status = serializers.CharField(source="cart.status")
    lines = CartLineSerializer(many=True)
    total = serializers.SerializerMethodField()
    currency = serializers.CharField()

    def get_total(self, obj):
        return _money(obj.total)


# --- Запись в корзину (тело запросов) ---
class AddCartItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


# ---------------------------------------------------------------------------
# Заказ (read-only снимки)
# ---------------------------------------------------------------------------
class OrderItemSerializer(serializers.ModelSerializer):
    price_base = serializers.SerializerMethodField()
    price_final = serializers.SerializerMethodField()
    discount = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "product_id",
            "code_1c",
            "article",
            "name",
            "unit",
            "price_base",
            "price_final",
            "discount",
            "price_type",
            "currency",
            "quantity",
            "line_total",
        )
        read_only_fields = fields

    def get_price_base(self, obj):
        return _money(obj.price_base)

    def get_price_final(self, obj):
        return _money(obj.price_final)

    def get_discount(self, obj):
        return _money(obj.discount)

    def get_line_total(self, obj):
        return _money(obj.line_total)


class OrderSerializer(serializers.ModelSerializer):
    """Снимок заказа для вывода (read-only)."""

    items = OrderItemSerializer(many=True, read_only=True)
    display_status = serializers.CharField(read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "external_order_id",
            "fulfillment_status",
            "payment_status",
            "sync_1c_status",
            "display_status",
            "customer_name",
            "customer_phone",
            "customer_email",
            "customer_type",
            "company_name",
            "inn",
            "kpp",
            "legal_address",
            "delivery_method",
            "delivery_address",
            "comment",
            "payment_method",
            "total",
            "currency",
            "created_at",
            "items",
        )
        read_only_fields = fields

    def get_total(self, obj):
        return _money(obj.total)


class CreateOrderSerializer(serializers.Serializer):
    """Тело POST /api/orders/.

    Любые price-поля в теле игнорируются: цена считается на сервере.
    """

    # Контактные данные (для гостя; у аутентифицированного добираются из учётки)
    customer_name = serializers.CharField(required=False, allow_blank=True, default="")
    customer_phone = serializers.CharField(required=False, allow_blank=True, default="")
    customer_email = serializers.EmailField(required=False, allow_blank=True, default="")
    customer_type = serializers.CharField(required=False, allow_blank=True, default="")

    # Реквизиты B2B (опционально; добираются из профиля)
    company_name = serializers.CharField(required=False, allow_blank=True, default="")
    inn = serializers.CharField(required=False, allow_blank=True, default="")
    kpp = serializers.CharField(required=False, allow_blank=True, default="")
    legal_address = serializers.CharField(required=False, allow_blank=True, default="")

    # Доставка / оплата
    delivery_method = serializers.CharField(required=False, allow_blank=True, default="")
    delivery_address = serializers.CharField(required=False, allow_blank=True, default="")
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    payment_method = serializers.CharField(required=False, allow_blank=True, default="")
