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
- неоднозначные совпадения и «многие к одному» — в отчёт, не в базу;
- единицы измерения сверяются fail-closed (ДРФ-1440): подпись с чужой единицей
  («Мощность, кВт» в ось «Вт», «Вес, кг» в ось «г») обязана нести ``source_unit``
  и нормализатор-конвертер, иначе карта не проходит ``validate_attr_map_units``
  и импорт не стартует — молчаливая ошибка в тысячу раз в фасете невозможна;
- лошадиные силы в ватты НЕ пересчитываются: у них своя ось ``power_hp``
  (решение владельца, см. комментарий к ``CONVERTERS``);
- оси из ``RESTRICTED_ATTRIBUTES`` (сейчас — ``weight``, «г», область молотков)
  закрыты для автоматической записи: карта, нацеленная в такую ось, не проходит.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from apps.catalog.brand_vocabulary import BRAND_VOCABULARY
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

# --- словарь брендов -------------------------------------------------------
#
# Словарь живёт в data/catalog_processing_rules/brand_vocabulary.json, загрузчик —
# в apps/catalog/brand_vocabulary.py. Здесь его копии нет: раньше BRAND_TOKENS
# выводился из реестра источников, из-за чего в индекс попадали товары лишь
# четырёх брендов — тех, чьи сайты мы парсили, а не тех, что есть в каталоге.
#
# Этот потребитель читает только canonical + aliases. compatibility_markers НЕ
# применяет сознательно (см. docstring product_brand_tokens).

# Дефолт бренда для ОДНО-брендового источника: у mono-brand сайта бренд карточки
# может быть пустым, и тогда его задаёт сам источник. Для мультибрендового
# источника (маркетплейс) дефолта нет — бренд обязан прийти из карточки.
BRAND_TOKEN_BY_SOURCE = dict(BRAND_VOCABULARY.source_defaults)
BRAND_TOKEN_BY_CARD_BRAND = dict(BRAND_VOCABULARY.canonical_by_alias)
# порядок стабилен и без дублей: имя товара может содержать несколько брендов
BRAND_TOKENS = BRAND_VOCABULARY.canonicals()

# Мусорные артикулы 1С: не уникальны, один и тот же код висит на разных товарах.
# Тот же список игнорирует ``article_check`` — индекс обязан вести себя так же,
# иначе ступень SKU выдаёт ``ambiguous`` на пустом месте.
GARBAGE_ARTICLE_PREFIXES = ("РСВ",)

# Артикул производителя, попавший в НАЗВАНИЕ товара: «72/14/4», «900/71/8/80».
# Требования выведены из замера каталога (см. docs ПАРС-17):
# - минимум ТРИ группы: двухгрупповые числа в названиях почти всегда параметры
#   («УШМ 125/900» — Ø и мощность, «ТВК-1 900/1800 В»), а не артикулы;
# - первая группа от двух цифр — иначе ловятся дроби «3/4», «1/2»;
# - слева не буква/цифра/дефис — иначе «ЭШМ-125/5Э» разбирается как артикул.
MANUFACTURER_SKU_IN_NAME_RE = re.compile(r"(?<![\w/\-])\d{2,4}(?:/\d{1,4}){2,4}(?![\w/])")


def norm_key(s: str) -> str:
    """Ключ модели: транслит + только буквы/цифры (полное равенство, не подстрока)."""
    return re.sub(r"[^a-z0-9]", "", s.lower().translate(TRANS))


# Унаследованный regex-префикс из MODEL_RE. Он единственный не-литеральный
# префикс, который допустимо переносить в карты категорий.
ALLOWED_REGEX_PREFIXES = frozenset({"D[A-Z]{1,2}"})

# Полный унаследованный перечень префиксов из MODEL_RE (включая generic
# D[A-Z]{1,2}). Используется для доказательства эквивалентности fallback.
LEGACY_MODEL_PREFIXES = [
    "ЗПМ",
    "ЗПВ",
    "ЗП",
    "ПА",
    "ПВ",
    "П",
    "ДАУ",
    "ДАЭ",
    "ДАШ",
    "ДА",
    "ДУ",
    "ДШ",
    "СШ",
    "ДЭ",
    "Д",
    "ЗДУ",
    "ЗДШ",
    "ЗДМ",
    "ЗД",
    "GVB",
    "DB",
    "DSH",
    "DU",
    "DAU",
    "D[A-Z]{1,2}",
]


