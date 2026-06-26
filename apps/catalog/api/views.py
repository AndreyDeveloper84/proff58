"""Публичный read-only API каталога: дерево категорий, список, карточка, фасеты."""

from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Case, F, FloatField, OuterRef, Prefetch, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.features import is_enabled
from apps.pricing.models import PriceRecord
from apps.pricing.services import WHOLESALE, price_map_for_products

from ..filters import ProductFilter, visible_products
from ..models import Category, ProductAttributeValue, StockStatus
from ..services import (
    FacetError,
    apply_product_attr_filters,
    build_facets_cached,
    compatibility_sections,
)
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


def parse_attr_params(params) -> tuple[dict[str, list[str]], dict[str, tuple]]:
    """Разобрать EAV-параметры PLP в фильтры и числовые диапазоны (общий разбор для вьюх).

    ``attr_<slug>`` → ``filters[slug] = [raw, ...]`` (чекбоксы/select, OR внутри атрибута).
    ``attr_<slug>_min`` / ``attr_<slug>_max`` → ``ranges[slug] = (lo, hi)`` (float; мусор/пусто
    игнорируем — ни список, ни фасеты не должны падать на кривом URL). Деление по суффиксу
    ``_min/_max``; slug select-атрибутов так не оканчивается, поэтому пересечения нет.
    Список товаров и счётчики фасетов используют ОДИН разбор → выдача согласована.
    """
    prefix = "attr_"
    filters: dict[str, list[str]] = {}
    ranges_acc: dict[str, list] = {}  # slug -> [lo, hi]
    for key in params:
        if not key.startswith(prefix) or not key[len(prefix) :]:
            continue
        body = key[len(prefix) :]
        if body.endswith("_min") or body.endswith("_max"):
            slug = body[:-4]
            if not slug:
                continue
            try:
                val = float(params.get(key))
            except (TypeError, ValueError):
                continue  # пустое/мусор → диапазон без этой границы
            lo, hi = ranges_acc.get(slug, [None, None])
            if body.endswith("_min"):
                lo = val
            else:
                hi = val
            ranges_acc[slug] = [lo, hi]
        else:
            filters[body] = params.getlist(key)
    return filters, {slug: (b[0], b[1]) for slug, b in ranges_acc.items()}


class ProductListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductListSerializer
    filterset_class = ProductFilter

    def get_queryset(self):
        # При поиске (?search=, len>=2) ordering по релевантности задаёт
        # ProductFilter.filter_search (.order_by("-_rank", ...)); _rank существует
        # только тогда. Без поиска — серверная сортировка (?sort=) / алфавит.
        qs = (
            visible_products()
            .select_related("category")
            .prefetch_related(
                "images",
                # specs на карточке: атрибуты товара одним prefetch (без N+1 по странице).
                Prefetch(
                    "attribute_values",
                    queryset=ProductAttributeValue.objects.select_related(
                        "attribute", "value_option"
                    ),
                ),
            )
        )
        attr_filters, attr_ranges = parse_attr_params(self.request.query_params)
        qs = apply_product_attr_filters(qs, attr_filters, attr_ranges)
        q = (self.request.query_params.get("search") or "").strip()
        if len(q) >= 2:
            return qs  # поиск → релевантность (filter_search); ?sort игнорируется
        return self._apply_sort(qs)

    def _annotate_effective_price(self, qs):
        """Аннотировать ``effective_price`` для SQL-сортировки по цене.

        Логика 1:1 с ``pricing.services.price_for``: для B2B (+фича ``b2b``) — текущая опт-цена
        из ``PriceRecord`` по ``(code_1c, currency, wholesale, is_current)``; при отсутствии —
        розница ``Product.price`` (Coalesce). Для B2C/анонима — сразу ``Product.price``.
        """
        user = self.request.user
        is_b2b = bool(user and getattr(user, "is_b2b", False)) and is_enabled("b2b")
        if not is_b2b:
            return qs.annotate(effective_price=F("price"))
        wholesale = (
            PriceRecord.objects.filter(
                code_1c=OuterRef("code_1c"),
                price_type=WHOLESALE,
                currency=OuterRef("currency"),
                is_current=True,
            )
            .order_by("-valid_from", "-id")  # детерминизм (unique по is_current; order_by — защита)
            .values("value")[:1]
        )
        return qs.annotate(
            effective_price=Coalesce(
                Subquery(wholesale, output_field=PriceRecord._meta.get_field("value")),
                F("price"),
            )
        )

    def _apply_sort(self, qs):
        """Серверная сортировка (whitelist) ДО пагинации. Дефолт — алфавит.

        ``price_asc/desc`` — по ЭФФЕКТИВНОЙ цене пользователя (B2B-опт через
        ``_annotate_effective_price``; для B2C/анонима = ``Product.price``). Товары без цены —
        в конец (nulls_last). Неизвестное/popular/rating → дефолт.

        Known limitation: price-ФИЛЬТР (``price_min/max``) и price-ФАСЕТ пока на ``Product.price``
        (retail) даже для B2B — полная консистентность price-контракта с B2B-ценой — отдельная задача.
        """
        sort = self.request.query_params.get("sort")
        if sort in ("price_asc", "price_desc"):
            qs = self._annotate_effective_price(qs)
            ep = F("effective_price")
            order = ep.asc(nulls_last=True) if sort == "price_asc" else ep.desc(nulls_last=True)
            return qs.order_by(order, "id")
        if sort == "new":
            return qs.order_by("-created_at", "id")
        return qs.order_by("name", "id")

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


SUGGEST_LIMIT = 10


class ProductSuggestView(APIView):
    """Подсказки автодополнения поиска (#52): лёгкий список {id, name, slug}.

    Только видимые товары, ранжированы по сходству имени (trigram), не более
    SUGGEST_LIMIT. Запрос короче 2 символов → пустой список.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            return Response([])
        # Буст по имени: точное совпадение > префикс > сходство (trigram).
        rank = Case(
            When(name__iexact=q, then=Value(2.0)),
            When(name__istartswith=q, then=Value(1.0)),
            default=Value(0.0),
            output_field=FloatField(),
        ) + TrigramSimilarity("name", q)
        rows = (
            visible_products()
            .annotate(_rank=rank)
            .filter(
                Q(name__icontains=q)
                | Q(name__trigram_similar=q)
                | Q(name__trigram_word_similar=q)
                | Q(article__icontains=q)
                | Q(brand__icontains=q)
                | Q(code_1c__istartswith=q)
            )
            .order_by("-_rank", "name")
            .values("id", "name", "slug")[:SUGGEST_LIMIT]
        )
        return Response(list(rows))


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

        attr_filters, attr_ranges = parse_attr_params(params)

        def _price(name):
            raw = params.get(name)
            if not raw:
                return None
            try:
                return float(raw)
            except ValueError:
                return None  # мусор в цене игнорируем (фасеты не должны падать)

        try:
            data = build_facets_cached(
                category,
                tool_type=params.get("tool_type") or None,
                brands=params.getlist("brand") or None,
                stock_status=stock_status or None,
                attr_filters=attr_filters,
                attr_ranges=attr_ranges,
                price_min=_price("price_min"),
                price_max=_price("price_max"),
            )
        except FacetError as exc:
            return Response({"detail": str(exc)}, status=400)

        hero_image = category.hero_image
        try:
            hero_url = request.build_absolute_uri(hero_image.url) if hero_image else None
        except ValueError:
            hero_url = None
        data["category"]["hero"] = {
            "image": hero_url,
            "eyebrow": category.hero_eyebrow,
            "ctaLabel": category.hero_cta_label,
            "ctaHref": category.hero_cta_href,
        }
        return Response(data)
