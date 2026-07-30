"""API информационных страниц («Доставка», «О компании», «Гарантия»).

Первое место, где контент из админки доходит до витрины: раньше apps.content
не имел API вовсе и всё, заведённое в разделе, никуда не шло.

Отдаём только опубликованное — та же дисциплина, что в каталоге
(`visible_products`): черновик не должен утекать на сайт по прямой ссылке.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import PublishStatus, SEOPage
from .serializers import InfoPageListSerializer, InfoPageSerializer


def published_pages():
    """Единственное определение «страница видна на сайте»."""
    return SEOPage.objects.filter(status=PublishStatus.PUBLISHED).order_by("title")


class InfoPageListView(APIView):
    """Список страниц для меню подвала."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(InfoPageListSerializer(published_pages(), many=True).data)


class InfoPageDetailView(APIView):
    """Одна страница по slug. Черновик — 404, как будто его нет."""

    permission_classes = [AllowAny]

    def get(self, request, slug):
        page = get_object_or_404(published_pages(), slug=slug)
        return Response(InfoPageSerializer(page).data)
