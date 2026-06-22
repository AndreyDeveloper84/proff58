"""Движок извлечения атрибута ``tool_type`` из данных 1С.

`tool_type` — это АТРИБУТ товара (вторая ось навигации / SEO-фасет), а НЕ узел
дерева категорий (ADR-0001). Здесь — чистая логика правил из
``tool_type_rules.json`` без обращения к БД: её используют и команда
``enrich_tool_type``, и юнит-тесты.

Две стратегии извлечения (поле ``extraction`` категории верхнего уровня):

* ``priority_keyword`` — приоритетный матч по ключевым словам в названии.
  Название приводится к нижнему регистру, ``ё`` → ``е``; правила перебираются
  ПО ПОРЯДКУ, выигрывает первое, чьё любое ключевое слово — подстрока названия.
  Правило с ``action == "recategorize"`` помечает «товар не в той категории»
  и tool_type НЕ присваивает.
* ``inherit_1c_subgroup`` — tool_type берётся из подгруппы 1С (она уже
  типизирована), парсинг названия не нужен.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


def normalize(text: str | None) -> str:
    """Нормализация для матчинга: нижний регистр и ``ё`` → ``е``."""
    return (text or "").lower().replace("ё", "е")


# Транслитерация кириллицы для ЧПУ-слугов (латиница, как у слугов категорий):
# tool_type/категория → /catalog/elektroinstrument/, а не /catalog/электроинструмент/.
_TRANSLIT = {
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
    "ц": "ts",
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


def transliterate(text: str) -> str:
    """Кириллица → латиница по таблице ``_TRANSLIT`` (для построения слугов)."""
    return "".join(_TRANSLIT.get(ch, _TRANSLIT.get(ch.lower(), ch)) for ch in text.lower())


# Результаты извлечения (совпадают с EnrichmentResult в models).
ASSIGNED = "assigned"
MODERATION = "moderation"
RECATEGORIZE = "recategorize"
INHERIT = "inherit"  # для категорий inherit_1c_subgroup — tool_type берётся из подгруппы


@dataclass(frozen=True)
class Rule:
    tool_type: str
    slug: str
    match_keywords: tuple[str, ...] = ()
    action: str | None = None  # None | "recategorize"

    @property
    def is_recategorize(self) -> bool:
        return self.action == "recategorize"


@dataclass
class CategoryRules:
    category: str
    extraction: str
    rules: list[Rule] = field(default_factory=list)


@dataclass
class Extraction:
    """Итог разбора одного товара."""

    result: str  # ASSIGNED | MODERATION | RECATEGORIZE
    tool_type: str = ""
    slug: str = ""
    matched_keyword: str = ""


class ToolTypeRules:
    """Загруженный и проиндексированный словарь правил."""

    def __init__(self, categories: list[CategoryRules]):
        self._by_category = {c.category: c for c in categories}
        self.categories = categories

    @classmethod
    def from_file(cls, path: str | Path) -> ToolTypeRules:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> ToolTypeRules:
        cats: list[CategoryRules] = []
        for c in data.get("categories", []):
            rules = [
                Rule(
                    tool_type=r["tool_type"],
                    slug=r["slug"],
                    match_keywords=tuple(r.get("match_keywords", [])),
                    action=r.get("action"),
                )
                for r in c.get("rules", [])
            ]
            cats.append(
                CategoryRules(category=c["category"], extraction=c["extraction"], rules=rules)
            )
        return cls(cats)

    def get(self, top_category: str) -> CategoryRules | None:
        return self._by_category.get(top_category)

    def options(self, top_category: str) -> list[Rule]:
        """tool_type-варианты категории БЕЗ recategorize (их не грузим как варианты)."""
        cat = self._by_category.get(top_category)
        if not cat:
            return []
        return [r for r in cat.rules if not r.is_recategorize]

    def extract(self, top_category: str, name: str, subgroup: str = "") -> Extraction:
        """Определить tool_type товара по его категории верхнего уровня.

        ``subgroup`` нужен только для категорий с ``inherit_1c_subgroup`` —
        это подгруппа 1С (лист дерева), которая и есть тип.
        """
        cat = self._by_category.get(top_category)
        if cat is None:
            return Extraction(result=MODERATION)

        if cat.extraction == "inherit_1c_subgroup":
            sub = (subgroup or "").strip()
            if not sub:
                return Extraction(result=MODERATION)
            slug = self._inherit_slug(cat, sub)
            return Extraction(result=ASSIGNED, tool_type=sub, slug=slug)

        # priority_keyword: первый матч выигрывает
        norm_name = normalize(name)
        for rule in cat.rules:
            for kw in rule.match_keywords:
                if normalize(kw) in norm_name:
                    if rule.is_recategorize:
                        return Extraction(
                            result=RECATEGORIZE,
                            tool_type=rule.tool_type,
                            slug=rule.slug,
                            matched_keyword=kw,
                        )
                    return Extraction(
                        result=ASSIGNED,
                        tool_type=rule.tool_type,
                        slug=rule.slug,
                        matched_keyword=kw,
                    )
        return Extraction(result=MODERATION)

    @staticmethod
    def _inherit_slug(cat: CategoryRules, subgroup: str) -> str:
        """Slug для inherit-подгруппы: канонический из правил по нормализованному
        совпадению имени, иначе пусто (загрузчик сгенерирует из имени)."""
        target = normalize(subgroup)
        for rule in cat.rules:
            if normalize(rule.tool_type) == target:
                return rule.slug
        return ""
