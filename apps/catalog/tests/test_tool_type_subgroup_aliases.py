"""Тесты слоя subgroup aliases ``legacy subgroup → live leaf name(s)``
(ENRICH-WRITE-PATH-HARDENING)."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

from apps.catalog.tool_type import ToolTypeRules
from apps.catalog.tool_type_subgroup_aliases import (
    SUBGROUP_ALIASES,
    SubgroupAliasConfigError,
    known_subgroup_identities,
    resolve_live_subgroup_to_legacy,
)


class TestKnownSubgroupIdentities:
    def test_collects_override_subgroups_and_base_types(self):
        rules = ToolTypeRules.from_dict(
            {
                "version": 1,
                "categories": [
                    {
                        "category": "Оснастка и расходники",
                        "extraction": "inherit_1c_subgroup",
                        "rules": [
                            {"tool_type": "Сверла", "slug": "sverla"},
                            {
                                "tool_type": "Переходные кольца",
                                "slug": "perehodnye-koltsa",
                                "subgroup": "Сверла",
                                "match_keywords": ["кольцо переходн"],
                            },
                        ],
                    }
                ],
            }
        )
        cat_rules = rules.get("Оснастка и расходники")
        assert known_subgroup_identities(cat_rules) == {"Сверла"}


class TestResolveHitMiss:
    def test_hit_resolves_live_leaf_to_legacy_subgroup(self):
        known = {"Пики и долота", "Сверла"}
        result = resolve_live_subgroup_to_legacy(
            "Оснастка и расходники",
            known,
            aliases={"Оснастка и расходники": {"Пики и долота": ("Пики, долота и зубила",)}},
        )
        assert result == {"Пики, долота и зубила": "Пики и долота"}

    def test_many_to_one_live_leaves(self):
        known = {"Алмазные круги"}
        result = resolve_live_subgroup_to_legacy(
            "Оснастка и расходники",
            known,
            aliases={
                "Оснастка и расходники": {
                    "Алмазные круги": ("Алмазная оснастка", "Диски", "Чашки"),
                }
            },
        )
        assert result == {
            "Алмазная оснастка": "Алмазные круги",
            "Диски": "Алмазные круги",
            "Чашки": "Алмазные круги",
        }

    def test_unrelated_category_returns_empty(self):
        result = resolve_live_subgroup_to_legacy(
            "Другая категория", {"Сверла"}, aliases={"Оснастка и расходники": {"Сверла": ("X",)}}
        )
        assert result == {}


class TestCollision:
    def test_missing_legacy_subgroup_raises(self):
        known = {"Сверла"}  # без "Пики и долота"
        with pytest.raises(SubgroupAliasConfigError, match="subgroup_alias_legacy_missing"):
            resolve_live_subgroup_to_legacy(
                "Оснастка и расходники",
                known,
                aliases={"Оснастка и расходники": {"Пики и долота": ("X",)}},
            )

    def test_live_name_already_resolving_is_redundant(self):
        # "Сверла" уже само по себе известная подгруппа — alias на него избыточен.
        known = {"Сверла", "Буры"}
        with pytest.raises(SubgroupAliasConfigError, match="subgroup_alias_redundant"):
            resolve_live_subgroup_to_legacy(
                "Оснастка и расходники",
                known,
                aliases={"Оснастка и расходники": {"Буры": ("Сверла",)}},
            )

    def test_live_name_matches_via_normalize_is_also_redundant(self):
        # "Свёрла" (ё) нормализуется в то же, что известная подгруппа "Сверла".
        known = {"Сверла", "Буры"}
        with pytest.raises(SubgroupAliasConfigError, match="subgroup_alias_redundant"):
            resolve_live_subgroup_to_legacy(
                "Оснастка и расходники",
                known,
                aliases={"Оснастка и расходники": {"Буры": ("Свёрла",)}},
            )

    def test_two_legacy_subgroups_claim_same_live_leaf(self):
        known = {"Пики и долота", "Буры"}
        with pytest.raises(SubgroupAliasConfigError, match="subgroup_alias_collision"):
            resolve_live_subgroup_to_legacy(
                "Оснастка и расходники",
                known,
                aliases={
                    "Оснастка и расходники": {
                        "Пики и долота": ("X",),
                        "Буры": ("X",),
                    }
                },
            )


class TestRealRulesFileWiring:
    """Реальный ``data/tool_type_rules.json``: подтверждённые subgroup aliases
    резолвятся без ошибок и не конфликтуют друг с другом."""

    def test_confirmed_aliases_resolve_without_error(self):
        rules = ToolTypeRules.from_file(Path(settings.BASE_DIR) / "data" / "tool_type_rules.json")
        cat_rules = rules.get("Оснастка и расходники")
        result = resolve_live_subgroup_to_legacy(
            "Оснастка и расходники", known_subgroup_identities(cat_rules)
        )
        assert result == {
            "Пики, долота и зубила": "Пики и долота",
            "Алмазная оснастка": "Алмазные круги",
            "Диски": "Алмазные круги",
            "Чашки": "Алмазные круги",
            "Мешки-пылесборники": "Мешки для пылесосов",
        }

    def test_krugi_leaf_is_not_mapped(self):
        # "Круги" (id=82) — подтверждённая смешанная корзина, НЕ должна попасть
        # ни в один legacy-таргет (owner-decision, не техническое решение).
        for live_names in SUBGROUP_ALIASES.get("Оснастка и расходники", {}).values():
            assert "Круги" not in live_names
