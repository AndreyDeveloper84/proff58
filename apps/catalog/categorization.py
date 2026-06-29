"""Движок авторазбора товаров по категориям сайта.

Применяет правила CategoryMappingRule по возрастанию priority. Первое
сработавшее правило определяет категорию. Если ничего не сработало —
возвращает (None, None), и товар уходит в «Неразобранные».

Это единственное место, где принимается решение о категории при импорте.
Группа из 1С (source_group) сама по себе категорию НЕ задаёт — она может
лишь участвовать как образец в правиле типа SOURCE_GROUP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Category, CategoryMappingRule, MappingRuleType


@dataclass
class ProductHint:
    """Признаки товара, по которым подбирается категория."""

    name: str = ""
    article: str = ""
    brand: str = ""
    source_group: str = ""


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _rxname(value: str | None) -> str:
    """Нормализация имени под regex: lower + ё→е + паддинг (как в классификаторе)."""
    return " " + re.sub(r"\s+", " ", (value or "").lower().replace("ё", "е")) + " "


def _safe_search(pattern: str, text: str) -> bool:
    try:
        return re.search(pattern, text) is not None
    except re.error:
        return False  # битый regex в правиле не должен ронять импорт


def _rule_matches(rule: CategoryMappingRule, hint: ProductHint) -> bool:
    pattern = _norm(rule.pattern)
    if not pattern:
        return False

    # Негативный guard по имени (regex): правило НЕ срабатывает при совпадении.
    if rule.exclude_pattern and _safe_search(rule.exclude_pattern, _rxname(hint.name)):
        return False

    if rule.rule_type == MappingRuleType.REGEX:
        return _safe_search(rule.pattern, _rxname(hint.name))

    if rule.rule_type == MappingRuleType.ARTICLE:
        return pattern == _norm(hint.article)

    if rule.rule_type == MappingRuleType.NAME_CONTAINS:
        return pattern in _norm(hint.name)

    if rule.rule_type == MappingRuleType.SOURCE_GROUP:
        return pattern == _norm(hint.source_group)

    if rule.rule_type == MappingRuleType.BRAND_PREFIX:
        # Совпадает бренд И серия (pattern) встречается в названии или артикуле.
        brand_ok = _norm(rule.brand) == _norm(hint.brand) if rule.brand else True
        series_ok = pattern in _norm(hint.name) or pattern in _norm(hint.article)
        return brand_ok and series_ok

    return False


def load_active_rules() -> list[CategoryMappingRule]:
    """Активные правила по приоритету — один запрос (для пакетной категоризации, #125)."""
    return list(
        CategoryMappingRule.objects.filter(is_active=True)
        .select_related("target_category")
        .order_by("priority", "id")
    )


def categorize(
    hint: ProductHint, rules: list[CategoryMappingRule] | None = None
) -> tuple[Category | None, CategoryMappingRule | None]:
    """Подобрать категорию сайта по правилам. Вернуть (категория, правило).

    ``rules`` — предзагруженный список (пакетный импорт передаёт его, чтобы не читать
    `CategoryMappingRule` на каждую строку); если ``None`` — читаем сами (одиночный путь).
    """
    if rules is None:
        rules = load_active_rules()
    for rule in rules:
        if _rule_matches(rule, hint):
            return rule.target_category, rule
    return None, None
