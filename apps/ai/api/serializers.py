"""Сериализация рекомендаций для публичного API AI-слоя.

Переиспользует ``ProductListSerializer`` каталога (цена строго через ``price_map``
из pricing, ADR-0006), добавляя поля рекомендации — ``reason`` и ``score``.
"""

from __future__ import annotations

from apps.catalog.api.serializers import ProductListSerializer


def serialize_recommendation(product, rec, *, context) -> dict:
    """Карточка товара (как в листинге каталога) + причина и оценка рекомендации.

    ``context`` обязан содержать ``price_map`` (bulk-цены) и ``request`` — цена
    берётся оттуда, без N+1 (см. ``ProductListSerializer.to_representation``).
    """
    data = ProductListSerializer(product, context=context).data
    data["reason"] = rec.reason
    data["score"] = rec.score
    return data