def _build_model_re(prefixes: list[str]) -> re.Pattern:
    """Собрать regex модели из префиксов категории (длинные раньше коротких).

    Префиксы вставляются в тело паттерна как есть. Литеральные префиксы
    безопасны, т.к. ``validate_model_prefixes`` отсекает regex-метасимволы,
    кроме явно разрешённых унаследованных выражений.
    """
    prefix_part = "|".join(p for p in sorted(prefixes, key=len, reverse=True))
    return re.compile(
        r"\b((?:" + prefix_part + r")"
        r"[-\s]?(?:\d+[А-ЯЁ]?(?:[-/,.]*\d+[А-ЯЁ]?)*|(?:[A-ZА-ЯЁ]\d+(?:[-/,.]*\d+[А-ЯЁ]?)*))"
        r"(?:\s?[А-ЯЁ]{1,3}\d{0,2}(?![А-ЯЁ0-9]))?"
        r"(?:[-][A-ZА-ЯЁ][A-ZА-ЯЁ0-9]{0,3})?)",
        re.I,
    )


def validate_model_prefixes(prefixes: list[str]) -> None:
    """Карта категории должна содержать литеральные префиксы моделей.

    Regex-метасимволы запрещены, кроме явно разрешённых унаследованных
    выражений (сейчас это только ``D[A-Z]{1,2}``). Унаследованный ``MODEL_RE``
    остаётся fallback для карт без ``model_prefixes``.
    """
    for p in prefixes:
        if re.escape(p) != p and p not in ALLOWED_REGEX_PREFIXES:
            raise ValueError(
                f"Префикс модели содержит regex-метасимволы: {p!r}. "
                "Карта должна содержать только литеральные префиксы."
            )


def extract_model(name: str, prefixes: list[str] | None = None) -> str | None:
    model_re = MODEL_RE if prefixes is None else _build_model_re(prefixes)
    m = model_re.search(name)
    return m.group(1).strip() if m else None


def model_key(name: str, prefixes: list[str] | None = None) -> str | None:
    model = extract_model(name, prefixes=prefixes)
    return norm_key(model) if model else None


def card_brand_token(card: dict, source: str) -> str | None:
    brand = (card.get("brand") or "").strip().lower()
    return BRAND_TOKEN_BY_CARD_BRAND.get(brand) or BRAND_TOKEN_BY_SOURCE.get(source)


def _exact_model_key(name: str, prefixes: list[str] | None = None) -> str | None:
    """Точное строковое совпадение извлечённой модели (без транслита)."""
    model = extract_model(name, prefixes=prefixes)
    return model.lower().strip() if model else None


def _alias_key(model: str | None) -> str | None:
    """Нормализованный ключ модели без trailing суффикса (1–3 кириллические буквы).

    Алиас — последняя ступень лестницы: ``ДА-24-2ЛК-У`` → ``ДА-24-2ЛК``.
    Без разделителя суффикс не отрезаем, чтобы не портить корень модели.
    """
    if not model:
        return None
    stripped = re.sub(r"(?:[-/\s])([А-ЯЁ]{1,3})$", "", model.strip(), flags=re.I)
    return norm_key(stripped)


def _card_sku_keys(card: dict) -> list[str]:
    raw = card.get("manufacturer_sku")
    if not raw:
        return []
    keys = []
    for part in re.split(r"[,;]", str(raw)):
        part = part.strip()
        if part:
            keys.append(norm_key(part))
    return keys


# --- нормализация значений (правила карты Phase 3) --------------------------

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
_POWER_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*Вт")

MAP_CONFIDENCE = {"high": 90, "medium": 70, "low": 40}

BATTERY_VOLTAGE_CEILING = 60  # напряжение ниже — признак аккумуляторного инструмента


