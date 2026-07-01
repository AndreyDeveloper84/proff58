"""Фасетные фильтры (#25) — read-слой поверх attrs_cache.

Фасеты категории со счётчиками (drill-down). Подсчёт — в PostgreSQL
(GROUP BY по JSONB ``attrs_cache``), не в Python.

Общий хелпер ``_category_filter_attributes`` живёт в ``queries`` и импортируется
сюда (направление facets → queries; обратной зависимости нет — цикла не возникает).
"""

from __future__ import annotations

import hashlib
import json
import operator
from collections import Counter
from functools import reduce

from django.conf import settings
from django.core.cache import cache as cache_store
from django.db.models import Case, Count, FloatField, Max, Min, Q, Value, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Lower

from .brand_slugs import build_brand_slug_map
from .filters import filtered_products
from .models import Attribute, AttributeOption, AttributeType, FacetGroup, StockStatus
from .queries import TOOL_TYPE_SLUG, _category_filter_attributes, _subtree_ids

# --- Лимиты фасетного эндпоинта (публичный AllowAny) ---
MAX_ATTR_FILTERS = 20
MAX_VALUES_PER_ATTR = 50
MAX_VALUE_LENGTH = 255
MAX_FACET_VALUES = 100
MAX_BRAND_FACETS = 50

_BOOL_TRUE = {"true", "1", "yes", "да"}
_BOOL_FALSE = {"false", "0", "no", "нет"}

