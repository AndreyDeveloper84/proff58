"""Публичный read-only API каталога: дерево категорий, список, карточка, фасеты."""

from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..filters import ProductFilter, visible_products
from ..models import Category, StockStatus
from ..services import FacetError, build_facets
from .serializers import ProductDetailSerializer, ProductListSerializer


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


class CategoryFacetsView(APIView):
    """Фасеты категории: фильтруемые характеристики со счётчиками (drill-down)."""

    permission_classes = [AllowAny]

    def get(self, request, slug):
        category = get_object_or_404(Category, slug=slug, is_active=True)
        params = request.query_params

        stock_status = params.get("stock_status")
        if stock_status and stock_status not in StockStatus.values:
            return Response({"detail": "Недопустимый stock_status"}, status=400)

        attr_filters = {}
        for key in params:
            if key.startswith("attr_") and key[len("attr_") :]:
                attr_filters[key[len("attr_") :]] = params.getlist(key)

        try:
            data = build_facets(
                category,
                brands=params.getlist("brand") or None,
                stock_status=stock_status or None,
                attr_filters=attr_filters,
            )
        except FacetError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(data)
