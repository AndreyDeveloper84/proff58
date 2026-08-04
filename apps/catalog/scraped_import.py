"""Импорт характеристик, спарсенных с сайтов производителей (PARS-04, Phase 4).

Ядро команды ``catalog_import_scraped``. Принципы (решения владельца и границы):

- ключ матчинга — ``(бренд, нормализованная модель)``: бренд — токен в названии
  нашего товара, модель — из НАЗВАНИЯ карточки источника (не из URL);
- подстрочное сравнение запрещено: только полное равенство нормализованных
  ключей (``ЗП-2680`` — подстрока ключа ``ЗП-26-800``, матчиться не должно);
- артикул — только подтверждение найденного совпадения; ``РСВ-…`` игнорируется;
- ``voltage`` пишется ТОЛЬКО аккумуляторному инструменту (``power_source=battery``
  или напряжение < 60 В) — сетевые значения 220/230 не попадают в фасет;
- перезапись решает ``source_priority`` из ``data/attribute_rules.json``:
  ``scraper=50`` — выше ``regex``(40), ниже ``import_1c``(60);
- неоднозначные совпадения и «многие к одному» — в отчёт, не в базу.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from apps.catalog.models import Attribute, AttributeOption, Product, ProductAttributeValue, Source

# --- нормализация ключей модели --------------------------------------------

TRANS = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)

# модель в названии: П-30-900К, П-24/700ЭР, ЗП-28-800 К, ЗП-2890 мс, П-1400 к-в …
# Дрели/шуруповёрты: ДУ-15/850, ДА-18-2ЛК-У, Д-10/350, DB-50-H3, ЗДУ-780-ЭРМ2,
# ЗД-П421, ЗДМ-820 РМ, GVB-250 и т.п.
# Суффиксы — кириллица (после пробела) или букво-цифры через дефис;
# латинское «SDS» после модели — не её часть.
# Конечная цифра буквенного суффикса — часть модели (РММ2 ≠ РММ, ЭРМ2 ≠ ЭРМ):
# у ЗУБРА это разные модификации, склеивание даёт пересорт характеристик.
MODEL_RE = re.compile(
    r"\b((?:ЗПМ|ЗПВ|ЗП|ПА|ПВ|П|"
    r"ДАУ|ДАЭ|ДАШ|ДА|ДУ|ДШ|СШ|ДЭ|Д|"
    r"ЗДУ|ЗДШ|ЗДМ|ЗД|"
    r"GVB|DB|DSH|DU|DAU|D[A-Z]{1,2})"
    r"[-\s]?(?:\d+[А-ЯЁ]?(?:[-/,.]*\d+[А-ЯЁ]?)*|(?:[A-ZА-ЯЁ]\d+(?:[-/,.]*\d+[А-ЯЁ]?)*))"
    r"(?:\s?[А-ЯЁ]{1,3}\d{0,2}(?![А-ЯЁ0-9]))?"
    r"(?:[-][A-ZА-ЯЁ][A-ZА-ЯЁ0-9]{0,3})?)",
    re.I,
)

# источник/бренд карточки → токен, который обязан быть в названии нашего товара
BRAND_TOKEN_BY_SOURCE = {
    "resanta": "ресанта",
    "vihr": "вихрь",
    "interskol": "интерскол",
    "zubr": "зубр",
}
BRAND_TOKEN_BY_CARD_BRAND = {
    "ресанта": "ресанта",
    "вихрь": "вихрь",
    "зубр": "зубр",
    "интерскол": "интерскол",
}


def norm_key(s: str) -> str:
    """Ключ модели: транслит + только буквы/цифры (полное равенство, не подстрока)."""
    return re.sub(r"[^a-z0-9]", "", s.lower().translate(TRANS))


def extract_model(name: str) -> str | None:
    m = MODEL_RE.search(name)
    return m.group(1).strip() if m else None


def model_key(name: str) -> str | None:
    model = extract_model(name)
    return norm_key(model) if model else None


def card_brand_token(card: dict, source: str) -> str | None:
    brand = (card.get("brand") or "").strip().lower()
    return BRAND_TOKEN_BY_CARD_BRAND.get(brand) or BRAND_TOKEN_BY_SOURCE.get(source)


# --- нормализация значений (правила карты Phase 3) --------------------------

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
_POWER_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*Вт")

MAP_CONFIDENCE = {"high": 90, "medium": 70, "low": 40}

BATTERY_VOLTAGE_CEILING = 60  # напряжение ниже — признак аккумуляторного инструмента


def _to_float(s: str) -> float:
    return float(s.replace(",", "."))


def normalize_scalar(raw: str, rule: str):
    if rule == "int":
        return int(_to_float(_NUM_RE.search(raw).group(0)))
    if rule == "decimal":
        return _to_float(_NUM_RE.search(raw).group(0))
    if rule == "range_upper_decimal":
        nums = _NUM_RE.findall(raw)
        if not nums:
            raise ValueError(f"нет числа: {raw!r}")
        return _to_float(nums[-1]) if re.search(r"\d\s*-\s*\d", raw) else _to_float(nums[0])
    if rule == "voltage_first":
        return _to_float(_NUM_RE.search(raw).group(0))
    raise ValueError(f"неизвестный нормализатор: {rule}")


@dataclass
class ScrapedValue:
    attribute_slug: str
    field: str  # подпись поля источника (или summary_raw / derived-правило)
    raw: str
    value: object  # Decimal | str(option slug)
    is_option: bool
    confidence: int


@dataclass
class CardExtraction:
    values: list[ScrapedValue] = field(default_factory=list)
    dropped: list[tuple[str, str, str]] = field(default_factory=list)  # (field, raw, причина)
    unmapped: list[str] = field(default_factory=list)


def load_attr_map(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_card_values(card: dict, source: str, amap: dict) -> CardExtraction:
    """Применить карту Phase 3 к карточке: map/fallback/derived → значения.

    Поля с action=ignore/unmapped пропускаются (unmapped считаются в отчёт),
    неизвестные значения опций и ошибки нормализации — в dropped.
    """
    res = CardExtraction()
    sdata = amap["sources"][source]
    attrs = card.get("attributes") or {}
    for fname, raw in attrs.items():
        entry = sdata["fields"].get(fname)
        if entry is None:
            res.dropped.append((fname, raw, "поле отсутствует в карте"))
            continue
        if entry["action"] == "unmapped":
            res.unmapped.append(fname)
            continue
        if entry["action"] != "map":
            continue  # ignore
        conf = MAP_CONFIDENCE[entry["confidence"]]
        try:
            if entry["attribute_type"] == "select":
                key = raw.strip().lower()
                if key not in entry["values"]:
                    res.dropped.append((fname, raw, "значение не в словаре опций"))
                    continue
                val = entry["values"][key]
                conf = MAP_CONFIDENCE[
                    entry.get("values_confidence", {}).get(key, entry["confidence"])
                ]
                res.values.append(ScrapedValue(entry["attribute"], fname, raw, val, True, conf))
            else:
                num = normalize_scalar(raw, entry["normalize"])
                res.values.append(
                    ScrapedValue(entry["attribute"], fname, raw, Decimal(str(num)), False, conf)
                )
        except (ValueError, AttributeError) as exc:
            res.dropped.append((fname, raw, f"ошибка нормализации: {exc}"))
    # fallback (например, power Ресанты из summary_raw)
    for fb in sdata.get("fallbacks", []):
        if any(f in attrs for f in fb["applies_when_missing"]):
            continue
        raw = card.get(fb["source_field"]) or ""
        m = _POWER_RE.search(raw)
        if m:
            res.values.append(
                ScrapedValue(
                    fb["attribute"],
                    fb["source_field"],
                    raw,
                    Decimal(str(int(_to_float(m.group(1))))),
                    False,
                    MAP_CONFIDENCE[fb["confidence"]],
                )
            )
        else:
            res.dropped.append((fb["source_field"], raw, "fallback: значение не извлечено"))
    # derived (power_source и т.п.)
    for d in sdata.get("derived", []):
        if d["rule"] == "mains_if_voltage_field" and not any("Напряжение" in f for f in attrs):
            continue
        res.values.append(
            ScrapedValue(
                d["attribute"],
                f"derived:{d['rule']}",
                d["rule"],
                d["value"],
                d["attribute_type"] == "select",
                MAP_CONFIDENCE[d["confidence"]],
            )
        )
    return res


# --- матчинг -----------------------------------------------------------------


@dataclass
class MatchResult:
    status: str  # matched | ambiguous | not_found
    model_key: str | None
    products: list[Product] = field(default_factory=list)


def build_product_index(products: list[Product]) -> dict[tuple[str, str], list[Product]]:
    """(brand_token, model_key) → товары. Товары без модели в названии не индексируются."""
    index: dict[tuple[str, str], list[Product]] = {}
    for p in products:
        token = next((t for t in BRAND_TOKEN_BY_SOURCE.values() if t in p.name.lower()), None)
        if token is None:
            continue
        key = model_key(p.name)
        if not key:
            continue
        index.setdefault((token, key), []).append(p)
    return index


def match_card(card: dict, source: str, index: dict[tuple[str, str], list[Product]]) -> MatchResult:
    token = card_brand_token(card, source)
    key = model_key(card["name"]) if token else None
    if not token or not key:
        return MatchResult("not_found", key)
    found = index.get((token, key), [])
    if len(found) == 1:
        return MatchResult("matched", key, found)
    if len(found) > 1:
        return MatchResult("ambiguous", key, found)
    return MatchResult("not_found", key)


def article_check(product: Product, card_sku: str | None) -> str | None:
    """Артикул — только подтверждение. ``РСВ-…`` игнорируется (мусор, не уникален)."""
    art = (product.article or "").strip()
    if not art or not card_sku:
        return None
    if art.upper().startswith("РСВ"):
        return None
    return "confirmed" if norm_key(art) == norm_key(card_sku) else "mismatch"


# --- план импорта -------------------------------------------------------------

VOLTAGE_SLUG = "voltage"
POWER_SOURCE_SLUG = "power_source"


@dataclass
class PlanItem:
    product_id: int
    attribute_slug: str
    field: str
    raw: str
    new_value: object
    is_option: bool
    confidence: int
    action: str  # create | confirm | overwrite | skipped_priority | skipped_voltage
    old_value: object = None
    old_source: str = ""


def _pav_current_value(pav: ProductAttributeValue):
    if pav.value_option_id:
        return pav.value_option.slug
    if pav.value_decimal is not None:
        return pav.value_decimal
    if pav.value_integer is not None:
        return pav.value_integer
    if pav.value_boolean is not None:
        return pav.value_boolean
    return pav.value_text or None


def _same_value(pav: ProductAttributeValue, value: object, is_option: bool) -> bool:
    cur = _pav_current_value(pav)
    if cur is None:
        return False
    if is_option:
        return cur == value
    try:
        return Decimal(str(cur)) == Decimal(str(value))
    except Exception:
        return False


def is_battery_values(values: list[ScrapedValue]) -> bool:
    """Признак аккумуляторного инструмента: power_source=battery или напряжение < 60 В."""
    for v in values:
        if v.attribute_slug == POWER_SOURCE_SLUG and v.value == "battery":
            return True
        if (
            v.attribute_slug == VOLTAGE_SLUG
            and not v.is_option
            and v.value < BATTERY_VOLTAGE_CEILING
        ):
            return True
    return False


def plan_product_values(
    product: Product,
    values: list[ScrapedValue],
    existing: dict[str, ProductAttributeValue],
    priority: dict[str, int],
) -> list[PlanItem]:
    """План по одному товару: create/confirm/overwrite/skipped_*.

    existing: {attribute_slug: PAV} по управляемым атрибутам.
    """
    battery = is_battery_values(values)
    items: list[PlanItem] = []
    for v in values:
        if v.attribute_slug == VOLTAGE_SLUG and not battery:
            items.append(
                PlanItem(
                    product.id,
                    v.attribute_slug,
                    v.field,
                    v.raw,
                    v.value,
                    v.is_option,
                    v.confidence,
                    "skipped_voltage",
                )
            )
            continue
        pav = existing.get(v.attribute_slug)
        if pav is None:
            items.append(
                PlanItem(
                    product.id,
                    v.attribute_slug,
                    v.field,
                    v.raw,
                    v.value,
                    v.is_option,
                    v.confidence,
                    "create",
                )
            )
            continue
        if _same_value(pav, v.value, v.is_option):
            items.append(
                PlanItem(
                    product.id,
                    v.attribute_slug,
                    v.field,
                    v.raw,
                    v.value,
                    v.is_option,
                    v.confidence,
                    "confirm",
                    _pav_current_value(pav),
                    pav.source,
                )
            )
            continue
        if priority.get(Source.SCRAPER, 0) >= priority.get(pav.source, 0):
            items.append(
                PlanItem(
                    product.id,
                    v.attribute_slug,
                    v.field,
                    v.raw,
                    v.value,
                    v.is_option,
                    v.confidence,
                    "overwrite",
                    _pav_current_value(pav),
                    pav.source,
                )
            )
        else:
            items.append(
                PlanItem(
                    product.id,
                    v.attribute_slug,
                    v.field,
                    v.raw,
                    v.value,
                    v.is_option,
                    v.confidence,
                    "skipped_priority",
                    _pav_current_value(pav),
                    pav.source,
                )
            )
    return items


def apply_plan_items(
    product: Product,
    items: list[PlanItem],
    attr_by_slug: dict[str, Attribute],
    option_index: dict[str, dict[str, AttributeOption]],
) -> int:
    """Записать create/overwrite по товару. Вызывать внутри transaction.atomic().

    Возвращает число записанных PAV. attrs_cache пересобирается точечно
    (rebuild_attrs_cache — собственный SELECT + save одного товара).
    """
    from apps.catalog.read_models import rebuild_attrs_cache

    written = 0
    existing = {
        pav.attribute.slug: pav
        for pav in product.attribute_values.select_related("attribute", "value_option")
    }
    for item in items:
        if item.action not in ("create", "overwrite"):
            continue
        attribute = attr_by_slug[item.attribute_slug]
        option = None
        if item.is_option:
            option = option_index[item.attribute_slug].get(item.new_value)
            if option is None:
                continue  # опции нет — не пишем (не создаём новых)
        pav = existing.get(item.attribute_slug)
        if pav is None:
            pav = ProductAttributeValue(product=product, attribute=attribute)
            existing[item.attribute_slug] = pav
        pav.value_text = ""
        pav.value_integer = None
        pav.value_decimal = None
        pav.value_boolean = None
        pav.value_option = None
        if item.is_option:
            pav.value_option = option
        else:
            pav.value_decimal = item.new_value
        pav.source = Source.SCRAPER
        pav.confidence = item.confidence
        pav.save()
        written += 1
    if written:
        rebuild_attrs_cache(product)
    return written
