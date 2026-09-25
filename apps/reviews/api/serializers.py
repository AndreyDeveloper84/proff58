"""Сериализаторы отзывов (#573). Публичный — БЕЗ ПДн (только снапшот имени)."""

from __future__ import annotations

from rest_framework import serializers

from ..models import Review


class PublicReviewSerializer(serializers.ModelSerializer):
    """Витрина: только то, что можно показывать всем. Оценки доставки/магазина
    публично не отдаём — они про заказ, а не про товар на PDP."""

    class Meta:
        model = Review
        fields = ("author_name", "product_rating", "text", "created_at")
        read_only_fields = fields


class MyReviewSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Review
        fields = (
            "id",
            "order_number",
            "product_rating",
            "delivery_rating",
            "shop_rating",
            "text",
            "status",
            "status_display",
            "rejection_reason",
            "created_at",
        )
        read_only_fields = fields


class MyReviewCreateSerializer(serializers.Serializer):
    order_number = serializers.CharField(max_length=32)
    product_rating = serializers.IntegerField(min_value=1, max_value=5)
    delivery_rating = serializers.IntegerField(min_value=1, max_value=5)
    shop_rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(required=False, allow_blank=True, max_length=4000, default="")
