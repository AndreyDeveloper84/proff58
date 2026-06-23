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

from django.db.models import Count, FloatField, Max, Min, Q
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast

from .brand_slugs import build_brand_slug_map
from .filters import filtered_products
from .models import Attribute, AttributeOption, AttributeType, StockStatus
from .queries import _category_filter_attributes

# --- Лимиты фасетного эндпоинта (публичный AllowAny) ---
MAX_ATTR_FILTERS = 20
MAX_VALUES_PER_ATTR = 50
MAX_VALUE_LENGTH = 255
MAX_FACET_VALUES = 100
MAX_BRAND_FACETS = 50

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


def _option_slug_maps(attr_ids) -> dict[int, dict]:
    """Карты опций select/multiselect ОДНИМ запросом (без N+1).

    ``{attr_id: {"slug_to_value", "value_to_slug", "value_to_sort"}}``:
      * ``slug_to_value`` — непустой slug опции → её raw value (slug→value резолв URL);
      * ``value_to_slug`` — raw value → непустой slug (эмиссия slug в фасетах);
      * ``value_to_sort`` — raw value → sort_order (сортировка значений).
    """
    maps: dict[int, dict] = {}
    if not attr_ids:
        return maps
    for opt in AttributeOption.objects.filter(attribute_id__in=attr_ids):
        m = maps.setdefault(
            opt.attribute_id,
            {"slug_to_value": {}, "value_to_slug": {}, "value_to_sort": {}},
        )
        m["value_to_sort"][opt.value] = opt.sort_order
        if opt.slug:
            m["slug_to_value"][opt.slug] = opt.value
            m["value_to_slug"][opt.value] = opt.slug
    return maps


def _resolve_tokens(slug_to_value: dict, raw_tokens) -> list:
    """slug|raw → canonical storage value, дедуп с сохранением порядка.

    Приоритет: токен совпал со slug опции → её value; иначе токен как есть (raw value
    или неизвестный токен — containment по нему просто ничего не найдёт, без падения).
    """
    out: list = []
    seen: set = set()
    for tok in raw_tokens:
        val = slug_to_value.get(tok, tok)
        if val not in seen:
            seen.add(val)
            out.append(val)
    return out


def resolve_attr_tokens(attribute, raw_tokens) -> list:
    """Публичный slug|raw → canonical value для SELECT (дедуп, порядок сохранён).

    Только для SELECT включён slug-маппинг; для прочих типов токены лишь дедуплицируются
    (коерсия по типу — отдельно в ``_coerce``). Делает свой запрос опций для одного
    атрибута; в горячих путях (build_facets/apply_product_attr_filters) используются
    предзагруженные ``_option_slug_maps``, чтобы не плодить запросы.
    """
    if attribute.attribute_type != AttributeType.SELECT:
        return _resolve_tokens({}, raw_tokens)
    maps = _option_slug_maps([attribute.id])
    return _resolve_tokens(maps.get(attribute.id, {}).get("slug_to_value", {}), raw_tokens)


def _apply_attr_filters(qs, coerced, exclude=None):
    """drill-down attr-фильтры через JSONB containment (GIN-ускоряемо). exclude — снять фильтр атрибута."""
    for slug, vals in coerced.items():
        if slug == exclude:
            continue
        if not vals:
            return qs.none()
        qs = qs.filter(reduce(operator.or_, (Q(attrs_cache__contains={slug: v}) for v in vals)))
    return qs


def _apply_attr_ranges(qs, ranges, exclude=None):
    """Числовой диапазон по EAV-значению из ``attrs_cache`` (INTEGER/DECIMAL).

    ``ranges``: ``{slug: (lo, hi)}`` (границы — float либо None). Сравнение через
    ``Cast(KeyTextTransform → FloatField)``: отсутствие ключа → NULL → товар отбрасывается,
    т.е. товары БЕЗ атрибута исключаются (containment этого не делал — он сравнивал значение,
    а не наличие). ``exclude`` — снять диапазон своего фасета (drill-down). Alias по индексу,
    чтобы slug с дефисами не ломал имя аннотации и диапазоны не конфликтовали между собой.
    """
    for i, (slug, (lo, hi)) in enumerate(ranges.items()):
        if slug == exclude or (lo is None and hi is None):
            continue
        alias = f"_rng_{i}"
        qs = qs.annotate(**{alias: Cast(KeyTextTransform(slug, "attrs_cache"), FloatField())})
        if lo is not None:
            qs = qs.filter(**{f"{alias}__gte": lo})
        if hi is not None:
            qs = qs.filter(**{f"{alias}__lte": hi})
    return qs


