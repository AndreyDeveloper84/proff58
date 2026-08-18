"""Определение бренда-ПРОИЗВОДИТЕЛЯ по названию товара (BRAND-02).

Второй потребитель ``brand_vocabulary.json``. От индекса матчинга
(:mod:`apps.catalog.scraped_import`) отличается вопросом, на который отвечает:

* индексу важно «с какими карточками товар может сойтись» — поэтому упоминание
  совместимого бренда там ПОЛЕЗНО и не отбрасывается: аккумулятор «для X и Y»
  обязан быть виден карточкам обоих;
* здесь вопрос «кто произвёл» — и «Аккумулятор **для Makita** DF330DWE» произведён
  не Makita. Такое упоминание обязано быть отброшено, иначе мы запишем в каталог
  чужого производителя.

Один словарь, разные его части у разных потребителей: ``compatibility_markers``
читает только этот модуль.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.catalog.scraped_import import BRAND_VOCABULARY, BrandVocabulary

# Статусы идентичности бренда по названию.
IDENTITY_HIGH = "HIGH_CONFIDENCE"
IDENTITY_COMPAT = "COMPAT_ONLY"
IDENTITY_AMBIGUOUS = "AMBIGUOUS_MULTI"
IDENTITY_NONE = "NO_BRAND"

# Маркеры совместимости делятся на два класса, потому что расстоянием они не
# разделяются. Замер по каталогу:
#
#   «Щетки угольные АНАЛОГ 5х10х14мм 18-120 MAKITA CB325»  → MAKITA совместимость
#   «Круг отрезной для металла 125х1,6х22,2 ЗУБР»          → ЗУБР производитель
#
# Разрыв между маркером и брендом в обоих случаях около двадцати символов, так
# что окно любой ширины ошибётся на одном из них. Различает сам маркер:
#
# ``strong``   — «аналог», «совместим», «подходит»: относятся ко всему названию,
#                действуют на любой бренд правее независимо от расстояния;
# ``adjacent`` — «для», «под», «тип»: действуют только на то, что стоит сразу за
#                ними. «для Makita» — совместимость, «для металла … ЗУБР» — нет.
DEFAULT_ADJACENT_WINDOW = 20


@dataclass(frozen=True)
class BrandHit:
    canonical: str
    position: int
    compatibility: bool


@dataclass(frozen=True)
class BrandDecision:
    """Решение по одному названию: статус и, если он HIGH, сам бренд."""

    status: str
    brand: str
    manufacturers: tuple[str, ...]
    compatibility_refs: tuple[str, ...]

    @property
    def is_high(self) -> bool:
        return self.status == IDENTITY_HIGH


def _word(marker: str) -> re.Pattern:
    """Маркер как отдельное слово — годится для ``strong``: важен сам факт."""
    return re.compile(rf"(?<![a-zа-я0-9]){re.escape(marker.lower())}(?![a-zа-я0-9])")


def _adjacent(marker: str) -> re.Pattern:
    """Маркер ВПЛОТНУЮ перед брендом: между ними только пробел, знак или «с»/«к».

    Строгая смежность обязательна. Мягкое окно (маркер где-то в двадцати
    символах слева) даёт массовую ошибку на назначении:

        «Адаптер **для бит** KRAFTOOL BULLDOG 150мм»   → KRAFTOOL производитель
        «Адаптер **для** биметал.коронок ЗУБР SDS+»     → ЗУБР производитель
        «Аккумулятор **для Makita** DF330DWE»           → MAKITA совместимость

    Разделяет не расстояние, а то, стоит ли бренд непосредственно объектом
    предлога. На замере пула мягкое окно пометило совместимостью 170 товаров,
    из которых подавляющее большинство — собственная продукция бренда.
    """
    return re.compile(
        rf"(?<![a-zа-я0-9]){re.escape(marker.lower())}[\s\-—,:«\"']*(?:с|к)?[\s\-—,:«\"']*$"
    )


@dataclass(frozen=True)
class Markers:
    strong: tuple[re.Pattern, ...]
    adjacent: tuple[re.Pattern, ...]
    window: int


_MARKERS_CACHE: dict[int, Markers] = {}


def _markers(vocabulary: BrandVocabulary) -> Markers:
    key = id(vocabulary)
    if key in _MARKERS_CACHE:
        return _MARKERS_CACHE[key]
    raw = vocabulary.compatibility_markers
    # Плоский список старой схемы трактуем как adjacent: он безопаснее — маркер
    # действует только вплотную и не может пометить производителя ошибочно.
    if isinstance(raw, dict):
        strong = tuple(_word(m) for m in raw.get("strong", ()))
        adjacent = tuple(_adjacent(m) for m in raw.get("adjacent", ()))
        window = int(raw.get("adjacent_window", DEFAULT_ADJACENT_WINDOW))
    else:
        strong = ()
        adjacent = tuple(_adjacent(m) for m in raw)
        window = DEFAULT_ADJACENT_WINDOW
    _MARKERS_CACHE[key] = Markers(strong, adjacent, window)
    return _MARKERS_CACHE[key]


def find_brand_hits(name: str, vocabulary: BrandVocabulary | None = None) -> list[BrandHit]:
    """Все упоминания брендов с пометкой «это ссылка на совместимость»."""
    vocabulary = vocabulary or BRAND_VOCABULARY
    low = (name or "").lower()
    markers = _markers(vocabulary)
    hits: dict[str, BrandHit] = {}
    for canonical, pattern in vocabulary.alias_patterns:
        m = pattern.search(low)
        if not m:
            continue
        head = low[: m.start()]
        compat = any(mk.search(head) for mk in markers.strong) or any(
            mk.search(head) for mk in markers.adjacent
        )
        prev = hits.get(canonical)
        # Бренд, упомянутый и как производитель, и как совместимость, считается
        # производителем: «KRAFTOOL … для KRAFTOOL» — это KRAFTOOL.
        if prev is None or (prev.compatibility and not compat):
            hits[canonical] = BrandHit(canonical, m.start(), compat)
    return sorted(hits.values(), key=lambda h: h.position)


def decide_brand(name: str, vocabulary: BrandVocabulary | None = None) -> BrandDecision:
    """Статус идентичности бренда для одного названия.

    ``HIGH_CONFIDENCE`` — ровно один бренд вне контекста совместимости.
    Именно и только он даёт право на запись в ``Product.brand``.
    """
    hits = find_brand_hits(name, vocabulary)
    manufacturers = tuple(h.canonical for h in hits if not h.compatibility)
    refs = tuple(h.canonical for h in hits if h.compatibility)
    if not hits:
        return BrandDecision(IDENTITY_NONE, "", (), ())
    if len(manufacturers) == 1:
        return BrandDecision(IDENTITY_HIGH, manufacturers[0], manufacturers, refs)
    if len(manufacturers) > 1:
        return BrandDecision(IDENTITY_AMBIGUOUS, "", manufacturers, refs)
    return BrandDecision(IDENTITY_COMPAT, "", (), refs)