# Нормализаторы-конвертеры (ДРФ-1440): имя правила -> (единица источника,
# единица оси, множитель). Пересчёт живёт в карте атрибутов, а не в голове
# оператора: подпись «Мощность, кВт» обязана нести normalize=decimal_kw_to_w,
# иначе карта не пройдёт validate_attr_map_units и импорт не стартует.
#
# ``decimal_hp_to_w`` — НАМЕРЕННО НЕ ИСПОЛЬЗУЕТСЯ НИ В ОДНОЙ КАРТЕ.
# Решение владельца от 2026-09-02: лошадиные силы живут отдельной осью
# ``power_hp`` (единица «л.с.»), в ватты не пересчитываются. Причины:
#   1. это разные величины — у сетевого инструмента паспортные ватты это
#      ПОТРЕБЛЯЕМАЯ мощность, у бензинового л.с. — мощность НА ВАЛУ; между ними
#      КПД, а не константа, поэтому в одном фильтре они несравнимы;
#   2. ось ``power`` фильтруемая и населена сетевыми значениями 90…2850 Вт;
#      4,5 л.с. -> 3310 Вт переопределили бы верх шкалы фильтра;
#   3. множитель неоднозначен: метрическая л.с. 735,5 Вт против механической
#      745,7 Вт — здесь взята метрическая, её используют российские
#      производители бензоинструмента.
# Правило оставлено рабочим и покрыто тестами на случай пересмотра решения;
# подключать его в карту без нового решения владельца нельзя.
CONVERTERS: dict[str, tuple[str, str, Decimal]] = {
    "decimal_kw_to_w": ("кВт", "Вт", Decimal("1000")),
    "decimal_hp_to_w": ("л.с.", "Вт", Decimal("735.5")),
    "decimal_kg_to_g": ("кг", "г", Decimal("1000")),
    "decimal_g_to_kg": ("г", "кг", Decimal("0.001")),
}
CONVERTER_BY_UNITS: dict[tuple[str, str], str] = {}

# Оси, закрытые для автоматической записи (ДРФ-1440, решение владельца, вариант A).
# slug -> причина. Карта парсера, нацеленная на такую ось, не проходит гейт:
# сузить область оси и при этом оставить её открытой для автоматов — значит
# не сузить ничего.
RESTRICTED_ATTRIBUTES: dict[str, str] = {
    "weight": (
        "ось «Вес» (единица «г») сужена до молотков (правило объявлено только в "
        "блоке tool_type=molotki) и закрыта для автоматической записи; "
        "каноническая ось веса каталога — weight_kg (кг)"
    ),
}

# Нормализаторы без пересчёта единиц (значение остаётся в единице источника).
PLAIN_NORMALIZERS = frozenset(
    {"int", "decimal", "range_upper_decimal", "voltage_first", "summary_power_w"}
)

_UNIT_NOISE_RE = re.compile(r"[\s.·*×]")


def _canon_unit(unit: str | None) -> str:
    """Каноническая форма единицы для сверки: «А*ч» == «А·ч», «Нм» == «Н·м».

    Схлопывается только типографика (пробелы, точки, знаки умножения) —
    «кВт» и «Вт», «кг» и «г» остаются разными единицами.
    """
    return _UNIT_NOISE_RE.sub("", (unit or "")).lower()


for _rule, (_src_unit, _dst_unit, _factor) in CONVERTERS.items():
    CONVERTER_BY_UNITS[(_canon_unit(_src_unit), _canon_unit(_dst_unit))] = _rule


def _to_float(s: str) -> float:
    return float(s.replace(",", "."))


def _first_number(raw: str) -> Decimal:
    """Первое число строки как Decimal; десятичная запятая -> точка.

    Единица внутри значения снимается самим regex: «0.07 кг» -> Decimal("0.07"),
    «2,3 кВт» -> Decimal("2.3"). Decimal, а не float, — чтобы пересчёт
    ×1000 не давал 70.00000000000001.
    """
    m = _NUM_RE.search(raw)
    if m is None:
        raise ValueError(f"нет числа: {raw!r}")
    return Decimal(m.group(0).replace(",", "."))


