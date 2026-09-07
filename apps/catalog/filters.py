"""Фильтрация товаров каталога — слой queryset-хелперов.

Намеренно НЕ зависит от `api/` (HTTP-слой): сюда вынесены `ProductFilter` и общая
выборка, чтобы и DRF-вьюхи, и сервисы (фасеты #25) опирались на один источник.
"""

from __future__ import annotations

import operator
from functools import reduce

import django_filters
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Case, FloatField, IntegerField, Prefetch, Q, Value, When

from .brand_slugs import resolve_brand_tokens
from .models import Category, Product, ProductAttributeValue, ProductStatus, StockStatus


def visible_products():
    """Товары, видимые на витрине (is_visible нельзя использовать в queryset)."""
    return Product.objects.filter(is_active=True, status=ProductStatus.PUBLISHED)


#: Потолок точечной выборки по id (?ids=). Избранное столько не набирает, а
#: длинный список превратил бы публичный маршрут в способ выгрузить каталог.
MAX_IDS_FILTER = 200


def availability_rank():
    """Ключ сортировки «сначала доступное»: в наличии (0) → под заказ (1) → нет (2).

    Один и тот же ключ у каталога, поиска и подсказок. Раньше он был только в
    листинге: поиск сортировал по чистой релевантности, и первые экраны выдачи
    состояли из позиций «Нет в наличии» — то есть один и тот же товар вёл себя
    по-разному в зависимости от того, как до него дошли. Позиции не скрываются,
    меняется только очерёдность.
    """
    return Case(
        When(stock_status=StockStatus.IN_STOCK, then=Value(0)),
        When(stock_status=StockStatus.ON_ORDER, then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    )


def products_by_ids_for_cards(ids) -> dict[int, Product]:
    """Карточные Product по списку id с prefetch без N+1 (для AI-рекомендаций и пр.).

    Инкапсулирует доступ к таблицам каталога: вызывающие из других приложений
    (apps/ai) не трогают Product.objects напрямую (ADR-0004). Возврат — словарь
    {id: Product}; порядок выстраивает вызывающий по своему списку id.
    """
    return {
        p.id: p
        for p in Product.objects.filter(id__in=list(ids))
        .select_related("category", "sales_stat")
        .prefetch_related(
            "images",
            Prefetch(
                "attribute_values",
                queryset=ProductAttributeValue.objects.select_related("attribute", "value_option"),
            ),
        )
    }


class ProductFilter(django_filters.FilterSet):
    # Категория + все потомки: зайдя в «Электроинструмент», видим товары из «Дрелей».
    category = django_filters.CharFilter(method="filter_category")
    brand = django_filters.CharFilter(method="filter_brand")
    # tool_type — вторая ось навигации (slug варианта атрибута), in_stock — наличие.
    tool_type = django_filters.CharFilter(method="filter_tool_type")
    in_stock = django_filters.CharFilter(method="filter_in_stock")
    # Диапазон розничной цены (PLP-фасет «Цена»): price_min / price_max.
    price_min = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    price_max = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    # Поиск по каталогу (#52): index-accelerated lookups + trigram (typo-tolerance).
    search = django_filters.CharFilter(method="filter_search")
    # Точечная выборка по id (comma-list) — избранное берёт карточки сохранённых
    # товаров ОДНИМ запросом вместо запроса на каждое сердечко.
    ids = django_filters.CharFilter(method="filter_ids")

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

    def filter_brand(self, queryset, name, value):
        """Бренд по slug ИЛИ сырой строке (dual-accept, P-полировка). comma-list → OR.

        Токены резолвятся slug→Product.brand (``resolve_brand_tokens``), фильтр —
        регистронезависимый OR (iexact; brand__in регистрозависим). Неизвестный токен
        просто ничего не находит, листинг не падает.
        """
        tokens = [t.strip() for t in (value or "").split(",") if t.strip()]
        brands = resolve_brand_tokens(tokens)
        if not brands:
            return queryset
        return queryset.filter(reduce(operator.or_, (Q(brand__iexact=b) for b in brands)))

    def filter_tool_type(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            attribute_values__attribute__slug="tool_type",
            attribute_values__value_option__slug=value,
        )

    def filter_in_stock(self, queryset, name, value):
        if str(value) in ("1", "true", "True", "yes"):
            return queryset.filter(stock_quantity__gt=0)
        return queryset

    def filter_ids(self, queryset, name, value):
        """comma-list id → ровно эти товары (и только видимые: базовый qs не ослабляем).

        Мусор и пустой список дают пустую выдачу, а не весь каталог: явно
        заданный фильтр, который ничего не выбрал, обязан вернуть ничего.
        """
        tokens = [token.strip() for token in (value or "").split(",")]
        ids = [int(token) for token in tokens if token.isdigit()]
        if not ids:
            return queryset.none()
        return queryset.filter(id__in=ids[:MAX_IDS_FILTER])

    def filter_search(self, queryset, name, value):
        """Поиск по name/article/brand/code_1c (#52), trigram V1.

        Матчинг ускоряется trigram-GIN (name/article/brand — icontains и
        trigram_similar) и btree (article/code_1c). По code_1c — только
        точное/префиксное совпадение (это техкод, fuzzy не нужен).

        Ранг — взвешенный (Case/When по типу совпадения + сходство имени);
        аннотируется ДО фильтра. Ordering задаётся здесь же при len(q) >= 2,
        чтобы во view не было ссылки на _rank, которой может не быть.

        Первый ключ порядка — наличие (``availability_rank``), как в каталоге:
        релевантность решает уже внутри доступных товаров. Аннотацию ставим
        здесь же, а не полагаемся на вьюху, — фильтром пользуются и другие
        вызывающие, и ссылка на чужую аннотацию сломала бы им запрос.
        """
        q = (value or "").strip()
        if len(q) < 2:
            return queryset

        rank = Case(
            When(Q(article__iexact=q) | Q(code_1c__iexact=q), then=Value(100.0)),
            When(Q(article__istartswith=q) | Q(code_1c__istartswith=q), then=Value(50.0)),
            When(brand__icontains=q, then=Value(20.0)),
            When(name__icontains=q, then=Value(10.0)),
            default=Value(0.0),
            output_field=FloatField(),
        ) + TrigramSimilarity("name", q)
        return search_match(
            queryset.annotate(_rank=rank, _availability=availability_rank()), q
        ).order_by("_availability", "-_rank", "name", "id")


def search_match(queryset, q):
    """Товары, попадающие под поисковый запрос: только отбор, без ранга и порядка.

    Вынесено из ``ProductFilter.filter_search`` ради фасетов поиска (DRF-1166,
    ``facets.build_search_facets``): счётчики обязаны считаться по тем же товарам,
    что попадают в список. Два независимых набора Q-условий разъехались бы при
    первой же правке матчинга, и сайдбар начал бы обещать выдачу, которой нет.

    Запрос короче двух символов ничего не отбирает — как и в фильтре списка.
    """
    q = (q or "").strip()
    if len(q) < 2:
        return queryset
    return queryset.filter(
        Q(name__icontains=q)
        | Q(name__trigram_similar=q)
        # word_similar — пословное сходство (%>): «перфоратр» матчит слово
        # «Перфоратор» внутри длинного name, где similar по всей строке
        # проседает ниже порога. Тот же gin_trgm_ops индекс.
        | Q(name__trigram_word_similar=q)
        | Q(article__icontains=q)
        | Q(article__trigram_similar=q)
        | Q(brand__icontains=q)
        | Q(brand__trigram_similar=q)
        | Q(code_1c__iexact=q)
        | Q(code_1c__istartswith=q)
    )


def filtered_products(category, *, brands=None, stock_status=None, subtree_ids=None):
    """Видимые товары категории (+ все потомки) с опциональными фильтрами.

    brands — список брендов, OR с регистронезависимым сравнением.
    ``subtree_ids`` — заранее посчитанные id поддерева (категория + потомки). Передаётся,
    когда выборка строится многократно для одной категории (фасеты считают N+ срезов
    drill-down): иначе ``get_descendants()`` бил бы в дерево на каждом срезе. None →
    считаем сами (обычный одиночный листинг).
    """
    ids = (
        subtree_ids
        if subtree_ids is not None
        else [
            category.pk,
            *category.get_descendants().values_list("pk", flat=True),
        ]
    )
    qs = visible_products().filter(category_id__in=ids)
    if brands:
        qs = qs.filter(reduce(operator.or_, (Q(brand__iexact=b) for b in brands)))
    if stock_status:
        qs = qs.filter(stock_status=stock_status)
    return qs
