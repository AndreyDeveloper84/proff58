"""Публичный read-only API каталога: дерево категорий, список, карточка, фасеты."""

import math

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
from ..filters import ProductFilter, availability_rank, search_products, visible_products
from ..models import Category, ProductAttributeValue, StockStatus
from ..sales import bestsellers_queryset
from ..seo_index import indexable_product_ids
from ..services import (
    FacetError,
    apply_product_attr_filters,
    brand_page,
    build_brand_facets,
    build_facets_cached,
    build_search_facets,
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


def _finite_float(raw) -> float | None:
    """Число из query-параметра; пустое, мусор, ``nan`` и ``±inf`` → ``None``.

    ``float()`` принимает ``"nan"``, ``"inf"`` и ``"1e999"`` без ошибки, а дальше они
    роняли ответ в 500: цена — в ``DecimalField`` (``ValidationError``), граница
    характеристики — в JSON-рендере (эхо в ``applied_filters``, «Out of range float
    values are not JSON compliant»). Кривой URL фасеты ронять не должен — игнорируем.
    """
    if not raw:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if math.isfinite(val) else None


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
            val = _finite_float(params.get(key))
            if val is None:
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
        # DRF-1166: у страницы поиска появился тулбар сортировки. Молчаливый выбор
        # (?sort не передан) по-прежнему релевантность — иначе поиск перестанет быть
        # поиском; явный ?sort уважаем, человек попросил именно его.
        if len(q) >= 2 and not self.request.query_params.get("sort"):
            return qs
        return self._apply_sort(qs)

    def _annotate_effective_price(self, qs):
        """Аннотировать ``effective_price`` для SQL-сортировки по цене.

        #430 (M-06, ADR #444): единый ценник — сортировка по ``Product.price`` для
        всех (B2C и B2B); отдельной оптовой цены нет. Логика 1:1 с
        ``pricing.services.price_for``.
        """
        return qs.annotate(effective_price=F("price"))

    def _annotate_availability(self, qs):
        """Аннотировать ``availability_rank`` для сортировки «сначала доступное».

        В наличии (0) → под заказ (1) → нет в наличии (2). Нужен потому, что 87 %
        каталога сейчас без остатка, и по любому порядку первые экраны состояли
        из «Сообщить о поступлении». Позиции не скрываются и не исключаются из
        выдачи — меняется только очерёдность; фасет «Наличие» работает как был.

        Сам ключ живёт в filters.availability_rank() — им же пользуются поиск и
        подсказки, чтобы порядок не расходился между маршрутами.
        """
        return qs.annotate(availability_rank=availability_rank())

    def _apply_sort(self, qs):
        """Серверная сортировка (whitelist) ДО пагинации. Дефолт — алфавит.

        Первым ключом везде идёт наличие (``availability_rank``) — выбранный
        пользователем порядок применяется уже внутри доступных товаров.
        ``price_asc/desc`` — по ``Product.price`` (#430/M-06: единый ценник для всех).
        Товары без цены — в конец (nulls_last). ``bestsellers`` — по рейтингу продаж
        (apps.catalog.sales). Неизвестное/popular/rating → дефолт.
        """
        sort = self.request.query_params.get("sort")
        qs = self._annotate_availability(qs)
        if sort in ("price_asc", "price_desc"):
            qs = self._annotate_effective_price(qs)
            ep = F("effective_price")
            order = ep.asc(nulls_last=True) if sort == "price_asc" else ep.desc(nulls_last=True)
            return qs.order_by("availability_rank", order, "id")
        if sort == "new":
            return qs.order_by("availability_rank", "-created_at", "id")
        if sort == "bestsellers":
            # Рейтинг продаж (apps.catalog.sales). Товары без продаж — в конец:
            # сортировка ничего не скрывает, но и не выдаёт их за продаваемые.
            return qs.annotate(sales_rank=F("sales_stat__rank")).order_by(
                "availability_rank", F("sales_rank").asc(nulls_last=True), "id"
            )
        return qs.order_by("availability_rank", "name", "id")

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

    Порядок — как в каталоге и поиске: сначала то, что есть в наличии. Десять
    подсказок из позиций «Нет в наличии» уводили покупателя в тупик ещё до
    выдачи, хотя доступный товар по тому же запросу существовал.
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
            .annotate(_rank=rank, _availability=availability_rank())
            .filter(
                Q(name__icontains=q)
                | Q(name__trigram_similar=q)
                | Q(name__trigram_word_similar=q)
                | Q(article__icontains=q)
                | Q(brand__icontains=q)
                | Q(code_1c__istartswith=q)
            )
            .order_by("_availability", "-_rank", "name")
            .values("id", "name", "slug")[:SUGGEST_LIMIT]
        )
        return Response(list(rows))


