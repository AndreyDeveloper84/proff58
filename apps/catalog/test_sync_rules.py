"""Тесты E2 — мост «словарь → CategoryMappingRule» и regex+exclude в движке.

Проверяют:
  * categorize() понимает rule_type=REGEX и exclude_pattern (негативный guard);
  * catalog_sync_rules генерирует regex-правила на v2-узлы; новые товары 1С
    раздела авто-классифицируются; повторный прогон идемпотентен.

Нужен PostgreSQL.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.categorization import ProductHint, categorize
from apps.catalog.models import Category, CategoryMappingRule, MappingRuleType


@pytest.mark.django_db
def test_regex_rule_with_exclude():
    root = Category.add_root(name="Оснастка и расходные материалы", slug="osnastka")
    bury = root.add_child(name="Буры", slug="bury")
    CategoryMappingRule.objects.create(
        rule_type=MappingRuleType.REGEX,
        pattern=r"\bбур\b",
        exclude_pattern=r"бурения земл|мотобур",
        target_category=bury,
        priority=1000,
    )

    cat, _rule = categorize(ProductHint(name="Бур SDS-Plus 12х260 мм"))
    assert cat is not None and cat.pk == bury.pk
    # Негативный guard: «бур для бурения земли» — НЕ оснастка (мотобур/садовый).
    cat2, rule2 = categorize(ProductHint(name="Бур д/бурения земли 100 мм HUTER"))
    assert cat2 is None and rule2 is None


@pytest.mark.django_db
def test_sync_rules_builds_and_categorizes():
    root = Category.add_root(name="Оснастка и расходные материалы", slug="osnastka")
    sverla = root.add_child(name="Свёрла", slug="sverla")
    root.add_child(name="Буры", slug="bury")

    out = StringIO()
    call_command("catalog_sync_rules", "--section", "osnastka", "--commit", stdout=out)
    assert "COMMIT:" in out.getvalue()

    # Созданы regex-правила на узел Свёрла.
    sverla_rules = CategoryMappingRule.objects.filter(
        rule_type=MappingRuleType.REGEX, target_category=sverla
    )
    assert sverla_rules.exists()
    assert all(r.note.startswith("[auto:osnastka]") for r in sverla_rules)

    # Новый товар 1С авто-классифицируется в Свёрла.
    cat, rule = categorize(ProductHint(name="Сверло по металлу 6 мм HSS Bosch"))
    assert cat is not None and cat.pk == sverla.pk
    assert rule.rule_type == MappingRuleType.REGEX

    # Не-оснастка — в «Неразобранные» (None).
    none_cat, _ = categorize(ProductHint(name="Молоток слесарный 500 г"))
    assert none_cat is None


@pytest.mark.django_db
def test_sync_rules_idempotent():
    root = Category.add_root(name="Оснастка и расходные материалы", slug="osnastka")
    root.add_child(name="Свёрла", slug="sverla")

    call_command("catalog_sync_rules", "--section", "osnastka", "--commit", stdout=StringIO())
    n1 = CategoryMappingRule.objects.filter(note__startswith="[auto:osnastka]").count()
    call_command("catalog_sync_rules", "--section", "osnastka", "--commit", stdout=StringIO())
    n2 = CategoryMappingRule.objects.filter(note__startswith="[auto:osnastka]").count()
    assert n1 == n2 and n1 > 0  # пересозданы, не задвоились
