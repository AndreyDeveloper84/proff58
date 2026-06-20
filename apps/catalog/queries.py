"""Запросы каталога: товары поддерева, счётчики, range-фильтры, tool_type-фасеты.

Контракт каталога для витрины и других модулей (ADR-0004: только через services).
Здесь же живут общие приватные хелперы ``_subtree_ids`` и
``_category_filter_attributes`` — модуль не зависит от facets, поэтому импорт
``facets → queries`` не создаёт цикла.
"""

from __future__ import annotations

from django.db.models import Count, Q

from .models import (
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
)

TOOL_TYPE_SLUG = "tool_type"


def _subtree_ids(category: Category) -> list[int]:
    return [category.pk, *category.get_descendants().values_list("pk", flat=True)]


def _category_filter_attributes(category) -> list:
    """Фильтруемые характеристики категории с наследованием от предков.

    Ближайшая категория переопределяет родителя; порядок вывода: текущая → выше
    по дереву, внутри — по sort_order.
    """
    ancestors = list(category.get_ancestors())  # от корня к родителю
    chain_ids = [category.pk, *[c.pk for c in reversed(ancestors)]]  # ближайшая первой
    pos = {pk: i for i, pk in enumerate(chain_ids)}

    best: dict[int, tuple] = {}  # attribute_id -> (pos, sort_order, attribute)
    qs = CategoryAttribute.objects.filter(
        category_id__in=chain_ids, attribute__is_filterable=True
    ).select_related("attribute")
    for ca in qs:
        key = (pos[ca.category_id], ca.sort_order)
        if ca.attribute_id not in best or key < best[ca.attribute_id][:2]:
            best[ca.attribute_id] = (pos[ca.category_id], ca.sort_order, ca.attribute)

    return [t[2] for t in sorted(best.values(), key=lambda t: (t[0], t[1]))]


def products_in(
    category: Category,
    *,
    tool_type=None,
    in_stock=False,
    published_only=False,
    attr_ranges=None,
):
    """Товары категории и всех её потомков с фильтрами витрины.

    ``tool_type`` — slug варианта атрибута tool_type (вторая ось навигации).
    ``in_stock`` — только с остатком > 0. ``published_only`` — для боевой витрины
    (на тестовой показываем и импортированные, не только опубликованные).
    ``attr_ranges`` — ``{slug: (min, max)}`` числовые диапазоны по EAV-значениям
    (#96, range-фильтры): обе границы по ОДНОМУ значению, поэтому каждый атрибут
    фильтруется отдельным ``filter()`` (иначе границы разъедутся по строкам EAV).
    """
    qs = Product.objects.filter(category_id__in=_subtree_ids(category))
    if published_only:
        from .models import ProductStatus

        qs = qs.filter(is_active=True, status=ProductStatus.PUBLISHED)
    if in_stock:
        qs = qs.filter(stock_quantity__gt=0)
    if tool_type:
        qs = qs.filter(
            attribute_values__attribute__slug=TOOL_TYPE_SLUG,
            attribute_values__value_option__slug=tool_type,
        )
    for slug, (lo, hi) in (attr_ranges or {}).items():
        conds = {"attribute_values__attribute__slug": slug}
        if lo is not None:
            conds["attribute_values__value_decimal__gte"] = lo
        if hi is not None:
            conds["attribute_values__value_decimal__lte"] = hi
        qs = qs.filter(**conds)
    return qs


def range_filter_attributes(category: Category) -> list[dict]:
    """Числовые диапазонные характеристики-фильтры категории (с наследованием).

    Backend-описание для range-фильтров (#96): slug/имя/единица. Вид фильтра
    выводим из типа атрибута (DECIMAL/INTEGER → диапазон), без отдельного поля.
    UI-ползунки — отдельная задача; здесь контракт, по которому витрина читает
    min/max из GET.
    """
    ancestors = list(category.get_ancestors())
    chain_ids = [category.pk, *[c.pk for c in ancestors]]
    seen: dict[str, dict] = {}
    qs = (
        CategoryAttribute.objects.filter(
            category_id__in=chain_ids,
            is_filter=True,
            attribute__is_filterable=True,
            attribute__attribute_type__in=[AttributeType.DECIMAL, AttributeType.INTEGER],
        )
        .select_related("attribute")
        .order_by("sort_order")
    )
    for ca in qs:
        seen.setdefault(
            ca.attribute.slug,
            {"slug": ca.attribute.slug, "name": ca.attribute.name, "unit": ca.attribute.unit},
        )
    return list(seen.values())


def category_counts(category: Category) -> dict:
    """Всего товаров и в наличии в поддереве категории."""
    agg = Product.objects.filter(category_id__in=_subtree_ids(category)).aggregate(
        total=Count("id"),
        in_stock=Count("id", filter=Q(stock_quantity__gt=0)),
    )
    return {"total": agg["total"] or 0, "in_stock": agg["in_stock"] or 0}


def tool_type_facets(category: Category) -> list[dict]:
    """Плитки tool_type для страницы категории: значение, slug, счётчик.

    Это «вторая ось»/фасет, как у конкурента: значения атрибута tool_type среди
    товаров поддерева. Пустой список — плиток нет.
    """
    rows = (
        ProductAttributeValue.objects.filter(
            attribute__slug=TOOL_TYPE_SLUG,
            value_option__isnull=False,
            product__category_id__in=_subtree_ids(category),
        )
        .values("value_option__value", "value_option__slug")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    return [
        {
            "value": r["value_option__value"],
            "slug": r["value_option__slug"],
            "count": r["count"],
        }
        for r in rows
    ]
