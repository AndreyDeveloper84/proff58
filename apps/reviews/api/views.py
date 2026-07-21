"""API отзывов (#573).

- POST/GET /api/account/reviews/ — создать/«мои» (IsAuthenticated; через Next-BFF);
- GET /api/reviews/product/<slug>/ — публичный список approved + summary.

Флаг ``reviews`` выключен → 404 с кодом: фича не существует для клиента,
фронт по коду прячет CTA/разделы без мигания.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.features import is_enabled
from apps.core.throttling import ReviewsRateThrottle

from .. import services
from ..models import Review
from .serializers import MyReviewCreateSerializer, MyReviewSerializer, PublicReviewSerializer

_DISABLED = {"detail": services.ERROR_MESSAGES["reviews_disabled"], "code": "reviews_disabled"}
# Код ошибки → HTTP-статус (человеческий detail приходит из ReviewError).
_ERROR_STATUS = {
    "reviews_disabled": status.HTTP_404_NOT_FOUND,
    "order_not_found": status.HTTP_404_NOT_FOUND,
    "order_not_completed": status.HTTP_400_BAD_REQUEST,
    "already_reviewed": status.HTTP_409_CONFLICT,
}


class AccountReviewsView(APIView):
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        # Троттлим только создание: чтение «моих» — обычный трафик ЛК.
        if self.request.method == "POST":
            return [ReviewsRateThrottle()]
        return super().get_throttles()

    def get(self, request):
        if not is_enabled("reviews"):
            return Response(_DISABLED, status=status.HTTP_404_NOT_FOUND)
        qs = (
            Review.objects.filter(author=request.user)
            .select_related("order")
            .order_by("-created_at")
        )
        order_number = request.query_params.get("order")
        if order_number:
            qs = qs.filter(order__order_number=order_number)
        paginator = LimitOffsetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(MyReviewSerializer(page, many=True).data)

    def post(self, request):
        if not is_enabled("reviews"):
            return Response(_DISABLED, status=status.HTTP_404_NOT_FOUND)
        ser = MyReviewCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            review = services.create_review(user=request.user, **ser.validated_data)
        except services.ReviewError as exc:
            return Response(
                {"detail": exc.message, "code": exc.code}, status=_ERROR_STATUS[exc.code]
            )
        return Response(MyReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class ProductReviewsView(APIView):
    """Публичные отзывы товара: только approved, только снапшот-поля, + summary."""

    permission_classes = [AllowAny]

    def get(self, request, slug):
        if not is_enabled("reviews"):
            return Response(_DISABLED, status=status.HTTP_404_NOT_FOUND)
        from apps.catalog.models import Product

        product = Product.objects.only("id").filter(slug=slug).first()
        if product is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        qs = services.public_reviews_for_product(product.pk)
        summary = services.product_rating_summary(qs)  # по всему qs, не по странице
        paginator = LimitOffsetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        response = paginator.get_paginated_response(PublicReviewSerializer(page, many=True).data)
        response.data["summary"] = summary
        return response