def _apply_price(qs, price_min, price_max):
    """Числовой фильтр цены (drill-down). None-границы игнорируются."""
    if price_min is not None:
        qs = qs.filter(price__gte=price_min)
    if price_max is not None:
        qs = qs.filter(price__lte=price_max)
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


def build_facets(
    category,
    *,
    brands=None,
    stock_status=None,
    attr_filters=None,
    attr_ranges=None,
    price_min=None,
    price_max=None,
) -> dict:
    """Фасеты категории со счётчиками (drill-down). attr_filters: {slug: [raw,...]}.

    ``attr_ranges``: ``{slug: (lo, hi)}`` — числовые диапазоны по EAV (INTEGER/DECIMAL),
    применяются ко всем срезам drill-down наравне с ``attr_filters``; для собственного
    числового фасета его диапазон исключается (иначе границы ползунка схлопнулись бы к выбору).

    Подсчёт — в PostgreSQL (GROUP BY по JSONB ``attrs_cache``), не в Python: на каждый
    фасет один индексируемый запрос (drill-down — со всеми фильтрами, кроме своего).
    Контракт ответа и смысл значений сохраняются. list/multiselect-значения в attrs_cache
    в этой версии не поддерживаются (containment `{slug: value}` не покроет массив).
    """
    attr_filters = attr_filters or {}
    attr_ranges = attr_ranges or {}
    if len(attr_filters) > MAX_ATTR_FILTERS:
        raise FacetError("Слишком много фильтров-характеристик")

    attributes = _category_filter_attributes(category)
    by_slug = {a.slug: a for a in attributes}

    # Диапазоны: только известные числовые атрибуты категории (прочее — игнор, без падения).
    ranges: dict[str, tuple] = {}
    for slug, bounds in attr_ranges.items():
        attr = by_slug.get(slug)
        if attr is None or attr.attribute_type not in (
            AttributeType.INTEGER,
            AttributeType.DECIMAL,
        ):
            continue
        ranges[slug] = (bounds[0], bounds[1])

    # Опции select/multiselect ОДНИМ запросом: сортировка + slug→value резолв + эмиссия slug.
    select_ids = [
        a.id
        for a in attributes
        if a.attribute_type in (AttributeType.SELECT, AttributeType.MULTISELECT)
    ]
    option_maps = _option_slug_maps(select_ids)

    # Приведение attr-фильтров: unknown → игнор, invalid known → FacetError.
    # SELECT: slug|raw → canonical storage value (slug-URL, P2). Прочие типы → _coerce под
    # тип в attrs_cache (JSONB containment: {"voltage":18} ≠ {"voltage":"18"}).
    coerced: dict[str, list] = {}
    for slug, raw_values in attr_filters.items():
        attr = by_slug.get(slug)
        if attr is None:
            continue
        if len(raw_values) > MAX_VALUES_PER_ATTR:
            raise FacetError(f"Слишком много значений для «{slug}»")
        for raw in raw_values:
            if len(raw) > MAX_VALUE_LENGTH:
                raise FacetError("Слишком длинное значение фильтра")
        if attr.attribute_type == AttributeType.SELECT:
            slug_to_value = option_maps.get(attr.id, {}).get("slug_to_value", {})
            coerced[slug] = _resolve_tokens(slug_to_value, raw_values)
        else:
            coerced[slug] = [_coerce(raw, attr.attribute_type) for raw in raw_values]

    # Бренд: входящие токены (slug|raw) → канонический Product.brand (dual-accept, P-полировка).
    # Глобальная карта (все видимые бренды) — один запрос; brand_to_slug для эмиссии value=slug.
    brand_slug_to_brand, brand_to_slug = build_brand_slug_map()
    resolved_brands = None
    if brands:
        resolved_brands = []
        _seen_brand: set = set()
        for tok in brands:
            b = brand_slug_to_brand.get(tok, tok)
            if b not in _seen_brand:
                _seen_brand.add(b)
                resolved_brands.append(b)

    # base_bs — category+brand+stock (без цены); base_qs — ещё и +price (drill-down для attr/total).
    base_bs = filtered_products(category, brands=resolved_brands, stock_status=stock_status)
    base_qs = _apply_price(base_bs, price_min, price_max)
    total = _apply_attr_ranges(_apply_attr_filters(base_qs, coerced), ranges).count()

    facets = []
    for attr in attributes:
        # GROUP BY по значению атрибута в выборке с активными фильтрами, КРОМЕ своего
        # (и checkbox-, и range-измерение своего фасета исключаем — drill-down).
        rows = (
            _apply_attr_ranges(
                _apply_attr_filters(base_qs, coerced, exclude=attr.slug), ranges, exclude=attr.slug
            )
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

        # selected — ПОСЛЕ slug→value резолва (coerced уже в canonical value): иначе при
        # ?attr_=<slug> чекбокс не подсветился бы (значение фасета — raw value из attrs_cache).
        selected = set(coerced.get(attr.slug, []))
        amap = option_maps.get(attr.id, {})
        value_to_slug = amap.get("value_to_slug", {})
        is_select = attr.attribute_type == AttributeType.SELECT
        ordered = _sort_facet_values(attr, counter, amap.get("value_to_sort", {}))
        values = []
        for v, n in ordered[:MAX_FACET_VALUES]:
            # value = raw canonical storage value (из attrs_cache); slug = preferred URL token
            # (только при заполненном AttributeOption.slug, только SELECT); label на фронте = value.
            entry = {"value": v, "count": n, "selected": v in selected}
            if is_select:
                slug_token = value_to_slug.get(v)
                if slug_token:
                    entry["slug"] = slug_token
            values.append(entry)
        facets.append(
            {
                "slug": attr.slug,
                "name": attr.name,
                "type": attr.attribute_type,
                "unit": attr.unit,
                "values": values,
            }
        )

    # --- price/brand/stock фасеты: drill-down (каждый БЕЗ собственного измерения) ---
    # price: база БЕЗ price (category+brand+stock+attrs), только товары с ценой.
    pa = (
        _apply_attr_ranges(_apply_attr_filters(base_bs, coerced), ranges)
        .filter(price__isnull=False)
        .aggregate(lo=Min("price"), hi=Max("price"))
    )
    price = {
        "min": float(pa["lo"]) if pa["lo"] is not None else None,
        "max": float(pa["hi"]) if pa["hi"] is not None else None,
    }
    # brands: база БЕЗ brand (category+stock+price+attrs), один group-by.
    brand_base = _apply_attr_ranges(
        _apply_attr_filters(
            _apply_price(
                filtered_products(category, brands=None, stock_status=stock_status),
                price_min,
                price_max,
            ),
            coerced,
        ),
        ranges,
    )
    selected_brands = {b.lower() for b in (resolved_brands or [])}
    brands_out = [
        {
            "value": brand_to_slug.get(r["brand"], r["brand"]),
            "label": r["brand"],
            "count": r["c"],
            "selected": r["brand"].lower() in selected_brands,
        }
        for r in brand_base.exclude(brand="")
        .values("brand")
        .annotate(c=Count("id"))
        .order_by("-c", "brand")[:MAX_BRAND_FACETS]
    ]
    # stock: база БЕЗ stock (category+brand+price+attrs), один group-by.
    stock_base = _apply_attr_ranges(
        _apply_attr_filters(
            _apply_price(
                filtered_products(category, brands=resolved_brands, stock_status=None),
                price_min,
                price_max,
            ),
            coerced,
        ),
        ranges,
    )
    stock_labels = dict(StockStatus.choices)
    stock_out = [
        {
            "value": r["stock_status"],
            "label": str(stock_labels.get(r["stock_status"], r["stock_status"])),
            "count": r["c"],
            "selected": r["stock_status"] == stock_status,
        }
        for r in stock_base.values("stock_status").annotate(c=Count("id")).order_by("-c")
    ]

    return {
        "category": {
            "name": category.name,
            "slug": category.slug,
            "description": getattr(category, "description", "") or "",
            "breadcrumb": [{"name": c.name, "slug": c.slug} for c in category.get_ancestors()]
            + [{"name": category.name, "slug": category.slug}],
        },
        "subcategories": [
            {"name": c.name, "slug": c.slug} for c in category.get_children().filter(is_active=True)
        ],
        "price": price,
        "brands": brands_out,
        "stock": stock_out,
        "total_products": total,
        "applied_filters": {
            "brands": list(brands or []),
            "stock_status": stock_status or None,
            "attrs": coerced,
            "attr_ranges": {s: list(b) for s, b in ranges.items()},
        },
        "facets": facets,
    }


def apply_product_attr_filters(
    qs, attr_filters: dict[str, list[str]], attr_ranges: dict[str, tuple] | None = None
):
    """Отфильтровать список товаров по EAV-атрибутам — ТЕМ ЖЕ механизмом, что фасеты.

    ``attr_filters``: ``{slug: [raw, ...]}`` — как разбирает ``CategoryFacetsView`` из
    параметров ``attr_<slug>``. Семантика: OR внутри одного атрибута, AND между разными.
    ``attr_ranges``: ``{slug: (lo, hi)}`` — числовые диапазоны (INTEGER/DECIMAL) из
    ``attr_<slug>_min|_max``; через тот же ``_apply_attr_ranges``, что и фасеты, поэтому
    список товаров и счётчики совпадают, а товары без атрибута исключаются.
    Неизвестный/нефильтруемый slug, пустые и неприводимые значения игнорируются (листинг
    не должен падать на мусоре в URL). Значения коерсятся по типу атрибута (как в
    ``build_facets``) — иначе JSONB containment не совпадёт ({"voltage":18} ≠ {"voltage":"18"})
    и список разойдётся со счётчиками фасетов.
    """
    attr_filters = attr_filters or {}
    attr_ranges = attr_ranges or {}
    if not attr_filters and not attr_ranges:
        return qs
    all_slugs = list({*attr_filters, *attr_ranges})
    by_slug = {a.slug: a for a in Attribute.objects.filter(slug__in=all_slugs, is_filterable=True)}
    select_ids = [a.id for a in by_slug.values() if a.attribute_type == AttributeType.SELECT]
    option_maps = _option_slug_maps(select_ids)
    coerced: dict[str, list] = {}
    for slug, raw_values in attr_filters.items():
        attr = by_slug.get(slug)
        if attr is None:
            continue
        if attr.attribute_type == AttributeType.SELECT:
            # SELECT: slug|raw → canonical value (slug-URL, P2); unknown токен → как есть (0 товаров).
            slug_to_value = option_maps.get(attr.id, {}).get("slug_to_value", {})
            vals = _resolve_tokens(slug_to_value, [r for r in raw_values if r])
        else:
            vals = []
            for raw in raw_values:
                if not raw:
                    continue
                try:
                    vals.append(_coerce(raw, attr.attribute_type))
                except FacetError:
                    continue  # битое значение игнорируем, а не роняем листинг
        if vals:
            coerced[slug] = vals
    # Диапазоны: только известные числовые атрибуты (прочее — игнор, без падения листинга).
    ranges: dict[str, tuple] = {}
    for slug, bounds in attr_ranges.items():
        attr = by_slug.get(slug)
        if attr is None or attr.attribute_type not in (
            AttributeType.INTEGER,
            AttributeType.DECIMAL,
        ):
            continue
        ranges[slug] = (bounds[0], bounds[1])
    return _apply_attr_ranges(_apply_attr_filters(qs, coerced), ranges)
