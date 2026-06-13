"""Движок авторазбора товаров по категориям сайта.

Применяет правила CategoryMappingRule по возрастанию priority. Первое
сработавшее правило определяет категорию. Если ничего не сработало —
возвращает (None, None), и товар уходит в «Неразобранные».

Это единственное место, где принимается решение о категории при импорте.
Группа из 1С (source_group) сама по себе категорию НЕ задаёт — она может
лишь участвовать как образец в правиле типа SOURCE_GROUP.
"""

from __future__ import annotations

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


def _rule_matches(rule: CategoryMappingRule, hint: ProductHint) -> bool:
    pattern = _norm(rule.pattern)
    if not pattern:
        return False

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


def categorize(hint: ProductHint) -> tuple[Category | None, CategoryMappingRule | None]:
    """Подобрать категорию сайта по правилам. Вернуть (категория, правило)."""
    rules = (
        CategoryMappingRule.objects.filter(is_active=True)
        .select_related("target_category")
        .order_by("priority", "id")
    )
    for rule in rules:
        if _rule_matches(rule, hint):
            return rule.target_category, rule
    return None, None