#: Быстрый поиск в шапке: сколько товаров и разделов показывает панель.
QUICK_SEARCH_PRODUCTS = 6
QUICK_SEARCH_CATEGORIES = 3
#: Сколько первых совпадений поиска смотрим, подбирая разделы. Разделы считаются
#: по той же ранжированной выдаче, что и товары, но глубже первой шестёрки: иначе
#: запрос «шуруп» показал бы раздел только тех шести товаров, что стоят первыми.
QUICK_SEARCH_POOL = 300


def _fold(text: str) -> str:
    """Нормализация для сравнения подписей: регистр и «ё» → «е»."""
    return (text or "").casefold().replace("ё", "е")


def _storefront_categories(paths) -> dict[str, dict]:
    """Категории, до которых покупатель доходит по дереву витрины, — ``{path: row}``.

    Один выключенный (``is_active``/``on_site``) предок прячет всё поддерево,
    поэтому смотрим всю цепочку: префиксы ``path`` длиной, кратной ``steplen``, —
    ровно предки узла (MP_Node). Та же логика, что ``facet_audit.visible_categories``,
    но одним запросом только по нужным цепочкам, а не по всему дереву.
    """
    step = Category.steplen
    chains = {
        path: [path[:i] for i in range(step, len(path) + 1, step)] for path in set(paths) if path
    }
    wanted = {prefix for chain in chains.values() for prefix in chain}
    if not wanted:
        return {}
    rows = {
        row["path"]: row
        for row in Category.objects.filter(path__in=wanted).values(
            "path", "name", "slug", "is_active", "on_site"
        )
    }
    return {
        path: rows[path]
        for path, chain in chains.items()
        if all(p in rows and rows[p]["is_active"] and rows[p]["on_site"] for p in chain)
    }


class SearchQuickView(APIView):
    """Быстрый поиск в шапке витрины: до 6 товаров и до 3 разделов по запросу.

    ``GET /api/catalog/search/quick/?q=`` → ``{"query", "products", "categories"}``.
    Запрос короче двух символов — пустые списки.

    Ранжированный поиск — тот же, что у ``products/?search=`` (``search_products``),
    и выполняется ОДИН раз: первые совпадения дают и товары, и разделы. Товары —
    карточки листинга (``ProductListSerializer`` с ценами одного bulk-вызова).

    Раздел — пара «категория + вид товара (tool_type)»: запрос «шуруп» должен
    развести шурупы, шуруповёрты и оснастку, а они часто лежат в одной категории.
    Выше стоят разделы, чьё название содержит сам запрос, дальше — по числу
    совпадений. Скрытые на витрине категории (сама или предок выключены) не
    предлагаются: ссылка на них вела бы в 404.

    Серверного кэша нет намеренно: цены в карточке зависят от пользователя.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            return Response({"query": q, "products": [], "categories": []})

        pool = list(
            search_products(visible_products(), q).values_list(
                "id", "category_id", "category__path"
            )[:QUICK_SEARCH_POOL]
        )
        return Response(
            {
                "query": q,
                "products": self._products(request, [pid for pid, _, _ in pool]),
                "categories": self._categories(q, pool),
            }
        )

    def _products(self, request, ids: list[int]) -> list:
        top = ids[:QUICK_SEARCH_PRODUCTS]
        if not top:
            return []
        order = {pid: i for i, pid in enumerate(top)}
        products = sorted(
            with_card_prefetch(visible_products().filter(id__in=top)),
            key=lambda p: order[p.id],
        )
        context = {
            "request": request,
            "view": self,
            "price_map": price_map_for_products(products, request.user),
        }
        return ProductListSerializer(products, many=True, context=context).data

    def _categories(self, q: str, pool) -> list[dict]:
        visible = _storefront_categories(path for _, _, path in pool)
        if not visible:
            return []
        # Вид товара одним запросом по всем совпадениям пула (у товара он один:
        # unique_together product+attribute).
        tool_types = {
            pid: (slug, value)
            for pid, slug, value in ProductAttributeValue.objects.filter(
                product_id__in=[pid for pid, _, _ in pool],
                attribute__slug="tool_type",
                value_option__isnull=False,
            )
            .exclude(value_option__slug="")
            .values_list("product_id", "value_option__slug", "value_option__value")
        }

        groups: dict[tuple, dict] = {}
        for index, (pid, _, path) in enumerate(pool):
            category = visible.get(path)
            if category is None:
                continue
            tool_slug, tool_name = tool_types.get(pid, (None, None))
            key = (path, tool_slug)
            group = groups.get(key)
            if group is None:
                groups[key] = group = {
                    "name": tool_name or category["name"],
                    "category": category,
                    "tool_type": tool_slug,
                    "count": 0,
                    "first": index,
                }
            group["count"] += 1

        needle = _fold(q)

        def sort_key(group):
            named = needle in _fold(group["name"]) or needle in _fold(group["category"]["name"])
            return (0 if named else 1, -group["count"], group["first"])

        out: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for group in sorted(groups.values(), key=sort_key):
            # Одинаковые подписи не повторяем: вид с тем же именем, что и раздел,
            # или одноимённые разделы в разных ветках дерева выглядели бы дублями.
            label = (_fold(group["name"]), _fold(group["category"]["name"]))
            if label in seen:
                continue
            seen.add(label)
            out.append(
                {
                    "name": group["name"],
                    "category": {
                        "name": group["category"]["name"],
                        "slug": group["category"]["slug"],
                    },
                    "tool_type": group["tool_type"],
                }
            )
            if len(out) == QUICK_SEARCH_CATEGORIES:
                break
        return out


class SitemapProductsView(APIView):
    """Товары для sitemap.xml витрины (PF-SH-RELEASE-01): только allowlist ∩ видимые.

    ``GET /api/catalog/seo/sitemap-products/`` → ``[{"slug", "updated_at"}]``.
    Остальной каталог в sitemap не попадает — он закрыт от индексации (noindex).
    """

    permission_classes = [AllowAny]

    def get(self, request):
        rows = (
            visible_products()
            .filter(id__in=indexable_product_ids())
            .order_by("slug")
            .values("slug", "updated_at")
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

        try:
            data = build_facets_cached(
                category,
                tool_type=params.get("tool_type") or None,
                brands=params.getlist("brand") or None,
                stock_status=stock_status or None,
                attr_filters=attr_filters,
                attr_ranges=attr_ranges,
                price_min=_finite_float(params.get("price_min")),
                price_max=_finite_float(params.get("price_max")),
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


class SearchFacetsView(APIView):
    """Базовые фасеты поисковой выдачи: цена, бренды, наличие (DRF-1166).

    Категории у поиска нет, поэтому EAV-характеристик здесь не бывает — только три
    оси, осмысленные для смешанной выдачи. Параметры те же, что у ``products/?search=``,
    чтобы сайдбар и список читались из одного URL.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        params = request.query_params
        q = (params.get("search") or "").strip()
        if len(q) < 2:
            # Короткий запрос ничего не ищет (см. filters.search_match) — фасетам
            # тоже нечего показывать; пустой ответ вместо фасетов всего каталога.
            return Response(
                {
                    "query": q,
                    "price": {"min": None, "max": None},
                    "brands": [],
                    "stock": [],
                    "total_products": 0,
                    "applied_filters": {"brands": [], "stock_status": None},
                }
            )

        stock_status = params.get("stock_status")
        if stock_status and stock_status not in StockStatus.values:
            return Response({"detail": "Недопустимый stock_status"}, status=400)

        return Response(
            build_search_facets(
                q,
                brands=params.getlist("brand") or None,
                stock_status=stock_status or None,
                price_min=_finite_float(params.get("price_min")),
                price_max=_finite_float(params.get("price_max")),
            )
        )


