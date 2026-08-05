"""Движок извлечения характеристик товара (EAV) из названия 1С.

Зеркало :mod:`apps.catalog.tool_type`: чистая логика правил из
``data/attribute_rules.json`` без обращения к БД. Используется командами
``load_attributes`` / ``enrich_attributes`` / ``attribute_coverage`` и тестами.

Три вида (``kind``) характеристик:

* ``select``  — значение из списка вариантов; перебор вариантов ПО ПОРЯДКУ,
  выигрывает первый, чьё любое ключевое слово — подстрока названия. Порядок
  важен: ``brushless`` должен стоять раньше ``brushed`` («бесщеточный» содержит
  «щеточный»). Opt-in флаг правила ``word_boundary: true`` переводит матч на
  «целое слово» (границы с обеих сторон, механика :mod:`apps.catalog.tool_type`)
  — для буквенных значений вроде размеров перчаток (``s`` внутри ``STELS``).
* ``number``  — число + единица; первый сработавший regex даёт значение
  (``Decimal``, запятая → точка).
* ``boolean`` — да/нет по whitelist: сначала ``false_keywords``, затем
  ``true_keywords``; иначе значение не извлекается.
* ``text``    — открытое строковое значение: первый сработавший regex, группа 1
  → строка (НЕ Decimal). Значение берётся из исходного названия (регистр
  сохраняется: «CB-155») и trim-ится; пустое после trim = не извлечено.

Любое правило может объявить ``skip_if`` — список стоп-слов. Если хоть одно из них
входит в нормализованное название, правило **не применяется целиком** (значение не
извлекается). Нужно для товаров, у которых характеристики в единственном числе не
существует: «Набор ключей 6-19 мм, 8 шт.» не имеет одного «размера под ключ». Выразить
это в regex нельзя — Python не поддерживает lookbehind переменной длины.

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

from .tool_type import (
    _keyword_ends_at_word_boundary,
    _keyword_starts_at_word_boundary,
    keyword_at_word_boundary,
    normalize,
)

SELECT = "select"
NUMBER = "number"
BOOLEAN = "boolean"
TEXT = "text"


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
    derive: dict | None = None  # инференс по другим атрибутам (см. _derive_one)
    skip_if: tuple[str, ...] = ()  # стоп-слова: правило целиком не применяется
    # select: матчить ключевые слова только целым словом (границы с обеих сторон).
    # По умолчанию выключено — поведение существующих select-правил не меняется.
    word_boundary: bool = False


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
    text: str = ""
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
            derive=a.get("derive"),
            skip_if=tuple(a.get("skip_if", [])),
            word_boundary=a.get("word_boundary", False),
        )

    def rules_for(self, tool_type_slug: str) -> list[AttrRule]:
        return self._by_tt.get(tool_type_slug, [])

    def extract(self, tool_type_slug: str, name: str) -> list[AttrValue]:
        """Извлечь все характеристики из названия товара указанного tool_type.

        Два прохода: сначала обычные правила (regex/keyword/boolean), затем
        derive-правила — инференс по уже извлечённым атрибутам (см. _derive_one).
        """
        norm = normalize(name)
        out: list[AttrValue] = []
        for rule in self.rules_for(tool_type_slug):
            value = self._extract_one(rule, norm, name)
            if value is not None:
                out.append(value)
        present = {v.slug for v in out}
        for rule in self.rules_for(tool_type_slug):
            if rule.derive is None or rule.slug in present:
                continue
            value = self._derive_one(rule, present)
            if value is not None:
                out.append(value)
                present.add(value.slug)
        return out

    def _derive_one(self, rule: AttrRule, present: set[str]) -> AttrValue | None:
        """Инференс select-значения по наличию/отсутствию других атрибутов.

        Фолбэк того же правила: если keyword/regex ничего не дали (свой slug ещё
        НЕ извлечён), значение выводится из соседних атрибутов. Срабатывает, если:
        * все ``requires_present`` присутствуют;
        * ни один ``requires_absent`` не присутствует.
        Источник берётся из ``derive.source`` (по умолчанию ``inferred`` —
        слабейший приоритет, корректируется keyword/1С/ручным).
        """
        d = rule.derive or {}
        if any(s not in present for s in d.get("requires_present", [])):
            return None
        if any(s in present for s in d.get("requires_absent", [])):
            return None
        opt = next((o for o in rule.options if o.slug == d.get("set_option")), None)
        if opt is None:
            return None
        source = d.get("source", "inferred")
        return AttrValue(
            slug=rule.slug,
            kind=SELECT,
            source=source,
            priority=self.source_priority.get(source, 0),
            option_slug=opt.slug,
            option_value=opt.value,
            unit=rule.unit,
            matched="(inferred)",
        )

    @staticmethod
    def _skip_if_matches(norm: str, norm_kw: str) -> bool:
        """Проверить вхождение стоп-слова с учётом границы слова.

        * Стоп-слово без ведущего пробела (например ``"комплект"``) требует
          границы начала: матчит «комплект»/«комплекта», но не «БОЕКОМПЛЕКТ».
        * Стоп-слово с ведущим пробелом (например ``" шт"``) требует
          границы конца: матчит «10 шт»/«10 шт.", но не «штампованный».

        Это сохраняет словоформы (набор/наборе, комплект/комплекта/комплекте)
        и одновременно не ломает слова, в которых подстрока — часть другого слова.
        """
        if not norm_kw:
            return False
        # Граница конца нужна, если стоп-слово начинается с пробела.
        check_end = norm_kw.startswith(" ")
        idx = norm.find(norm_kw)
        while idx != -1:
            if check_end:
                if _keyword_ends_at_word_boundary(norm, idx + len(norm_kw)):
                    return True
            else:
                if _keyword_starts_at_word_boundary(norm, idx):
                    return True
            idx = norm.find(norm_kw, idx + 1)
        return False

    @staticmethod
    def _extract_one(rule: AttrRule, norm: str, raw: str = "") -> AttrValue | None:
        # Стоп-слова правила: у товара-набора «размер»/«диаметр» один назвать нельзя
        # («Набор ключей 6-19 мм, 8 шт.»), поэтому правило не применяется целиком —
        # это надёжнее, чем пытаться выразить исключение в regex.
        if any(AttributeRules._skip_if_matches(norm, normalize(kw)) for kw in rule.skip_if):
            return None

        if rule.kind == SELECT:
            for opt in rule.options:
                for kw in opt.keywords:
                    norm_kw = normalize(kw)
                    # opt-in word_boundary: ключевое слово — целое слово (обе границы);
                    # без флага — голая подстрока, как было всегда.
                    hit = (
                        keyword_at_word_boundary(norm, norm_kw)
                        if rule.word_boundary
                        else norm_kw in norm
                    )
                    if hit:
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

        if rule.kind == TEXT:
            for pat in rule.patterns:
                m = pat.search(norm)
                if not m:
                    continue
                try:
                    start, end = m.span(1)
                except IndexError:
                    continue
                # Значение — из ИСХОДНОГО названия: normalize() сохраняет длину
                # (регистр + ё→е), поэтому span матча по norm валиден и для raw.
                # Коды вроде «CB-155» не должны терять регистр. Если длина вдруг
                # изменилась (экзотика Unicode) — откат на normalize()-нный фрагмент.
                raw_value = raw[start:end] if len(raw) == len(norm) else m.group(1)
                value = raw_value.strip()
                if not value:
                    continue
                return AttrValue(
                    slug=rule.slug,
                    kind=TEXT,
                    source=rule.source,
                    priority=rule.priority,
                    text=value,
                    matched=m.group(0),
                )
            return None

        return None
