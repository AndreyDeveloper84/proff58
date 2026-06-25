"""Фильтрация товаров каталога — слой queryset-хелперов.

Намеренно НЕ зависит от `api/` (HTTP-слой): сюда вынесены `ProductFilter` и общая
выборка, чтобы и DRF-вьюхи, и сервисы (фасеты #25) опирались на один источник.
"""

from __future__ import annotations

import operator
from functools import reduce

import django_filters
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Case, FloatField, Q, Value, When

from .brand_slugs import resolve_brand_tokens
from .models import Category, Product, ProductStatus


def visible_products():
    """Товары, видимые на витрине (is_visible нельзя использовать в queryset)."""
    return Product.objects.filter(is_active=True, status=ProductStatus.PUBLISHED)


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

    def filter_search(self, queryset, name, value):
        """Поиск по name/article/brand/code_1c (#52), trigram V1.

        Матчинг ускоряется trigram-GIN (name/article/brand — icontains и
        trigram_similar) и btree (article/code_1c). По code_1c — только
        точное/префиксное совпадение (это техкод, fuzzy не нужен).

        Ранг — взвешенный (Case/When по типу совпадения + сходство имени);
        аннотируется ДО фильтра. Ordering задаётся здесь же при len(q) >= 2,
        чтобы во view не было ссылки на _rank, которой может не быть.
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
        return (
            queryset.annotate(_rank=rank)
            .filter(
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
            .order_by("-_rank", "name", "id")
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