def _trim(value: Decimal) -> Decimal:
    """Убрать хвостовые нули без экспоненты: 70.000 -> 70, 3310.750 -> 3310.75."""
    value = value.normalize()
    return value.quantize(Decimal(1)) if value == value.to_integral_value() else value


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
    if rule in CONVERTERS:
        _, _, factor = CONVERTERS[rule]
        return _trim(_first_number(raw) * factor)
    raise ValueError(f"неизвестный нормализатор: {rule}")


def _all_map_entries(amap: dict):
    """(источник, подпись поля, запись) по всем записям карты, пишущим значение."""
    for source, sdata in amap.get("sources", {}).items():
        for fname, entry in sdata.get("fields", {}).items():
            if entry.get("action") != "map":
                continue
            yield source, fname, entry
        for entry in sdata.get("fallbacks", []):
            yield source, f"fallback:{entry.get('source_field')}", entry
        for entry in sdata.get("derived", []):
            yield source, f"derived:{entry.get('rule')}", entry


def _numeric_map_entries(amap: dict):
    """(источник, подпись поля, запись) по всем числовым полям карты с action=map."""
    for source, fname, entry in _all_map_entries(amap):
        if entry.get("attribute_type") == "select":
            continue
        if fname.startswith("derived:"):
            continue
        yield source, fname, entry


def validate_attr_map_units(amap: dict, attr_by_slug: dict | None = None) -> None:
    """Fail-closed сверка единиц карты (ДРФ-1440). Ошибки — ValueError списком.

    Для каждого числового поля с ``action=map`` (и для fallback-ов):

    1. ``normalize`` обязан быть известным правилом;
    2. если задан ``source_unit`` и он отличается от ``unit`` оси — ``normalize``
       обязан быть конвертером ровно этой пары единиц;
    3. если ``source_unit`` не задан или совпадает с ``unit`` — ``normalize``
       конвертером быть НЕ должен (молчаливый пересчёт запрещён);
    4. при переданном ``attr_by_slug`` — ``unit`` карты обязан совпасть с
       ``Attribute.unit`` в БД (сверка по канонической форме: «Нм» == «Н·м»).

    Именно пункт 4 ловит подпись «Вес, кг» -> ось ``weight`` с единицей «г»:
    без ``source_unit``/конвертера 0.07 кг легло бы в фасет как 0.07 г.

    Отдельно (и раньше всех единиц) проверяется, что карта не целится в ось из
    :data:`RESTRICTED_ATTRIBUTES` — оси, закрытые для автоматической записи.
    """
    problems: list[str] = []
    for source, fname, entry in _all_map_entries(amap):
        slug = entry.get("attribute")
        reason = RESTRICTED_ATTRIBUTES.get(slug)
        if reason:
            problems.append(
                f"{source}/{fname}: ось {slug!r} закрыта для автоматической записи — {reason}"
            )
    for source, fname, entry in _numeric_map_entries(amap):
        where = f"{source}/{fname}"
        slug = entry.get("attribute")
        rule = entry.get("normalize")
        unit = entry.get("unit")
        source_unit = entry.get("source_unit")

        if rule not in PLAIN_NORMALIZERS and rule not in CONVERTERS:
            problems.append(f"{where}: неизвестный нормализатор {rule!r}")
            continue

        if source_unit is not None and _canon_unit(source_unit) != _canon_unit(unit):
            expected = CONVERTER_BY_UNITS.get((_canon_unit(source_unit), _canon_unit(unit)))
            if expected is None:
                problems.append(
                    f"{where}: нет конвертера {source_unit!r} -> {unit!r}; "
                    f"пересчёт не объявлен — поле нельзя сопоставлять"
                )
            elif rule != expected:
                problems.append(
                    f"{where}: единица источника {source_unit!r} при оси {unit!r} "
                    f"требует normalize={expected!r}, в карте {rule!r}"
                )
        elif rule in CONVERTERS:
            src_unit, dst_unit, _ = CONVERTERS[rule]
            problems.append(
                f"{where}: normalize={rule!r} пересчитывает {src_unit} -> {dst_unit}, "
                f"но source_unit не объявлен (или равен unit) — молчаливый пересчёт запрещён"
            )

        if attr_by_slug is not None:
            attr = attr_by_slug.get(slug)
            if attr is None:
                problems.append(f"{where}: атрибут {slug!r} отсутствует в БД")
            elif _canon_unit(attr.unit) != _canon_unit(unit):
                problems.append(
                    f"{where}: карта объявляет unit={unit!r}, "
                    f"а ось {slug!r} в БД имеет единицу {attr.unit!r}"
                )
    if problems:
        raise ValueError("единицы карты не сходятся:\n  - " + "\n  - ".join(problems))


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


