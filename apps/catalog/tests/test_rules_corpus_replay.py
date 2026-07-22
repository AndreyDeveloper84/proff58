"""Regression replay утверждённого ruleset v1 на applied corpus (Phase 7A).

Stage 7 закрыт 2026-07-21: 11/11 candidate-правил approved,
``expected_recall = 0.59`` approved (measured 32/54 = 0.5926).
Replay — regression-check, НЕ gate (правила выведены из этих же товаров);
gate precision ≥ 99% выполняется в Phase 7B на независимой выборке.

Порог 0.59 сохраняет все 32 покрытых товара: потеря любого из них даёт
31/54 ≈ 0.5741 < 0.59 и роняет тест. Все 22 mismatch обязаны быть
``no_match`` — wrong-slug prediction или collision недопустимы.
"""

from pathlib import Path

import pytest
from django.conf import settings

from apps.catalog.management.commands.catalog_rules_shadow import Command as ShadowCommand
from apps.catalog.models import Attribute, AttributeOption, AttributeType
from apps.catalog.queue_contract import _allowed_tool_type_options
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

EXPECTED_ITEMS = 54
EXPECTED_CORRECT = 32
APPROVED_EXPECTED_RECALL = 0.59


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


@pytest.mark.django_db
def test_ruleset_slugs_exist_in_taxonomy():
    attr = Attribute.objects.get_or_create(
        slug="tool_type",
        defaults={"name": "Тип инструмента", "attribute_type": AttributeType.SELECT},
    )[0]
    ruleset = load_ruleset(RULESET_PATH)
    for slug in sorted({r.option_slug for r in ruleset.rules}):
        AttributeOption.objects.get_or_create(attribute=attr, slug=slug, defaults={"value": slug})
    allowed = {o["slug"] for o in _allowed_tool_type_options()}
    assert validate_against_taxonomy(ruleset, allowed) == []


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