class BrandDetailView(APIView):
    """Страница бренда (UX-07): название, категории бренда, цена, наличие, счётчики.

    ``GET /api/catalog/brands/<slug>/?category=&stock_status=&price_min=&price_max=``.
    Список товаров берётся обычным ``products/?brand_slug=<slug>`` с теми же параметрами —
    отбор у них общий, поэтому ``total_products`` равен ``count`` списка.

    Три разных исхода, которые витрина обязана различать:
    404 — бренда нет ни у одного товара; 200 с ``brand_total_products == 0`` — бренд
    известен, но на витрине сейчас пусто; 200 с ``total_products == 0`` при ненулевом
    ``brand_total_products`` — товары есть, их скрыли выбранные фильтры.
    """

    permission_classes = [AllowAny]

    def get(self, request, slug):
        page = brand_page(slug)
        if page is None:
            return Response({"detail": "Бренд не найден."}, status=status.HTTP_404_NOT_FOUND)

        params = request.query_params
        stock_status = params.get("stock_status")
        if stock_status and stock_status not in StockStatus.values:
            return Response({"detail": "Недопустимый stock_status"}, status=400)

        category = None
        category_slug = (params.get("category") or "").strip()
        if category_slug:
            category = Category.objects.filter(slug=category_slug, is_active=True).first()
            if category is None:
                # Список по неизвестной категории пуст (ProductFilter.filter_category) —
                # фасеты обязаны сказать то же самое, а не показать весь бренд.
                return Response({"detail": "Категория не найдена."}, status=400)

        data = build_brand_facets(
            page["spellings"],
            category=category,
            stock_status=stock_status or None,
            price_min=_finite_float(params.get("price_min")),
            price_max=_finite_float(params.get("price_max")),
        )
        data["brand"] = {"slug": page["slug"], "name": page["name"]}
        data["brand_total_products"] = page["visible_total"]
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