LADDER_RANK = {
    "sku": 0,
    "exact_model": 1,
    "normalized_model": 2,
    "alias": 3,
}


@dataclass
class MatchResult:
    status: str  # matched | ambiguous | not_found
    model_key: str | None
    products: list[Product] = field(default_factory=list)
    matched_by: str = ""


@dataclass
class ProductMatchEntry:
    product: Product
    tokens: list[str]  # все брендовые токены из имени товара (обычно один)
    exact_key: str | None
    normalized_key: str | None
    alias_key: str | None
    article_keys: list[str]  # артикул 1С + артикулы производителя из имени


@dataclass
class MatchIndex:
    entries: list[ProductMatchEntry] = field(default_factory=list)
    by_token: dict[str, list[ProductMatchEntry]] = field(default_factory=lambda: defaultdict(list))
    by_article: dict[tuple[str, str], list[ProductMatchEntry]] = field(
        default_factory=lambda: defaultdict(list)
    )
    by_exact: dict[tuple[str, str], list[ProductMatchEntry]] = field(
        default_factory=lambda: defaultdict(list)
    )
    by_normalized: dict[tuple[str, str], list[ProductMatchEntry]] = field(
        default_factory=lambda: defaultdict(list)
    )
    by_alias: dict[tuple[str, str], list[ProductMatchEntry]] = field(
        default_factory=lambda: defaultdict(list)
    )


def product_brand_tokens(name: str) -> list[str]:
    """Все брендовые идентичности в названии товара, в стабильном порядке.

    Возвращает КАНОНИЧЕСКИЕ имена брендов, а не найденные подстроки: иначе три
    потребителя словаря (индекс, Product.brand, сверка с источником) со временем
    разошлись бы по нормализации — «hikoki» и «hitachi» стали бы разными брендами.

    Раньше брался только первый: товар, в имени которого упомянуты два бренда
    (совместимая оснастка, аккумулятор «для X и Y»), был виден карточкам лишь
    одного из них.

    Маркеры совместимости здесь НЕ применяются сознательно: для индекса важно
    «с какими карточками товар может сойтись», и совместимая оснастка обязана
    оставаться видимой обоим брендам. Отсечение «для X» — забота BRAND-02, где
    вопрос другой: кто произвёл товар.
    """
    low = name.lower()
    out: list[str] = []
    for canonical, pattern in BRAND_VOCABULARY.alias_patterns:
        if canonical not in out and pattern.search(low):
            out.append(canonical)
    return out


def product_article_keys(product: Product) -> list[str]:
    """Ключи ступени SKU по одному товару: артикул 1С + артикулы из имени.

    Артикул производителя у Ресанты/Вихря нередко стоит прямо в названии
    («Перф. П-800к 72/3/6 ВИХРЬ»), а поле ``article`` при этом пустое или
    занято мусорным кодом ``РСВ-…``. Такой товар терял ступень SKU целиком.
    Мусорные артикулы в индекс не попадают — как и в ``article_check``.
    """
    keys: list[str] = []
    article = (product.article or "").strip()
    if article and not article.upper().startswith(GARBAGE_ARTICLE_PREFIXES):
        key = norm_key(article)
        if key:
            keys.append(key)
    for raw in MANUFACTURER_SKU_IN_NAME_RE.findall(product.name):
        key = norm_key(raw)
        if key and key not in keys:
            keys.append(key)
    return keys


def _index_entry(product: Product, prefixes: list[str] | None = None) -> ProductMatchEntry | None:
    tokens = product_brand_tokens(product.name)
    if not tokens:
        return None
    exact = _exact_model_key(product.name, prefixes=prefixes)
    normalized = model_key(product.name, prefixes=prefixes)
    alias = _alias_key(extract_model(product.name, prefixes=prefixes)) if exact else None
    return ProductMatchEntry(
        product=product,
        tokens=tokens,
        exact_key=exact,
        normalized_key=normalized,
        alias_key=alias,
        article_keys=product_article_keys(product),
    )


