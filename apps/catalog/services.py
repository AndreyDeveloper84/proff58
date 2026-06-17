"""Сервисы каталога: денормализация EAV-характеристик в Product.attrs_cache.

`attrs_cache` — read-model `{slug_атрибута: значение}` для быстрых фасетов (#25)
и фильтров. Источник истины — `ProductAttributeValue`. Полная идемпотентная
пересборка из EAV (а не точечное обновление ключа).
"""

from __future__ import annotations

from collections import Counter

from .filters import filtered_products
from .models import (
    AttributeOption,
    AttributeType,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
)

# --- Лимиты фасетного эндпоинта (публичный AllowAny) ---
MAX_ATTR_FILTERS = 20
MAX_VALUES_PER_ATTR = 50
MAX_VALUE_LENGTH = 255
MAX_FACET_VALUES = 100

_BOOL_TRUE = {"true", "1", "yes", "да"}
_BOOL_FALSE = {"false", "0", "no", "нет"}


class FacetError(ValueError):
    """Невалидный фасетный запрос — транслируется во view в HTTP 400."""


def attr_value_to_json(pav: ProductAttributeValue):
    """JSON-safe значение характеристики по её типу.

    Decimal → float — намеренно и ТОЛЬКО для характеристик/фасетов (мощность, вес,
    диаметр и т.п.), не для денег: JSONField без encoder не умеет Decimal, а для
    числовых фильтров float достаточно.
    """
    t = pav.attribute.attribute_type
    if t == AttributeType.TEXT:
        return pav.value_text
    if t == AttributeType.INTEGER:
        return pav.value_integer
    if t == AttributeType.DECIMAL:
        return float(pav.value_decimal) if pav.value_decimal is not None else None
    if t == AttributeType.BOOLEAN:
        return pav.value_boolean
    if t in (AttributeType.SELECT, AttributeType.MULTISELECT):
        return pav.value_option.value if pav.value_option_id else None
    return None


def rebuild_attrs_cache(product: Product) -> dict:
    """Пересобрать Product.attrs_cache из EAV-значений. Идемпотентно."""
    cache: dict = {}
    for pav in product.attribute_values.select_related("attribute", "value_option"):
        value = attr_value_to_json(pav)
        # Пустые значения не кладём; boolean False — валидное значение, сохраняем.
        if value is not None and value != "":
            cache[pav.attribute.slug] = value
    product.attrs_cache = cache
    product.save(update_fields=["attrs_cache"])
    return cache


# ---------------------------------------------------------------------------
# Фасетные фильтры (#25) — read-слой поверх attrs_cache
# ---------------------------------------------------------------------------


def _coerce(raw: str, attr_type: str):
    """Привести строку запроса к типу значения в attrs_cache. Ошибка → FacetError."""
    if attr_type == AttributeType.INTEGER:
        try:
            return int(raw)
        except ValueError as exc:
            raise FacetError(f"Неверное целое значение: {raw!r}") from exc
    if attr_type == AttributeType.DECIMAL:
        try:
            return float(raw)
        except ValueError as exc:
            raise FacetError(f"Неверное числовое значение: {raw!r}") from exc
    if attr_type == AttributeType.BOOLEAN:
        v = raw.strip().lower()
        if v in _BOOL_TRUE:
            return True
        if v in _BOOL_FALSE:
            return False
        raise FacetError(f"Неверное булево значение: {raw!r}")
    return raw  # text / select / multiselect


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


def _sort_facet_values(attr, counter: Counter, options_order: dict) -> list:
    """Отсортировать (value, count). Возвращает список пар."""
    items = list(counter.items())
    t = attr.attribute_type
    if t in (AttributeType.SELECT, AttributeType.MULTISELECT):
        known = sorted(
            (it for it in items if it[0] in options_order),
            key=lambda it: (options_order[it[0]], str(it[0])),
        )
        unknown = sorted(
            (it for it in items if it[0] not in options_order),
            key=lambda it: str(it[0]),
        )
        return known + unknown
    if t in (AttributeType.INTEGER, AttributeType.DECIMAL):
        return sorted(items, key=lambda it: it[0])
    return sorted(items, key=lambda it: (-it[1], str(it[0])))  # text/boolean → по count


def build_facets(category, *, brands=None, stock_status=None, attr_filters=None) -> dict:
    """Фасеты категории со счётчиками (drill-down). attr_filters: {slug: [raw,...]}."""
    attr_filters = attr_filters or {}
    if len(attr_filters) > MAX_ATTR_FILTERS:
        raise FacetError("Слишком много фильтров-характеристик")

    attributes = _category_filter_attributes(category)
    by_slug = {a.slug: a for a in attributes}

    # Приведение attr-фильтров: unknown → игнор, invalid known → FacetError.
    coerced: dict[str, list] = {}
    for slug, raw_values in attr_filters.items():
        attr = by_slug.get(slug)
        if attr is None:
            continue
        if len(raw_values) > MAX_VALUES_PER_ATTR:
            raise FacetError(f"Слишком много значений для «{slug}»")
        vals = []
        for raw in raw_values:
            if len(raw) > MAX_VALUE_LENGTH:
                raise FacetError("Слишком длинное значение фильтра")
            vals.append(_coerce(raw, attr.attribute_type))
        coerced[slug] = vals

    rows = list(
        filtered_products(category, brands=brands, stock_status=stock_status).values_list(
            "attrs_cache", flat=True
        )
    )

    def _match(cache: dict, exclude: str | None = None) -> bool:
        for slug, vals in coerced.items():
            if slug == exclude:
                continue
            cur = cache.get(slug)
            if isinstance(cur, list):
                if not set(cur) & set(vals):
                    return False
            elif cur not in vals:
                return False
        return True

    total = sum(1 for c in rows if _match(c))

    # Опции select/multiselect одним запросом — для сортировки значений.
    select_ids = [
        a.id
        for a in attributes
        if a.attribute_type in (AttributeType.SELECT, AttributeType.MULTISELECT)
    ]
    options_by_attr: dict[int, dict] = {}
    if select_ids:
        for opt in AttributeOption.objects.filter(attribute_id__in=select_ids):
            options_by_attr.setdefault(opt.attribute_id, {})[opt.value] = opt.sort_order

    facets = []
    for attr in attributes:
        counter: Counter = Counter()
        for cache in rows:
            if not _match(cache, exclude=attr.slug):
                continue
            value = cache.get(attr.slug)
            if value is None:
                continue
            if isinstance(value, list):
                counter.update(value)
            else:
                counter[value] += 1
        if not counter:
            continue  # пустой фасет не отдаём

        selected = set(coerced.get(attr.slug, []))
        ordered = _sort_facet_values(attr, counter, options_by_attr.get(attr.id, {}))
        facets.append(
            {
                "slug": attr.slug,
                "name": attr.name,
                "type": attr.attribute_type,
                "unit": attr.unit,
                "values": [
                    {"value": v, "count": n, "selected": v in selected}
                    for v, n in ordered[:MAX_FACET_VALUES]
                ],
            }
        )

    return {
        "category": category.slug,
        "total_products": total,
        "applied_filters": {
            "brands": list(brands or []),
            "stock_status": stock_status or None,
            "attrs": coerced,
        },
        "facets": facets,
    }
