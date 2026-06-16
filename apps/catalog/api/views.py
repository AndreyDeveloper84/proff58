"""Публичный read-only API каталога: дерево категорий, список и карточка товара."""

import django_filters
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Category, Product, ProductStatus
from .serializers import ProductDetailSerializer, ProductListSerializer


def visible_products():
    """Товары, видимые на витрине (is_visible нельзя использовать в queryset)."""
    return Product.objects.filter(is_active=True, status=ProductStatus.PUBLISHED)


def build_category_tree(nodes) -> list:
    """Построить вложенное дерево из treebeard-узлов, отсортированных по path.

    Узел оставляем, только если он корень или на вершине стека лежит его настоящий
    прямой родитель (по depth И по префиксу path). Иначе узел — «сирота» (родитель
    неактивен/выпал из выборки) и отбрасывается вместе с поддеревом.
    """
    roots: list = []
    stack: list = []  # [(node, item)]
    for node in nodes:
        item = {
            "id": node.id,
            "name": node.name,
            "slug": node.slug,
            "sort_order": node.sort_order,
            "children": [],
        }
        while stack and stack[-1][0].depth >= node.depth:
            stack.pop()

        if node.depth == 1:
            roots.append(item)
            stack.append((node, item))
            continue

        if not stack:
            continue  # нет родителя в выборке — сирота
        parent_node, parent_item = stack[-1]
        if parent_node.depth == node.depth - 1 and node.path.startswith(parent_node.path):
            parent_item["children"].append(item)
            stack.append((node, item))
        # иначе — родитель неактивен/из другой ветки → пропускаем
    return roots


class CategoryTreeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        nodes = list(Category.objects.filter(is_active=True).order_by("path"))
        return Response(build_category_tree(nodes))


class ProductFilter(django_filters.FilterSet):
    # Категория + все потомки: зайдя в «Электроинструмент», видим товары из «Дрелей».
    category = django_filters.CharFilter(method="filter_category")
    brand = django_filters.CharFilter(field_name="brand", lookup_expr="iexact")

    class Meta:
        model = Product
        fields = ["stock_status"]  # category/brand — объявлены выше явными фильтрами

    def filter_category(self, queryset, name, value):
        try:
            cat = Category.objects.get(slug=value)
        except Category.DoesNotExist:
            return queryset.none()
        ids = [cat.pk, *cat.get_descendants().values_list("pk", flat=True)]
        return queryset.filter(category_id__in=ids)


class ProductListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductListSerializer
    filterset_class = ProductFilter

    def get_queryset(self):
        return (
            visible_products()
            .select_related("category")
            .prefetch_related("images")
            .order_by("name")
        )


class ProductDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return (
            visible_products()
            .select_related("category")
            .prefetch_related(
                "images",
                "attribute_values__attribute",
                "attribute_values__value_option",
            )
        )
