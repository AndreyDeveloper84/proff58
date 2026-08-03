"""Движок извлечения атрибута ``tool_type`` из данных 1С.

`tool_type` — это АТРИБУТ товара (вторая ось навигации / SEO-фасет), а НЕ узел
дерева категорий (ADR-0001). Здесь — чистая логика правил из
``tool_type_rules.json`` без обращения к БД: её используют и команда
``enrich_tool_type``, и юнит-тесты.

Две стратегии извлечения (поле ``extraction`` категории верхнего уровня):

* ``priority_keyword`` — приоритетный матч по ключевым словам в названии.
  Название приводится к нижнему регистру, ``ё`` → ``е``; правила перебираются
  ПО ПОРЯДКУ, выигрывает первое, чьё любое ключевое слово — подстрока названия,
  начинающаяся на границе слова (``match_keywords``). Ключи из
  ``match_keywords_word`` дополнительно обязаны ЗАКАНЧИВАТЬСЯ на границе слова —
  для коротких корней вроде «вал», которые иначе захватили бы «валик»/«вальцы».
  Правило с ``action == "recategorize"`` помечает «товар не в той категории»
  и tool_type НЕ присваивает.
* ``inherit_1c_subgroup`` — tool_type берётся из подгруппы 1С (она уже
  типизирована), парсинг названия не нужен.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


def normalize(text: str | None) -> str:
    """Нормализация для матчинга: нижний регистр и ``ё`` → ``е``."""
    return (text or "").lower().replace("ё", "е")


_WORD_CHAR = re.compile(r"[a-zа-я0-9]")  # применяется к уже normalize()-нному тексту

# Guard — ТОЧЕЧНЫЙ список подтверждённых ложных срабатываний priority_keyword
# (ALIAS-CONFLICT-374-report.md, 7 групп/25 товаров): слово-триггер описывает
# аксессуар/цель применения ВНУТРИ названия основного товара, а не сам товар
# («пистолет ДЛЯ герметиков», «(маска+краги)», «...с кисточкой», «...с головкой
# и стволом», «...(очки) с подсветкой», «...фартуком для защиты руки», «...под
# огнетушитель»). НЕ применяется ко всем ключевым словам ruleset — глобальный
# контекстный фильтр ломает валидные срабатывания за пределами этих 7 групп
# (напр. «Штифт СО шплинтом», «...ПОД шплинт» в блоке «Крепёж и метизы» —
# регрессия, обнаруженная прогоном 13 блоков; см. условие остановки промпта).
# Ключ — normalize()-нное ключевое слово ИЗ ПРАВИЛА (как в match_keywords).
_PURPOSE_PREFIXES = ("для ", "под ")
_BUNDLE_LOOKBACK_WORDS = 3
_BUNDLE_MARKER_WORDS = {"с", "со", "и"}

_GUARDED_KEYWORDS: dict[str, dict[str, object]] = {
    # str-pistolety vs str-germetiki: «Пистолет ДЛЯ герметиков».
    "герметик": {"purpose": True},
    # krepleniya-ognetushiteley vs siz-ognetushiteli: «Подставка ПОД огнетушитель».
    "огнетушитель": {"purpose": True},
    # izm-lupy vs siz-ochki: «Лупа... (очки) с подсветкой» / «Лупа... очки с подсветкой».
    "очки": {"parens": True, "cooccurs_with": ("лупа",)},
    # siz-rukava vs siz-golovki: «Рукав... с головкой ГР-50 Ал и стволом РС-50».
    "головка": {"bundle": True},
    "ствол": {"bundle": True},
    # zubila vs siz-odezhda: «Зубило с пластмассовым фартуком для защиты руки».
    "фартук": {"bundle": True},
    # svar-apparaty vs siz-perchatki: «...(маска+краги)».
    "краги": {"parens": True, "plus": True},
    # str-laki vs str-kisti: «Цапон лак прозрачный с кисточкой».
    "кисточк": {"bundle": True},
}


def _keyword_starts_at_word_boundary(norm_name: str, start: int) -> bool:
    if start == 0:
        return True
    return not _WORD_CHAR.match(norm_name[start - 1])


def _is_accessory_or_purpose_context(norm_name: str, start: int, norm_keyword: str) -> bool:
    """Слово-триггер (из ``_GUARDED_KEYWORDS``) — объект применения/бонус-
    аксессуар внутри названия основного товара, а не сам товар (см.
    alias-conflict-374-report.md). Для остальных ключевых слов — не вызывается."""
    spec = _GUARDED_KEYWORDS.get(norm_keyword)
    if spec is None:
        return False
    prefix = norm_name[:start]
    if spec.get("purpose") and prefix.endswith(_PURPOSE_PREFIXES):
        return True
    if spec.get("plus") and prefix.endswith("+"):
        return True
    if spec.get("parens"):
        open_paren = prefix.rfind("(")
        close_paren = prefix.rfind(")")
        if open_paren != -1 and open_paren > close_paren:
            return True
    if spec.get("bundle"):
        lookback = prefix.split()[-_BUNDLE_LOOKBACK_WORDS:]
        if any(w in _BUNDLE_MARKER_WORDS for w in lookback):
            return True
    cooccurs_with = spec.get("cooccurs_with")
    if cooccurs_with and any(marker in norm_name for marker in cooccurs_with):
        return True
    return False


def find_keyword_match(norm_name: str, keywords: tuple[str, ...]) -> str | None:
    """Первое ключевое слово из ``keywords``, реально совпавшее с ``norm_name``:
    матч должен начинаться на границе слова (см. ``_keyword_starts_at_word_boundary``
    — ловит словоформы вроде «герметиков», но не мусор в середине чужого слова) и,
    для точечного списка ``_GUARDED_KEYWORDS``, не приходиться на контекст
    «объект применения/бонус-аксессуар» (``_is_accessory_or_purpose_context``).
    Возвращает ключевое слово как задано в правиле (не normalize()-нное) — для
    ``matched_keyword``."""
    for kw in keywords:
        norm_kw = normalize(kw)
        if not norm_kw:
            continue
        idx = norm_name.find(norm_kw)
        while idx != -1:
            if _keyword_starts_at_word_boundary(
                norm_name, idx
            ) and not _is_accessory_or_purpose_context(norm_name, idx, norm_kw):
                return kw
            idx = norm_name.find(norm_kw, idx + 1)
    return None


def _keyword_ends_at_word_boundary(norm_name: str, end: int) -> bool:
    if end >= len(norm_name):
        return True
    return not _WORD_CHAR.match(norm_name[end])


def find_word_keyword_match(norm_name: str, keywords: tuple[str, ...]) -> str | None:
    """Как ``find_keyword_match``, но матч обязан ЗАКАНЧИВАТЬСЯ на границе слова.

    Для ключей ``match_keywords_word`` (TT-17): короткий корень ловится только
    как отдельное слово — «вал» совпадает с «Вал гибкий», но не с «валик»,
    «вальцы» или «интервал». Словоформы («валы», «валу», «валом») задаются
    отдельными ключами явно — движок ничего не стеммит.
    """
    for kw in keywords:
        norm_kw = normalize(kw)
        if not norm_kw:
            continue
        idx = norm_name.find(norm_kw)
        while idx != -1:
            if (
                _keyword_starts_at_word_boundary(norm_name, idx)
                and _keyword_ends_at_word_boundary(norm_name, idx + len(norm_kw))
                and not _is_accessory_or_purpose_context(norm_name, idx, norm_kw)
            ):
                return kw
            idx = norm_name.find(norm_kw, idx + 1)
    return None


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
    # Ключи с границей слова С ОБЕИХ сторон (TT-17) — только priority_keyword;
    # в inherit-override не участвуют.
    match_keywords_word: tuple[str, ...] = ()
    action: str | None = None  # None | "recategorize"
    subgroup: str = ""  # для inherit-override: ключевые слова применяются только в этой подгруппе

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
                    match_keywords_word=tuple(r.get("match_keywords_word", [])),
                    action=r.get("action"),
                    subgroup=r.get("subgroup", ""),
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
            # Override по имени ВНУТРИ подгруппы: аксессуары (кольца, чашки, головки,
            # приспособления) внутри товарной подгруппы получают свой tool_type, не
            # засоряя фасет основной подгруппы. Скоуп по subgroup — иначе ключи воруют
            # товары из соседних подгрупп («держатель бит», «торцевые головки»).
            norm_name = normalize(name)
            target = normalize(sub)
            for rule in cat.rules:
                if not (rule.subgroup and rule.match_keywords):
                    continue
                if normalize(rule.subgroup) != target:
                    continue
                matched = find_keyword_match(norm_name, rule.match_keywords)
                if matched is not None:
                    return Extraction(
                        result=ASSIGNED,
                        tool_type=rule.tool_type,
                        slug=rule.slug,
                        matched_keyword=matched,
                    )
            slug = self._inherit_slug(cat, sub)
            if not slug:
                # Подгруппа не резолвится ни override'ом (выше), ни базовым
                # rule.tool_type — оставлять tool_type=сырое имя листа (с пустым
                # slug) означало бы протащить в БД значение вне манифеста
                # (option_not_in_manifest на запись). Явный subgroup-mapping —
                # apps.catalog.tool_type_subgroup_aliases — таких случаев не
                # покрывает намеренно (см. окно ENRICH-WRITE-PATH-HARDENING).
                return Extraction(result=MODERATION)
            return Extraction(result=ASSIGNED, tool_type=sub, slug=slug)

        # priority_keyword: первый матч выигрывает
        norm_name = normalize(name)
        for rule in cat.rules:
            matched = find_keyword_match(norm_name, rule.match_keywords)
            if matched is None:
                matched = find_word_keyword_match(norm_name, rule.match_keywords_word)
            if matched is not None:
                if rule.is_recategorize:
                    return Extraction(
                        result=RECATEGORIZE,
                        tool_type=rule.tool_type,
                        slug=rule.slug,
                        matched_keyword=matched,
                    )
                return Extraction(
                    result=ASSIGNED,
                    tool_type=rule.tool_type,
                    slug=rule.slug,
                    matched_keyword=matched,
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
