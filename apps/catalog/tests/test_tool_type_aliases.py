"""Тесты слоя aliases ``legacy root name → live root name`` (ENRICH-DRYRUN-ALIASES)."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

from apps.catalog.tool_type import ToolTypeRules
from apps.catalog.tool_type_aliases import ROOT_ALIASES, AliasConfigError, resolve_live_to_legacy


class TestRootAliasesConstant:
    def test_exactly_two_aliases(self):
        assert len(ROOT_ALIASES) == 2

    def test_confirmed_pairs(self):
        assert ROOT_ALIASES == {
            "Спецодежда и защита": "Спецодежда и СИЗ",
            "Строительное и отделочное": "Строительный и отделочный инструмент",
        }


class TestResolveHitMiss:
    def test_hit_resolves_live_to_legacy(self):
        rule_categories = {"Спецодежда и защита", "Строительное и отделочное", "Запчасти"}
        result = resolve_live_to_legacy(rule_categories)
        assert result == {
            "Спецодежда и СИЗ": "Спецодежда и защита",
            "Строительный и отделочный инструмент": "Строительное и отделочное",
        }

    def test_miss_is_simply_absent_no_fuzzy(self):
        # Похожее, но не идентичное live-имя не попадает в lookup ни при каких условиях —
        # только точное совпадение.
        rule_categories = {"Спецодежда и защита"}
        result = resolve_live_to_legacy(
            rule_categories, aliases={"Спецодежда и защита": "Спецодежда и СИЗ"}
        )
        assert "СПЕЦОДЕЖДА И СИЗ" not in result
        assert "Спецодежда и СИЗ " not in result
        assert " Спецодежда и СИЗ" not in result
        assert result == {"Спецодежда и СИЗ": "Спецодежда и защита"}

    def test_custom_aliases_param_used_over_default(self):
        rule_categories = {"Легаси"}
        result = resolve_live_to_legacy(rule_categories, aliases={"Легаси": "Живая"})
        assert result == {"Живая": "Легаси"}


class TestCollision:
    def test_legacy_block_missing_raises(self):
        rule_categories = {"Запчасти"}  # без "Спецодежда и защита"
        with pytest.raises(AliasConfigError, match="alias_legacy_block_missing"):
            resolve_live_to_legacy(
                rule_categories, aliases={"Спецодежда и защита": "Спецодежда и СИЗ"}
            )

    def test_live_name_collides_with_own_direct_block(self):
        # Live-имя alias-цели само уже является отдельным rule-блоком — двусмысленность.
        rule_categories = {"Легаси", "Живая"}
        with pytest.raises(AliasConfigError, match="alias_collision"):
            resolve_live_to_legacy(rule_categories, aliases={"Легаси": "Живая"})

    def test_two_legacy_blocks_map_to_same_live_name(self):
        rule_categories = {"Легаси1", "Легаси2"}
        with pytest.raises(AliasConfigError, match="alias_collision"):
            resolve_live_to_legacy(
                rule_categories, aliases={"Легаси1": "Живая", "Легаси2": "Живая"}
            )

    def test_no_exception_raised_before_full_validation_short_circuits_safely(self):
        # Порядок aliases (dict) не должен влиять на то, что коллизия в итоге обнаружена.
        rule_categories = {"Легаси1", "Легаси2"}
        with pytest.raises(AliasConfigError):
            resolve_live_to_legacy(
                rule_categories, aliases={"Легаси2": "Живая", "Легаси1": "Живая"}
            )


class TestRealRulesFileWiring:
    """Реальный ``data/tool_type_rules.json``: подтверждённые 2 alias резолвятся без ошибок."""

    def test_real_ruleset_resolves_confirmed_aliases(self):
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")
        rule_categories = {c.category for c in rules.categories}
        result = resolve_live_to_legacy(rule_categories)
        assert result == {
            "Спецодежда и СИЗ": "Спецодежда и защита",
            "Строительный и отделочный инструмент": "Строительное и отделочное",
        }
