"""Публичный API AI-слоя: рекомендации «похожие по характеристикам»."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.api.serializers import serialize_recommendation
from apps.ai.services import DEFAULT_LIMIT, recommend
from apps.catalog.filters import visible_products
from apps.catalog.models import Product
from apps.pricing.services import price_map_for_products


def _parse_limit(raw) -> int:
    """limit из query: целое или дефолт. Валидацию границ делает recommend()."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


class ProductRecommendationsView(APIView):
    """``GET /api/ai/products/<slug>/recommendations/?limit=N`` — подбор похожих.

    Якорь — видимый товар по slug (404, если нет). Порядок выдачи строго совпадает
    с порядком ``recommend()``; цена — bulk через ``price_map_for_products`` (без
    N+1).
    """

    permission_classes = [AllowAny]

    def get(self, request, slug):
        anchor = get_object_or_404(visible_products(), slug=slug)
        limit = _parse_limit(request.query_params.get("limit"))

        recs = recommend(context={"product_id": anchor.id}, limit=limit)

        by_id = {
            p.id: p
            for p in Product.objects.filter(id__in=[r.product_id for r in recs])
            .select_related("category")
            .prefetch_related("images")
        }
        ordered = [(by_id[r.product_id], r) for r in recs if r.product_id in by_id]

        price_map = price_map_for_products([p for p, _ in ordered], request.user)
        context = {"request": request, "price_map": price_map}

        results = [
            serialize_recommendation(product, rec, context=context) for product, rec in ordered
        ]
        return Response({"results": results})
