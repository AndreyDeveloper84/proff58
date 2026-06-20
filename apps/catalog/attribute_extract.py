"""Движок извлечения характеристик товара (EAV) из названия 1С.

Зеркало :mod:`apps.catalog.tool_type`: чистая логика правил из
``data/attribute_rules.json`` без обращения к БД. Используется командами
``load_attributes`` / ``enrich_attributes`` / ``attribute_coverage`` и тестами.

Три вида (``kind``) характеристик:

* ``select``  — значение из списка вариантов; перебор вариантов ПО ПОРЯДКУ,
  выигрывает первый, чьё любое ключевое слово — подстрока названия. Порядок
  важен: ``brushless`` должен стоять раньше ``brushed`` («бесщеточный» содержит
  «щеточный»).
* ``number``  — число + единица; первый сработавший regex даёт значение
  (``Decimal``, запятая → точка).
* ``boolean`` — да/нет по whitelist: сначала ``false_keywords``, затем
  ``true_keywords``; иначе значение не извлекается.

Приоритет источника берётся из правила (поле ``priority`` / карта
``source_priority``), а НЕ хардкодится в движке: ``enrich_attributes`` сравнивает
приоритет нового значения с уже сохранённым (``ProductAttributeValue.source``),
чтобы не затирать ручное/1С-значение менее надёжным regex/keyword.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .tool_type import normalize

SELECT = "select"
NUMBER = "number"
BOOLEAN = "boolean"


@dataclass(frozen=True)
class Option:
    """Вариант select-характеристики."""

    value: str  # отображаемое имя (рус.) — попадает в attrs_cache/витрину
    slug: str  # канонический англо-идентификатор — фильтр/SEO/API
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttrRule:
    slug: str
    name: str
    kind: str  # select | number | boolean
    unit: str = ""
    source: str = "regex"
    priority: int = 0
    is_filter: bool = True
    is_seo_facet: bool = False
    is_ai_feature: bool = False
    options: tuple[Option, ...] = ()  # select
    patterns: tuple[re.Pattern, ...] = ()  # number
    true_keywords: tuple[str, ...] = ()  # boolean
    false_keywords: tuple[str, ...] = ()  # boolean


@dataclass
class AttrValue:
    """Извлечённое значение одной характеристики."""

    slug: str
    kind: str
    source: str
    priority: int
    number: Decimal | None = None
    option_slug: str = ""
    option_value: str = ""
    boolean: bool | None = None
    unit: str = ""
    matched: str = ""


class AttributeRules:
    """Загруженный и проиндексированный словарь правил характеристик."""

    def __init__(self, by_tool_type: dict[str, list[AttrRule]], source_priority: dict[str, int]):
        self._by_tt = by_tool_type
        self.source_priority = source_priority

    @classmethod
    def from_file(cls, path: str | Path) -> AttributeRules:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> AttributeRules:
        source_priority = data.get("source_priority", {})
        by_tt: dict[str, list[AttrRule]] = {}
        for tt in data.get("tool_types", []):
            by_tt[tt["tool_type"]] = [
                cls._rule(a, source_priority) for a in tt.get("attributes", [])
            ]
        return cls(by_tt, source_priority)

    @staticmethod
    def _rule(a: dict, source_priority: dict[str, int]) -> AttrRule:
        source = a.get("source", "regex")
        return AttrRule(
            slug=a["slug"],
            name=a["name"],
            kind=a["kind"],
            unit=a.get("unit", ""),
            source=source,
            priority=a.get("priority", source_priority.get(source, 0)),
            is_filter=a.get("is_filter", True),
            is_seo_facet=a.get("is_seo_facet", False),
            is_ai_feature=a.get("is_ai_feature", False),
            options=tuple(
                Option(o["value"], o["slug"], tuple(o.get("keywords", [])))
                for o in a.get("options", [])
            ),
            patterns=tuple(re.compile(p) for p in a.get("regex", [])),
            true_keywords=tuple(a.get("true_keywords", [])),
            false_keywords=tuple(a.get("false_keywords", [])),
        )

    def rules_for(self, tool_type_slug: str) -> list[AttrRule]:
        return self._by_tt.get(tool_type_slug, [])

    def extract(self, tool_type_slug: str, name: str) -> list[AttrValue]:
        """Извлечь все характеристики из названия товара указанного tool_type."""
        norm = normalize(name)
        out: list[AttrValue] = []
        for rule in self.rules_for(tool_type_slug):
            value = self._extract_one(rule, norm)
            if value is not None:
                out.append(value)
        return out

    @staticmethod
    def _extract_one(rule: AttrRule, norm: str) -> AttrValue | None:
        if rule.kind == SELECT:
            for opt in rule.options:
                for kw in opt.keywords:
                    if normalize(kw) in norm:
                        return AttrValue(
                            slug=rule.slug,
                            kind=SELECT,
                            source=rule.source,
                            priority=rule.priority,
                            option_slug=opt.slug,
                            option_value=opt.value,
                            unit=rule.unit,
                            matched=kw,
                        )
            return None

        if rule.kind == NUMBER:
            for pat in rule.patterns:
                m = pat.search(norm)
                if not m:
                    continue
                try:
                    num = Decimal(m.group(1).replace(",", "."))
                except (InvalidOperation, IndexError):
                    continue
                return AttrValue(
                    slug=rule.slug,
                    kind=NUMBER,
                    source=rule.source,
                    priority=rule.priority,
                    number=num,
                    unit=rule.unit,
                    matched=m.group(0),
                )
            return None

        if rule.kind == BOOLEAN:
            for kw in rule.false_keywords:
                if normalize(kw) in norm:
                    return AttrValue(
                        slug=rule.slug,
                        kind=BOOLEAN,
                        source=rule.source,
                        priority=rule.priority,
                        boolean=False,
                        matched=kw,
                    )
            for kw in rule.true_keywords:
                if normalize(kw) in norm:
                    return AttrValue(
                        slug=rule.slug,
                        kind=BOOLEAN,
                        source=rule.source,
                        priority=rule.priority,
                        boolean=True,
                        matched=kw,
                    )
            return None

        return None
