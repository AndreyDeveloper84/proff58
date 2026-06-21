"""Публичный read-only API каталога: дерево категорий, список, карточка, фасеты."""

from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.pricing.services import price_map_for_products

from ..filters import ProductFilter, visible_products
from ..models import Category, StockStatus
from ..services import FacetError, build_facets, compatibility_sections
from .serializers import (
    ProductDetailSerializer,
    ProductListSerializer,
    serialize_compat_item,
)


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

    def list(self, request, *args, **kwargs):
        """Считаем опт-цены ОДНИМ bulk-запросом по текущей странице (без N+1).

        price_map строится только по товарам страницы и передаётся сериализатору
        через context; формат пагинации сохраняется.
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        products = list(page) if page is not None else list(queryset)
        price_map = price_map_for_products(products, request.user)
        context = {**self.get_serializer_context(), "price_map": price_map}
        serializer = self.get_serializer_class()(products, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


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


class ProductCompatibleView(APIView):
    """Совместимость товара (#79): три секции — аксессуары, к чему подходит, совместимые.

    Цены по всем товарам трёх секций считаются ОДНИМ bulk-запросом
    (price_map_for_products), чтобы не было N+1 по опт-ценам.
    """

    permission_classes = [AllowAny]

    def get(self, request, slug):
        product = get_object_or_404(visible_products(), slug=slug)
        sections = compatibility_sections(product)

        # Все товары трёх секций → один price_map (дедуп по pk для bulk-резолвера).
        all_products = {}
        for items in sections.values():
            for item in items:
                all_products.setdefault(item.product.pk, item.product)
        price_map = price_map_for_products(list(all_products.values()), request.user)
        context = {"request": request, "price_map": price_map}

        return Response(
            {
                name: [serialize_compat_item(item, context) for item in items]
                for name, items in sections.items()
            }
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
