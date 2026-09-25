"""API контента витрины: информационные страницы и статьи.

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

from ..models import Article, PublishStatus, SEOPage
from .serializers import (
    ArticleListSerializer,
    ArticleSerializer,
    InfoPageListSerializer,
    InfoPageSerializer,
)


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


def published_articles():
    """Статьи витрины: опубликованные, свежие сверху."""
    return (
        Article.objects.filter(status=PublishStatus.PUBLISHED)
        .select_related("catalog_category")
        .order_by("-published_at", "-created_at")
    )


class ArticleListView(APIView):
    """Лента статей."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(ArticleListSerializer(published_articles(), many=True).data)


class ArticleDetailView(APIView):
    """Статья целиком, с уже разобранной структурой."""

    permission_classes = [AllowAny]

    def get(self, request, slug):
        article = get_object_or_404(published_articles(), slug=slug)
        return Response(ArticleSerializer(article).data)