# Числовой литерал для guarded-каста диапазонов (целое/десятичное, опц. минус). POSIX-regex
# Postgres (lookup ``__regex`` → ``~``). Нечисловая строка под числовым атрибутом не должна
# ронять запрос в DataError → CASE кастит только прошедшие этот гард (см. _apply_attr_ranges).
_NUMERIC_RE = r"^-?[0-9]+(\.[0-9]+)?$"


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
        # D3 (§22.4 «сортирует значения»): кураторский ``sort_order`` — главный ключ; при
        # равных (по дефолту все 0, т.е. опции не упорядочены вручную) — по убыванию count
        # (популярные сверху), затем по label для детерминизма. Так упорядоченные опции
        # сохраняют заданный порядок, а неупорядоченные деградируют к «по популярности», а
        # не к алфавиту. ``unknown`` (значения без AttributeOption) — сразу по count.
        known = sorted(
            (it for it in items if it[0] in options_order),
            key=lambda it: (options_order[it[0]], -it[1], str(it[0])),
        )
        unknown = sorted(
            (it for it in items if it[0] not in options_order),
            key=lambda it: (-it[1], str(it[0])),
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

    Guarded cast: голый ``::float`` падал бы с DataError (→ HTTP 500 на публичном AllowAny
    эндпоинте), если у товара под числовым атрибутом в кэше лежит нечисловая строка
    (рассинхрон пайплайна импорта, ручная правка). ``CASE`` гарантирует, что ``Cast``
    выполняется ТОЛЬКО для значений, прошедших ``_NUMERIC_RE``; прочее → NULL → товар
    отбрасывается (та же семантика, что и отсутствие ключа).
    """
    for i, (slug, (lo, hi)) in enumerate(ranges.items()):
        if slug == exclude or (lo is None and hi is None):
            continue
        txt = f"_rngtxt_{i}"
        alias = f"_rng_{i}"
        qs = qs.annotate(**{txt: KeyTextTransform(slug, "attrs_cache")})
        qs = qs.annotate(
            **{
                alias: Case(
                    When(
                        **{f"{txt}__regex": _NUMERIC_RE},
                        then=Cast(KeyTextTransform(slug, "attrs_cache"), FloatField()),
                    ),
                    default=Value(None),
                    output_field=FloatField(),
                )
            }
        )
        if lo is not None:
            qs = qs.filter(**{f"{alias}__gte": lo})
        if hi is not None:
            qs = qs.filter(**{f"{alias}__lte": hi})
    return qs


def _apply_tool_type(qs, slug):
    """Навигация по типу инструмента — relational EAV (как ``ProductFilter.filter_tool_type``).

    Намеренно НЕ через attrs_cache-containment: список товаров фильтрует `tool_type`
    relational-механизмом (``attribute_values__value_option__slug``), и фасеты обязаны
    сужаться ТЕМ ЖЕ способом, иначе list и facets разойдутся. Пусто/None → без фильтра.
    Связь 1:1 (SELECT, один value_option на товар) — джойн не дублирует строки.
    """
    if not slug:
        return qs
    return qs.filter(
        attribute_values__attribute__slug=TOOL_TYPE_SLUG,
        attribute_values__value_option__slug=slug,
    )


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


def _build_tool_type_panel(panel_base, tt_attr, selected_slug):
    """TypePanel: GROUP BY value_option на own-axis базе (без tool_type), один запрос.

    ``panel_base`` уже несёт brand/stock/price/attr, но НЕ tool_type — панель показывает
    все типы со счётчиками, чтобы можно было переключиться (§13). Поля значения:
    ``{value, slug, count, selected}``; порядок — ``value_option.sort_order``, затем
    ``-count``, затем ``slug`` (детерминизм при равных счётчиках).

    ``Count("id")`` без distinct: JOIN сужен фильтром до ОДНОЙ tool_type-строки на товар
    (``unique_together(product, attribute)`` в ``ProductAttributeValue``), поэтому
    инфляции нет — ровно как в ``ProductFilter.filter_tool_type``, чтобы панель и список
    считались одинаково. Пусто → ``None`` (панель не отдаём, как и пустой обычный фасет).
    """
    opt = "attribute_values__value_option"
    values = [
        {
            "value": r[f"{opt}__value"],
            "slug": r[f"{opt}__slug"],
            "count": r["c"],
            "selected": r[f"{opt}__slug"] == selected_slug,
        }
        for r in (
            panel_base.filter(
                attribute_values__attribute__slug=TOOL_TYPE_SLUG,
                **{f"{opt}__isnull": False},
            )
            .values(f"{opt}__slug", f"{opt}__value", f"{opt}__sort_order")
            .annotate(c=Count("id"))
            .order_by(f"{opt}__sort_order", "-c", f"{opt}__slug")[:MAX_FACET_VALUES]
        )
    ]
    if not values:
        return None
    return {
        "slug": tt_attr.slug,
        "name": tt_attr.name,
        "type": tt_attr.attribute_type,
        "unit": tt_attr.unit,
        "is_nav": True,
        "values": values,
    }


def build_facets(
    category,
    *,
    tool_type=None,
    brands=None,
    stock_status=None,
    attr_filters=None,
    attr_ranges=None,
    price_min=None,
    price_max=None,
) -> dict:
    """Фасеты категории со счётчиками (drill-down). attr_filters: {slug: [raw,...]}.

    ``tool_type`` (slug опции) — НАВИГАЦИЯ по типу инструмента (панель над выдачей,
    а не сайдбар-фасет). Сужает все срезы relational-механизмом (как
    ``ProductFilter.filter_tool_type``), поэтому список товаров и фасеты совпадают.
    Сам `tool_type` эмитится отдельной панелью с ``is_nav=True`` и own-axis exclude:
    панель показывает ВСЕ типы со счётчиками (свою ось не фильтрует), но учитывает
    brand/stock/price/attr. Прочие фасеты получают ``is_nav=False``.

    ``attr_ranges``: ``{slug: (lo, hi)}`` — числовые диапазоны по EAV (INTEGER/DECIMAL),
    применяются ко всем срезам drill-down наравне с ``attr_filters``; для собственного
    числового фасета его диапазон исключается (иначе границы ползунка схлопнулись бы к выбору).

    Подсчёт — в PostgreSQL (GROUP BY по JSONB ``attrs_cache``, для tool_type — по
    ``value_option``), не в Python: на каждый фасет один индексируемый запрос (drill-down —
    со всеми фильтрами, кроме своего). Контракт ответа и смысл значений сохраняются.
    list/multiselect-значения в attrs_cache в этой версии не поддерживаются (containment
    `{slug: value}` не покроет массив).
    """
    attr_filters = attr_filters or {}
    attr_ranges = attr_ranges or {}
    tool_type = tool_type or None  # "" → None (нет фильтра) один раз, дальше единообразно
    if len(attr_filters) > MAX_ATTR_FILTERS:
        raise FacetError("Слишком много фильтров-характеристик")

    attributes = _category_filter_attributes(category)
    by_slug = {a.slug: a for a in attributes}

    # Поддерево считаем ОДИН раз: drilldown() строит N+5 срезов на запрос фасетов, и без
    # этого get_descendants() бил бы в дерево на каждом (P1 ревью — лишние ~N запросов).
    subtree_ids = _subtree_ids(category)

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

    # Опции SELECT одним запросом. MULTISELECT исключён (#282): unique_together(product, attribute)
    # делает хранение нескольких значений невозможным — GROUP BY по attrs_cache даёт неверные
    # счётчики (агрегируется JSON-массив целиком, а не отдельные элементы).
    select_ids = [
        a.id
        for a in attributes
        if a.attribute_type == AttributeType.SELECT
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

    # Единая сборка drill-down среза. Каждый «own-axis» фасет считается на базе со ВСЕМИ
    # активными фильтрами, КРОМЕ своей оси — её нейтрализуем kwarg-ом (brands=None /
    # stock_status=None / tool_type=None / price=False / exclude_attr=slug). Так «забыть
    # ось» на одном из срезов невозможно, и list/facets гарантированно согласованы.
    def drilldown(
        *,
        brands=resolved_brands,
        stock_status=stock_status,
        tool_type=tool_type,
        price=True,
        exclude_attr=None,
    ):
        qs = _apply_tool_type(
            filtered_products(
                category, brands=brands, stock_status=stock_status, subtree_ids=subtree_ids
            ),
            tool_type,
        )
        if price:
            qs = _apply_price(qs, price_min, price_max)
        qs = _apply_attr_filters(qs, coerced, exclude=exclude_attr)
        return _apply_attr_ranges(qs, ranges, exclude=exclude_attr)

    total = drilldown().count()

    facets = []
    for attr in attributes:
        if attr.slug == TOOL_TYPE_SLUG:
            continue  # tool_type — навигация: эмитим отдельной панелью, не attrs_cache-фасетом
        if attr.attribute_type == AttributeType.MULTISELECT:
            continue  # MULTISELECT не поддерживается фасетами (#282): unique_together не позволяет хранить несколько значений
        # GROUP BY по значению атрибута в выборке с активными фильтрами, КРОМЕ своего
        # (и checkbox-, и range-измерение своего фасета исключаем — drill-down).
        rows = (
            drilldown(exclude_attr=attr.slug)
            .annotate(_fv=KeyTextTransform(attr.slug, "attrs_cache"))
            .filter(_fv__isnull=False)  # ключ есть и значение не JSON null (== старое None→skip)
            .values("_fv")
            .annotate(c=Count("id"))
        )
        counter: Counter = Counter()
        for row in rows:
            try:
                key = _cast_facet_value(row["_fv"], attr.attribute_type)
            except (ValueError, TypeError):
                # Нечисловой мусор под числовым атрибутом (рассинхрон кэша): пропускаем
                # значение, а не роняем весь ответ фасетов в 500 (парный гард к _apply_attr_ranges).
                continue
            counter[key] = row["c"]
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
                "is_nav": False,
                # Группа сайдбара (D1, §22.4): main|extra из ближайшей CategoryAttribute
                # (closest-wins, проброшено transient на Attribute). Дефолт — main.
                "group": getattr(attr, "_facet_group", FacetGroup.MAIN),
                "values": values,
            }
        )

    # --- TypePanel: навигационный фасет tool_type (own-axis exclude — без tool_type) ---
    tt_attr = by_slug.get(TOOL_TYPE_SLUG)
    if tt_attr is not None:
        panel = _build_tool_type_panel(drilldown(tool_type=None), tt_attr, tool_type)
        if panel is not None:
            facets.append(panel)

    # --- price/brand/stock фасеты: drill-down (каждый БЕЗ собственного измерения) ---
    # price: own-axis — без price (но с tool_type/brand/stock/attr), только товары с ценой.
    pa = (
        drilldown(price=False)
        .filter(price__isnull=False)
        .aggregate(lo=Min("price"), hi=Max("price"))
    )
    price = {
        "min": float(pa["lo"]) if pa["lo"] is not None else None,
        "max": float(pa["hi"]) if pa["hi"] is not None else None,
    }
    # brands: own-axis — без brand (category+stock+price+attrs+tool_type), один group-by.
    brand_base = drilldown(brands=None)
    selected_brands = {b.lower() for b in (resolved_brands or [])}
    # Группируем по Lower(brand): иначе «Bosch»/«BOSCH» дают раздельные счётчики,
    # тогда как фильтр товаров использует brand__iexact (объединяет) — сумма фасета
    # рассинхронизировалась бы со списком (#11). label — представитель регистра.
    brands_out = [
        {
            "value": brand_to_slug.get(r["label"], r["label"]),
            "label": r["label"],
            "count": r["c"],
            "selected": r["brand_lc"] in selected_brands,
        }
        for r in brand_base.exclude(brand="")
        .annotate(brand_lc=Lower("brand"))
        .values("brand_lc")
        .annotate(c=Count("id"), label=Max("brand"))
        .order_by("-c", "brand_lc")[:MAX_BRAND_FACETS]
    ]
    # stock: own-axis — без stock (category+brand+price+attrs+tool_type), один group-by.
    stock_base = drilldown(stock_status=None)
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
            "tool_type": tool_type,
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


# --- Кэш фасетов (#222, P1-2) ----------------------------------------------------------------
# build_facets пересобирает 2N+ индексируемых запросов на КАЖДЫЙ хит публичного (AllowAny)
# фасет-эндпоинта. Результат детерминирован по (категория, параметры) и меняется только при
# изменении данных каталога, поэтому кэшируем его (как get_category_tree). Ключей по
# (category, params) бесконечно много — перечислить и удалить их при инвалидации, как 2 ключа
# дерева, нельзя; поэтому инвалидация ВЕРСИОННАЯ: bump общей версии орфанит все старые ключи
# разом, а TTL добивает осиротевшие. Сигналы-издатели версии — в apps/catalog/signals.py
# (post_save/post_delete товаров/категорий/привязок), как и у дерева: ловит и 1С-обновления
# цены/остатка (они делают product.save()), не завися от наличия доменного издателя.
FACETS_CACHE_VERSION_KEY = "catalog:facets:version"


def _facets_cache_ttl() -> int:
    """TTL кэша фасетов (сек). <=0 → кэш выключен (dev/CI: тесты не зависят от кэша); прод
    включает через FACETS_CACHE_TTL (см. config/settings/prod.py)."""
    return getattr(settings, "FACETS_CACHE_TTL", 0)


def _facets_version() -> int:
    """Текущая версия кэша фасетов (часть ключа). Инициализируется в 1 без срока жизни."""
    v = cache_store.get(FACETS_CACHE_VERSION_KEY)
    if v is None:
        cache_store.set(FACETS_CACHE_VERSION_KEY, 1, None)  # счётчик версии не истекает
        return 1
    return v


def invalidate_facets_cache() -> None:
    """Версионная инвалидация: bump версии делает все ранее закэшированные (category, params)
    ключи недостижимыми (старые добиваются TTL). Зовётся из сигналов изменения данных каталога.
    No-op при выключенном кэше — не трогаем стор зря."""
    if _facets_cache_ttl() <= 0:
        return
    try:
        cache_store.incr(FACETS_CACHE_VERSION_KEY)
    except ValueError:  # ключа ещё нет — инициализируем (следующее чтение возьмёт 1)
        cache_store.set(FACETS_CACHE_VERSION_KEY, 1, None)


def _facets_cache_key(category, kwargs: dict) -> str:
    """Стабильный ключ по (версия, slug категории, нормализованные параметры build_facets).
    Параметры канонизируются (сортировка по slug, списки в исходном порядке) и хэшируются —
    один и тот же набор фильтров (в любом порядке query-параметров) даёт один ключ."""
    payload = {
        "tool_type": kwargs.get("tool_type") or None,
        "brands": list(kwargs.get("brands") or []),
        "stock_status": kwargs.get("stock_status") or None,
        "attr_filters": {k: list(v) for k, v in sorted((kwargs.get("attr_filters") or {}).items())},
        "attr_ranges": {k: list(v) for k, v in sorted((kwargs.get("attr_ranges") or {}).items())},
        "price_min": kwargs.get("price_min"),
        "price_max": kwargs.get("price_max"),
    }
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"catalog:facets:v{_facets_version()}:{category.slug}:{digest}"


def build_facets_cached(category, **kwargs) -> dict:
    """Кэшированная обёртка над build_facets. FacetError (валидация параметров) поднимается
    ДО кэша — невалидный запрос не кэшируется. Кэш выключен (TTL<=0) → прозрачный вызов
    build_facets без обращения к стору."""
    ttl = _facets_cache_ttl()
    if ttl <= 0:
        return build_facets(category, **kwargs)
    key = _facets_cache_key(category, kwargs)
    cached = cache_store.get(key)
    if cached is not None:
        return cached
    data = build_facets(category, **kwargs)
    cache_store.set(key, data, ttl)
    return data
