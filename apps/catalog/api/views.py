"""Публичный read-only API каталога: дерево категорий, список, карточка, фасеты."""

from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Case, F, FloatField, Prefetch, Q, Value, When
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import SubscriptionRateThrottle
from apps.pricing.services import price_map_for_products

from ..availability_subscriptions import (
    MaxConnectionRequired,
    ProductInStock,
    ProductNotEligible,
    get_eligible_product,
    get_status,
    subscribe,
    unsubscribe,
)
from ..filters import ProductFilter, visible_products
from ..models import Category, ProductAttributeValue, StockStatus
from ..sales import bestsellers_queryset
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


def with_card_prefetch(qs):
    """Догрузить всё, что нужно карточке товара, без N+1 по странице выдачи.

    Общая для списка каталога и витрины хитов: расхождение в prefetch между ними
    оборачивалось бы лишними запросами на одном из маршрутов.
    """
    return qs.select_related("category", "sales_stat").prefetch_related(
        "images",
        Prefetch(
            "attribute_values",
            queryset=ProductAttributeValue.objects.select_related("attribute", "value_option"),
        ),
    )


class ProductListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductListSerializer
    filterset_class = ProductFilter

    def get_queryset(self):
        # При поиске (?search=, len>=2) ordering по релевантности задаёт
        # ProductFilter.filter_search (.order_by("-_rank", ...)); _rank существует
        # только тогда. Без поиска — серверная сортировка (?sort=) / алфавит.
        qs = with_card_prefetch(visible_products())
        attr_filters, attr_ranges = parse_attr_params(self.request.query_params)
        qs = apply_product_attr_filters(qs, attr_filters, attr_ranges)
        q = (self.request.query_params.get("search") or "").strip()
        if len(q) >= 2:
            return qs  # поиск → релевантность (filter_search); ?sort игнорируется
        return self._apply_sort(qs)

    def _annotate_effective_price(self, qs):
        """Аннотировать ``effective_price`` для SQL-сортировки по цене.

        #430 (M-06, ADR #444): единый ценник — сортировка по ``Product.price`` для
        всех (B2C и B2B); отдельной оптовой цены нет. Логика 1:1 с
        ``pricing.services.price_for``.
        """
        return qs.annotate(effective_price=F("price"))

    def _apply_sort(self, qs):
        """Серверная сортировка (whitelist) ДО пагинации. Дефолт — алфавит.

        ``price_asc/desc`` — по ``Product.price`` (#430/M-06: единый ценник для всех).
        Товары без цены — в конец (nulls_last). ``bestsellers`` — по рейтингу продаж
        (apps.catalog.sales). Неизвестное/popular/rating → дефолт.
        """
        sort = self.request.query_params.get("sort")
        if sort in ("price_asc", "price_desc"):
            qs = self._annotate_effective_price(qs)
            ep = F("effective_price")
            order = ep.asc(nulls_last=True) if sort == "price_asc" else ep.desc(nulls_last=True)
            return qs.order_by(order, "id")
        if sort == "new":
            return qs.order_by("-created_at", "id")
        if sort == "bestsellers":
            # Рейтинг продаж (apps.catalog.sales). Товары без продаж — в конец:
            # сортировка ничего не скрывает, но и не выдаёт их за продаваемые.
            return qs.annotate(sales_rank=F("sales_stat__rank")).order_by(
                F("sales_rank").asc(nulls_last=True), "id"
            )
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


class BestsellersView(ProductListView):
    """Товары с реальными продажами за окно — витрина «Хиты продаж».

    Отдельный маршрут, а не ``?sort=bestsellers``, именно из-за честности: здесь
    выдача ОГРАНИЧЕНА товарами, у которых есть продажи. Пустой ответ означает
    «продаж пока нет» — подменять его новинками или ручным списком нельзя, это и
    была прежняя неправда витрины. Фильтры каталога тут не применяются.
    """

    filterset_class = None

    def get_queryset(self):
        return with_card_prefetch(bestsellers_queryset())


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


class ProductAvailabilitySubscriptionView(APIView):
    """GET/POST/DELETE /api/catalog/products/<slug>/availability-subscription/ (#517).

    Только authenticated (product/user ownership — всегда request.user, чужой id
    в пути невозможен). Правила (товар не в наличии, есть MAX) — в сервисном
    слое (`apps.catalog.availability_subscriptions`), не только здесь, чтобы их
    нельзя было обойти вызовом функции напрямую в обход API.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [SubscriptionRateThrottle]

    def _get_product_or_404(self, slug: str):
        try:
            return get_eligible_product(slug), None
        except ProductNotEligible as exc:
            return None, Response(
                {"detail": "Товар не найден.", "code": exc.code}, status=status.HTTP_404_NOT_FOUND
            )

    def get(self, request, slug):
        product, error = self._get_product_or_404(slug)
        if error is not None:
            return error
        sub = get_status(request.user, product)
        return Response({"status": sub.status if sub else None})

    def post(self, request, slug):
        product, error = self._get_product_or_404(slug)
        if error is not None:
            return error
        try:
            sub = subscribe(request.user, product)
        except ProductInStock as exc:
            return Response(
                {"detail": "Товар сейчас в наличии.", "code": exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except MaxConnectionRequired as exc:
            return Response(
                {"detail": "Нужна активная привязка MAX.", "code": exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"status": sub.status}, status=status.HTTP_201_CREATED)

    def delete(self, request, slug):
        product, error = self._get_product_or_404(slug)
        if error is not None:
            return error
        unsubscribe(request.user, product)
        return Response(status=status.HTTP_204_NO_CONTENT)
