"""Regression replay утверждённого ruleset v1 на applied corpus (Phase 7A).

Stage 7 закрыт 2026-07-21: 11/11 candidate-правил approved,
``expected_recall = 0.59`` approved (measured 32/54 = 0.5926).
Replay — regression-check, НЕ gate (правила выведены из этих же товаров);
gate precision ≥ 99% выполняется в Phase 7B на независимой выборке.

Порог 0.59 сохраняет все 32 покрытых товара: потеря любого из них даёт
31/54 ≈ 0.5741 < 0.59 и роняет тест. Все 22 mismatch обязаны быть
``no_match`` — wrong-slug prediction или collision недопустимы.

Taxonomy-проверка ruleset выполняется против НЕЗАВИСИМОГО pinned export
(``tool_type_taxonomy_export.v1.json`` — read-only snapshot staging
2026-07-21, 328 rows / 327 unique slugs), а не против taxonomy,
построенной из самого ruleset: циклический тест не способен упасть
(review PR #581). Export одновременно документирует DEVIATION-2
(duplicate slug ``steplery``).
"""

import json
from dataclasses import replace
from pathlib import Path

from django.conf import settings

from apps.catalog.management.commands.catalog_rules_shadow import Command as ShadowCommand
from apps.catalog.queue_contract import _taxonomy_hash
from apps.catalog.rules_engine import (
    ProductFacts,
    check_negative_fixtures,
    evaluate_product,
    load_corpus,
    load_ruleset,
    validate_against_taxonomy,
)

RULESET_PATH = Path(settings.BASE_DIR) / "data" / "catalog_processing_rules" / "tool_type.v1.json"
CORPUS_PATH = (
    Path(settings.BASE_DIR)
    / "data"
    / "catalog_processing_rules"
    / "applied_corpus_tool_type.v1.json"
)

TAXONOMY_EXPORT_PATH = (
    Path(settings.BASE_DIR)
    / "data"
    / "catalog_processing_rules"
    / "tool_type_taxonomy_export.v1.json"
)

EXPECTED_ITEMS = 54
EXPECTED_CORRECT = 32
APPROVED_EXPECTED_RECALL = 0.59
# pinned staging taxonomy 2026-07-21 (DEVIATION-2: duplicate slug steplery)
PINNED_TAXONOMY_ROWS = 328
PINNED_TAXONOMY_UNIQUE_SLUGS = 327
PINNED_TAXONOMY_HASH = "1100482c4c074499cf3950d902de84e1afe70c0e80b6ee363c777a4b7c1f5a9f"


def _pinned_export() -> dict:
    return json.loads(TAXONOMY_EXPORT_PATH.read_text(encoding="utf-8"))


def _pinned_allowed_slugs() -> set[str]:
    return {o["slug"] for o in _pinned_export()["options"]}


def test_ruleset_loads():
    ruleset = load_ruleset(RULESET_PATH)
    assert ruleset.ruleset_id == "tool_type.v1"
    assert len(ruleset.rules) == 11


def test_corpus_loads_with_approved_expected_recall():
    corpus = load_corpus(CORPUS_PATH)
    assert len(corpus.items) == EXPECTED_ITEMS
    assert corpus.expected_recall == APPROVED_EXPECTED_RECALL


def test_negative_fixtures_hold():
    assert check_negative_fixtures(load_ruleset(RULESET_PATH)) == []


def test_derived_from_subset_of_corpus():
    ruleset = load_ruleset(RULESET_PATH)
    corpus_ids = load_corpus(CORPUS_PATH).product_ids
    leaked = [r.rule_ref for r in ruleset.rules if not set(r.derived_from) <= corpus_ids]
    assert leaked == []


def test_ruleset_slugs_exist_in_pinned_taxonomy():
    """Ruleset проверяется против НЕЗАВИСИМОГО pinned staging export —
    источника, который не строится из проверяемого ruleset (review PR #581:
    циклический тест, создающий options из slug'ов ruleset, не способен
    обнаружить опечатку или удалённый taxonomy slug)."""
    ruleset = load_ruleset(RULESET_PATH)
    assert validate_against_taxonomy(ruleset, _pinned_allowed_slugs()) == []


def test_taxonomy_check_catches_unknown_slug():
    """Negative: подмена одного option_slug на несуществующий обязана
    вернуть нарушение — доказывает, что проверка способна падать."""
    ruleset = load_ruleset(RULESET_PATH)
    broken_rule = replace(ruleset.rules[0], option_slug="krep-shplintyy")
    broken = replace(ruleset, rules=(broken_rule,) + ruleset.rules[1:])
    assert validate_against_taxonomy(broken, _pinned_allowed_slugs()) == ["krep-shplintyy"]


def test_pinned_taxonomy_integrity_and_deviation_2():
    """Целостность pinned export + фиксация DEVIATION-2 (duplicate slug
    steplery): 328 строк, 327 уникальных slug, hash пересчитывается."""
    export = _pinned_export()
    rows = export["options"]
    assert export["count"] == len(rows) == PINNED_TAXONOMY_ROWS
    assert len({o["slug"] for o in rows}) == PINNED_TAXONOMY_UNIQUE_SLUGS
    assert _taxonomy_hash(rows) == export["taxonomy_hash"] == PINNED_TAXONOMY_HASH
    steplery_values = sorted(o["value"] for o in rows if o["slug"] == "steplery")
    assert steplery_values == ["Степлеры (скобозабивные)", "Степлеры и заклёпочники"]


def test_replay_meets_approved_recall():
    ruleset = load_ruleset(RULESET_PATH)
    replay = ShadowCommand._replay(ruleset, CORPUS_PATH)
    assert replay["items"] == EXPECTED_ITEMS
    assert replay["correct"] == EXPECTED_CORRECT
    assert replay["expected_recall"] == APPROVED_EXPECTED_RECALL
    assert replay["recall"] >= replay["expected_recall"]
    # все mismatches — no_match: ни одного wrong-slug prediction,
    # ни одной collision (collision попала бы в mismatches со своим status)
    assert len(replay["mismatches"]) == 22
    assert all(m["status"] == "no_match" and m["predicted"] == "" for m in replay["mismatches"])


def test_every_rule_hits_exactly_its_derived_from():
    ruleset = load_ruleset(RULESET_PATH)
    corpus = load_corpus(CORPUS_PATH)
    candidate = [r for r in ruleset.rules if r.tier == "candidate"]
    hits = {r.rule_ref: set() for r in candidate}
    for item in corpus.items:
        facts = ProductFacts(
            product_id=item.product_id,
            name=item.name,
            original_name=item.original_name,
            brand=item.brand,
            source_group=item.source_group,
            article=item.article,
        )
        verdict = evaluate_product(candidate, facts)
        assert verdict.status != "collision"
        for ref in verdict.rule_refs:
            hits[ref].add(item.product_id)
    for rule in candidate:
        assert hits[rule.rule_ref] == set(rule.derived_from)