def build_product_index(products: list[Product], prefixes: list[str] | None = None) -> MatchIndex:
    """Индекс для лестницы матчинга: SKU → exact → normalized → alias.

    Брендовый токен в названии остаётся обязательным условием попадания в
    индекс: он единственное, что отделяет ступень SKU от ложных совпадений —
    артикулы источников (``70/6/14``) сталкиваются с 1С-артикулами посторонних
    товаров, а ``resanta.ru`` и ``vihr.su`` делят одно пространство SKU.
    """
    index = MatchIndex()
    for p in products:
        entry = _index_entry(p, prefixes=prefixes)
        if entry is None:
            continue
        index.entries.append(entry)
        for token in entry.tokens:
            index.by_token[token].append(entry)
            for article_key in entry.article_keys:
                index.by_article[(token, article_key)].append(entry)
            if entry.exact_key:
                index.by_exact[(token, entry.exact_key)].append(entry)
            if entry.normalized_key:
                index.by_normalized[(token, entry.normalized_key)].append(entry)
            if entry.alias_key:
                index.by_alias[(token, entry.alias_key)].append(entry)
    return index


def _resolve(candidates: list[ProductMatchEntry], step: str, model_key: str | None) -> MatchResult:
    products = [e.product for e in candidates]
    if len(candidates) == 1:
        return MatchResult("matched", model_key, products, matched_by=step)
    return MatchResult("ambiguous", model_key, products)


def match_card(
    card: dict, source: str, index: MatchIndex, prefixes: list[str] | None = None
) -> MatchResult:
    token = card_brand_token(card, source)
    if not token:
        return MatchResult("not_found", None)

    name = card["name"]
    exact = _exact_model_key(name, prefixes=prefixes)
    normalized = model_key(name, prefixes=prefixes)
    alias = _alias_key(extract_model(name, prefixes=prefixes))

    # 1. точный SKU / артикул — до проверки модели: артикул источника самодостаточен
    # и не зависит от того, распозналась ли модель в имени карточки (ПАРС-16).
    for sku_key in _card_sku_keys(card):
        candidates = index.by_article.get((token, sku_key), [])
        if candidates:
            return _resolve(candidates, "sku", normalized)

    if not any((exact, normalized, alias)):
        return MatchResult("not_found", normalized)

    # 2. точная модель
    if exact:
        candidates = index.by_exact.get((token, exact), [])
        if candidates:
            return _resolve(candidates, "exact_model", normalized)

    # 3. нормализованная модель
    if normalized:
        candidates = index.by_normalized.get((token, normalized), [])
        if candidates:
            return _resolve(candidates, "normalized_model", normalized)

    # 4. alias
    if alias:
        candidates = index.by_alias.get((token, alias), [])
        if candidates:
            return _resolve(candidates, "alias", normalized)

    return MatchResult("not_found", normalized)


def article_check(product: Product, card_sku: str | None) -> str | None:
    """Артикул — только подтверждение. ``РСВ-…`` игнорируется (мусор, не уникален)."""
    art = (product.article or "").strip()
    if not art or not card_sku:
        return None
    if art.upper().startswith(GARBAGE_ARTICLE_PREFIXES):
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
    action: str  # create | confirm | conflict | skipped_voltage
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
    """План по одному товару: create / confirm / conflict / skipped_voltage.

    existing: {attribute_slug: PAV} по управляемым атрибутам.

    Автоматический overwrite запрещён (CODE-04): любое расхождение со
    значением в каталоге уходит в ``conflict`` / manual review.
    ``priority`` больше не влияет на решение, но оставлен для совместимости.
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
        # Расхождение — в ручную проверку, без перезаписи.
        items.append(
            PlanItem(
                product.id,
                v.attribute_slug,
                v.field,
                v.raw,
                v.value,
                v.is_option,
                v.confidence,
                "conflict",
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
