"""Фасетные фильтры (#25) — read-слой поверх attrs_cache.

Фасеты категории со счётчиками (drill-down). Подсчёт — в PostgreSQL
(GROUP BY по JSONB ``attrs_cache``), не в Python.

Общий хелпер ``_category_filter_attributes`` живёт в ``queries`` и импортируется
сюда (направление facets → queries; обратной зависимости нет — цикла не возникает).
"""

from __future__ import annotations

import operator
from collections import Counter
from functools import reduce

from django.db.models import Count, Q
from django.db.models.fields.json import KeyTextTransform

from .filters import filtered_products
from .models import AttributeOption, AttributeType
from .queries import _category_filter_attributes

# --- Лимиты фасетного эндпоинта (публичный AllowAny) ---
MAX_ATTR_FILTERS = 20
MAX_VALUES_PER_ATTR = 50
MAX_VALUE_LENGTH = 255
MAX_FACET_VALUES = 100

_BOOL_TRUE = {"true", "1", "yes", "да"}
_BOOL_FALSE = {"false", "0", "no", "нет"}


class FacetError(ValueError):
    """Невалидный фасетный запрос — транслируется во view в HTTP 400."""


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


def _apply_attr_filters(qs, coerced, exclude=None):
    """drill-down attr-фильтры через JSONB containment (GIN-ускоряемо). exclude — снять фильтр атрибута."""
    for slug, vals in coerced.items():
        if slug == exclude:
            continue
        if not vals:
            return qs.none()
        qs = qs.filter(reduce(operator.or_, (Q(attrs_cache__contains={slug: v}) for v in vals)))
    return qs


def _cast_facet_value(text, attr_type):
    """Текст из ``->>'slug'`` (KeyTextTransform) → типизированное значение по типу атрибута."""
    if attr_type == AttributeType.INTEGER:
        return int(text)
    if attr_type == AttributeType.DECIMAL:
        return float(text)
    if attr_type == AttributeType.BOOLEAN:
        return text == "true"
    return text  # text / select


def build_facets(category, *, brands=None, stock_status=None, attr_filters=None) -> dict:
    """Фасеты категории со счётчиками (drill-down). attr_filters: {slug: [raw,...]}.

    Подсчёт — в PostgreSQL (GROUP BY по JSONB ``attrs_cache``), не в Python: на каждый
    фасет один индексируемый запрос (drill-down — со всеми фильтрами, кроме своего).
    Контракт ответа и смысл значений сохраняются. list/multiselect-значения в attrs_cache
    в этой версии не поддерживаются (containment `{slug: value}` не покроет массив).
    """
    attr_filters = attr_filters or {}
    if len(attr_filters) > MAX_ATTR_FILTERS:
        raise FacetError("Слишком много фильтров-характеристик")

    attributes = _category_filter_attributes(category)
    by_slug = {a.slug: a for a in attributes}

    # Приведение attr-фильтров: unknown → игнор, invalid known → FacetError.
    # _coerce даёт ТИП, лежащий в attrs_cache (int/float/bool/str) — это нужно для
    # JSONB containment ({"voltage":18} ≠ {"voltage":"18"}).
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

    base_qs = filtered_products(category, brands=brands, stock_status=stock_status)
    total = _apply_attr_filters(base_qs, coerced).count()

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
        # GROUP BY по значению атрибута в выборке с активными фильтрами, КРОМЕ своего.
        rows = (
            _apply_attr_filters(base_qs, coerced, exclude=attr.slug)
            .annotate(_fv=KeyTextTransform(attr.slug, "attrs_cache"))
            .filter(_fv__isnull=False)  # ключ есть и значение не JSON null (== старое None→skip)
            .values("_fv")
            .annotate(c=Count("id"))
        )
        counter: Counter = Counter()
        for row in rows:
            counter[_cast_facet_value(row["_fv"], attr.attribute_type)] = row["c"]
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
