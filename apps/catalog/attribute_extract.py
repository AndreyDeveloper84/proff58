"""Движок извлечения характеристик товара из его названия (Фаза B, #96).

Зеркало ``tool_type.py``, но для произвольных атрибутов: напряжение, крутящий
момент, наличие аккумулятора, тип питания/двигателя. Чистая логика правил из
``attribute_rules.json`` без обращения к БД — её используют команды
``load_attributes``/``enrich_attributes``/``attribute_coverage`` и юнит-тесты.

Правила сгруппированы по ``tool_type`` (значение атрибута tool_type, например
«Дрели и шуруповёрты»). У каждого атрибута один из видов извлечения:

* ``number`` — regex-словарь вариантов написания (``18В``, ``18 V``, ``20V``…);
  первый сработавший паттерн даёт число (``,`` → ``.``). Источник ``name_regex``.
* ``boolean`` — словарь подстрок. **Порядок важен:** сначала негативные
  («без АКБ», «без ЗУ и АКБ» → False), потом позитивные («с АКБ» → True), иначе
  «с акб» ложно срабатывает на «без АКБ и ЗУ». Источник ``name_keyword``.
* ``select`` — варианты с ключевыми словами; первый вариант, чьё слово —
  подстрока названия, выигрывает. Источник ``name_keyword``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .source_priority import Source
from .tool_type import normalize

# Уверенность по источнику (шкала 0–100, см. ProductAttributeValue.confidence).
CONFIDENCE_REGEX = 100
CONFIDENCE_KEYWORD = 90

# Виды извлечения атрибута.
KIND_NUMBER = "number"
KIND_BOOLEAN = "boolean"
KIND_SELECT = "select"

# Соответствие kind → AttributeType (строкой, чтобы не тянуть модели в чистый движок).
KIND_TO_ATTRIBUTE_TYPE = {
    KIND_NUMBER: "decimal",
    KIND_BOOLEAN: "boolean",
    KIND_SELECT: "select",
}


@dataclass(frozen=True)
class OptionSpec:
    value: str
    slug: str
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttributeSpec:
    slug: str
    name: str
    kind: str  # number | boolean | select
    unit: str = ""
    is_filter: bool = True
    is_seo_facet: bool = False
    is_ai_feature: bool = False
    filter_kind: str = "select"  # select | range
    patterns: tuple[str, ...] = ()  # number
    true_patterns: tuple[str, ...] = ()  # boolean (позитивные)
    false_patterns: tuple[str, ...] = ()  # boolean (негативные)
    options: tuple[OptionSpec, ...] = ()  # select

    @property
    def attribute_type(self) -> str:
        return KIND_TO_ATTRIBUTE_TYPE[self.kind]


@dataclass(frozen=True)
class ToolTypeAttributes:
    tool_type: str  # значение атрибута tool_type, напр. «Дрели и шуруповёрты»
    slug: str  # slug этого tool_type (dreli-shurupoverty)
    category: str  # категория верхнего уровня, к которой биндим атрибуты
    attributes: list[AttributeSpec] = field(default_factory=list)


@dataclass
class ExtractedValue:
    """Итог извлечения одного атрибута у одного товара."""

    spec: AttributeSpec
    decimal: float | None = None
    boolean: bool | None = None
    option_value: str = ""
    option_slug: str = ""
    matched: str = ""
    source: str = Source.NAME_REGEX
    confidence: int = CONFIDENCE_REGEX


class AttributeRules:
    """Загруженный и проиндексированный словарь правил характеристик."""

    def __init__(self, tool_types: list[ToolTypeAttributes]):
        self.tool_types = tool_types
        self._by_value = {t.tool_type: t for t in tool_types}
        self._by_slug = {t.slug: t for t in tool_types}

    @classmethod
    def from_file(cls, path: str | Path) -> AttributeRules:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> AttributeRules:
        items: list[ToolTypeAttributes] = []
        for t in data.get("tool_types", []):
            specs = [cls._spec_from_dict(a) for a in t.get("attributes", [])]
            items.append(
                ToolTypeAttributes(
                    tool_type=t["tool_type"],
                    slug=t.get("slug", ""),
                    category=t.get("category", ""),
                    attributes=specs,
                )
            )
        return cls(items)

    @staticmethod
    def _spec_from_dict(a: dict) -> AttributeSpec:
        rules = a.get("rules", {})
        options = tuple(
            OptionSpec(
                value=o["value"],
                slug=o.get("slug", ""),
                keywords=tuple(o.get("keywords", [])),
            )
            for o in a.get("options", [])
        )
        return AttributeSpec(
            slug=a["slug"],
            name=a["name"],
            kind=a["kind"],
            unit=a.get("unit", ""),
            is_filter=a.get("is_filter", True),
            is_seo_facet=a.get("is_seo_facet", False),
            is_ai_feature=a.get("is_ai_feature", False),
            filter_kind=a.get("filter_kind", "select"),
            patterns=tuple(a.get("patterns", [])),
            true_patterns=tuple(rules.get("true", [])),
            false_patterns=tuple(rules.get("false", [])),
            options=options,
        )

    # --- доступ ----------------------------------------------------------

    def get(self, tool_type: str) -> ToolTypeAttributes | None:
        """Найти набор атрибутов по значению tool_type или по его slug."""
        return self._by_value.get(tool_type) or self._by_slug.get(tool_type)

    def specs(self, tool_type: str) -> list[AttributeSpec]:
        item = self.get(tool_type)
        return list(item.attributes) if item else []

    # --- извлечение ------------------------------------------------------

    def extract_all(self, tool_type: str, name: str) -> list[ExtractedValue]:
        """Все найденные значения характеристик для товара данного tool_type."""
        norm = normalize(name)
        out: list[ExtractedValue] = []
        for spec in self.specs(tool_type):
            value = self._extract_one(spec, norm)
            if value is not None:
                out.append(value)
        return out

    def _extract_one(self, spec: AttributeSpec, norm: str) -> ExtractedValue | None:
        if spec.kind == KIND_NUMBER:
            return self._extract_number(spec, norm)
        if spec.kind == KIND_BOOLEAN:
            return self._extract_boolean(spec, norm)
        if spec.kind == KIND_SELECT:
            return self._extract_select(spec, norm)
        return None

    @staticmethod
    def _extract_number(spec: AttributeSpec, norm: str) -> ExtractedValue | None:
        for pattern in spec.patterns:
            m = re.search(pattern, norm)
            if m:
                raw = m.group(1).replace(",", ".")
                try:
                    number = float(raw)
                except ValueError:
                    continue
                return ExtractedValue(
                    spec=spec,
                    decimal=number,
                    matched=m.group(0),
                    source=Source.NAME_REGEX,
                    confidence=CONFIDENCE_REGEX,
                )
        return None

    @staticmethod
    def _extract_boolean(spec: AttributeSpec, norm: str) -> ExtractedValue | None:
        # Порядок критичен: негативные ДО позитивных («без АКБ и ЗУ» → False).
        for kw in spec.false_patterns:
            if normalize(kw) in norm:
                return ExtractedValue(
                    spec=spec,
                    boolean=False,
                    matched=kw,
                    source=Source.NAME_KEYWORD,
                    confidence=CONFIDENCE_KEYWORD,
                )
        for kw in spec.true_patterns:
            if normalize(kw) in norm:
                return ExtractedValue(
                    spec=spec,
                    boolean=True,
                    matched=kw,
                    source=Source.NAME_KEYWORD,
                    confidence=CONFIDENCE_KEYWORD,
                )
        return None

    @staticmethod
    def _extract_select(spec: AttributeSpec, norm: str) -> ExtractedValue | None:
        for opt in spec.options:
            for kw in opt.keywords:
                if normalize(kw) in norm:
                    return ExtractedValue(
                        spec=spec,
                        option_value=opt.value,
                        option_slug=opt.slug,
                        matched=kw,
                        source=Source.NAME_KEYWORD,
                        confidence=CONFIDENCE_KEYWORD,
                    )
        return None
