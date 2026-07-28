"""Запросы каталога: товары поддерева, счётчики, range-фильтры, tool_type-фасеты.

Контракт каталога для витрины и других модулей (ADR-0004: только через services).
Здесь же живут общие приватные хелперы ``_subtree_ids`` и
``_category_filter_attributes`` — модуль не зависит от facets, поэтому импорт
``facets → queries`` не создаёт цикла.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Count, Prefetch, Q

from .models import (
    AttributeType,
    Category,
    CategoryAttribute,
    CompatibilityKind,
    Product,
    ProductAttributeValue,
    ProductCompatibility,
    ProductStatus,
)

TOOL_TYPE_SLUG = "tool_type"


def _attrs_prefetch(rel: str) -> Prefetch:
    """Prefetch характеристик связанного товара (specs в карточках секций совместимости)."""
    return Prefetch(
        f"{rel}__attribute_values",
        queryset=ProductAttributeValue.objects.select_related("attribute", "value_option"),
    )


def _subtree_ids(category: Category) -> list[int]:
    return [category.pk, *category.get_descendants().values_list("pk", flat=True)]


def _category_filter_attributes(category) -> list:
    """Фильтруемые характеристики категории с наследованием от предков.

    Ближайшая категория переопределяет родителя; порядок вывода: текущая → выше
    по дереву, внутри — по sort_order.

    Гейт состава (§10.2, §22.3): глобальный ``Attribute.is_filterable=True`` И per-category
    ``CategoryAttribute.is_filter=True`` — куратор может выключить конкретный атрибут как
    фильтр для конкретной категории. ``is_filter`` имеет default=True, поэтому существующее
    поведение не меняется. Согласовано с ``range_filter_attributes`` (тот же двойной гейт).

    Известное ограничение: гейт — это WHERE по всей цепочке, НЕ closest-wins по самому
    флагу. Строки с is_filter=False выпадают из выборки ДО разрешения «ближайшая
    переопределяет родителя», поэтому если у листа is_filter=False, но у предка для ТОГО
    ЖЕ атрибута is_filter=True — атрибут всё равно попадёт (из строки предка). Override
    уровня флага между уровнями намеренно не поддержан (§22.3, простой WHERE по ТЗ).

    Замечание про tool_type: build_facets эмитит TypePanel (навигацию) из этого же
    гейтнутого списка (``by_slug.get("tool_type")``). Значит is_filter=False на строке
    CategoryAttribute для tool_type скроет нав-панель целиком. Под default (True) панель
    цела; долгосрочно навигацию стоит эмитить независимо от is_filter (см. §10.1 ui_placement).
    """
    ancestors = list(category.get_ancestors())  # от корня к родителю
    chain_ids = [category.pk, *[c.pk for c in reversed(ancestors)]]  # ближайшая первой
    pos = {pk: i for i, pk in enumerate(chain_ids)}

    best: dict[int, tuple] = {}  # attribute_id -> (pos, sort_order, attribute, group, display_name)
    qs = CategoryAttribute.objects.filter(
        category_id__in=chain_ids, is_filter=True, attribute__is_filterable=True
    ).select_related("attribute")
    for ca in qs:
        key = (pos[ca.category_id], ca.sort_order)
        if ca.attribute_id not in best or key < best[ca.attribute_id][:2]:
            best[ca.attribute_id] = (
                pos[ca.category_id],
                ca.sort_order,
                ca.attribute,
                ca.group,
                ca.display_name,
            )

    # Группу фасета (D1, §22.4) и переопределение подписи берём из той же ближайшей строки
    # CategoryAttribute, что выиграла closest-wins по (pos, sort_order) — кладём транзиентно
    # на Attribute, чтобы не менять тип возврата (список Attribute) и не плодить запросы.
    # Потребители, которым они не нужны (coverage_report, range_filter_attributes), их просто
    # игнорируют. Пустой display_name → fallback на Attribute.name у потребителя.
    ordered = sorted(best.values(), key=lambda t: (t[0], t[1]))
    result = []
    for _pos, _sort_order, attribute, group, display_name in ordered:
        attribute._facet_group = group
        attribute._display_name = display_name
        result.append(attribute)
    return result


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


# ---------------------------------------------------------------------------
# Совместимость товаров (#79): резолверы каталожных связей товар↔товар
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompatibilityItem:
    """Элемент секции совместимости: связанный товар + метаданные ребра."""

    product: Product
    note: str
    sort_order: int


def accessories_of(product: Product) -> list[CompatibilityItem]:
    """Аксессуары/оснастка/расходники К товару (ребра ACCESSORY, product=source).

    Только видимые товары-аксессуары (is_active + PUBLISHED), порядок —
    sort_order, затем id.
    """
    edges = (
        ProductCompatibility.objects.filter(
            source=product,
            kind=CompatibilityKind.ACCESSORY,
            target__is_active=True,
            target__status=ProductStatus.PUBLISHED,
        )
        .select_related("target", "target__category")
        .prefetch_related("target__images", _attrs_prefetch("target"))
        .order_by("sort_order", "id")
    )
    return [
        CompatibilityItem(product=e.target, note=e.note, sort_order=e.sort_order) for e in edges
    ]


def fits_of(product: Product) -> list[CompatibilityItem]:
    """Товары, К КОТОРЫМ подходит данный аксессуар (ACCESSORY, product=target).

    Обратное направление accessories_of: для аксессуара показываем инструменты,
    к которым он подходит. Только видимые источники.
    """
    edges = (
        ProductCompatibility.objects.filter(
            target=product,
            kind=CompatibilityKind.ACCESSORY,
            source__is_active=True,
            source__status=ProductStatus.PUBLISHED,
        )
        .select_related("source", "source__category")
        .prefetch_related("source__images", _attrs_prefetch("source"))
        .order_by("sort_order", "id")
    )
    return [
        CompatibilityItem(product=e.source, note=e.note, sort_order=e.sort_order) for e in edges
    ]


def compatible_of(product: Product) -> list[CompatibilityItem]:
    """Симметрично совместимые товары (COMPATIBLE; product как source ИЛИ target).

    Ребро хранится канонически, поэтому ищем по обоим концам. Видимость второго
    конца проверяем в Python (is_visible), т.к. он может быть и source, и target.
    Дедуп по other.id (сохраняем первый встреченный порядок).
    """
    edges = (
        ProductCompatibility.objects.filter(
            Q(source=product) | Q(target=product),
            kind=CompatibilityKind.COMPATIBLE,
        )
        .select_related("source", "target", "source__category", "target__category")
        .prefetch_related(
            "source__images", "target__images", _attrs_prefetch("source"), _attrs_prefetch("target")
        )
        .order_by("sort_order", "id")
    )
    items: list[CompatibilityItem] = []
    seen: set[int] = set()
    for e in edges:
        other = e.target if e.source_id == product.id else e.source
        if not other.is_visible:
            continue
        if other.id in seen:
            continue
        seen.add(other.id)
        items.append(CompatibilityItem(product=other, note=e.note, sort_order=e.sort_order))
    return items


def compatibility_sections(product: Product) -> dict[str, list[CompatibilityItem]]:
    """Три секции совместимости товара одним вызовом."""
    return {
        "accessories": accessories_of(product),
        "fits": fits_of(product),
        "compatible": compatible_of(product),
    }
