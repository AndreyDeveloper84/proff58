import json

import pytest

from apps.catalog.rules_engine import (
    ProductFacts,
    check_negative_fixtures,
    evaluate_product,
    load_ruleset,
    rule_matches,
    validate_against_taxonomy,
)


def _ruleset_dict(**over):
    data = {
        "version": 1,
        "ruleset_id": "tool_type.v1",
        "rules": [
            {
                "rule_ref": "tt-test-001",
                "option_slug": "krep-shplinty",
                "match": {"name_keywords_any": ["шплинт"]},
                "negative_keywords": [],
                "derived_from": [26864, 26865],
            }
        ],
        "negative_fixtures": [],
    }
    data.update(over)
    return data


def test_load_ruleset_valid(tmp_path):
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(_ruleset_dict()), encoding="utf-8")
    rs = load_ruleset(p)
    assert rs.version == 1
    assert rs.ruleset_id == "tool_type.v1"
    assert len(rs.rules) == 1
    assert rs.rules[0].rule_ref == "tt-test-001"
    assert rs.rules[0].tier == "candidate"  # default
    assert len(rs.ruleset_hash) == 64


def test_load_ruleset_rejects_schema_violation(tmp_path):
    bad = _ruleset_dict()
    del bad["rules"][0]["rule_ref"]
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="схеме"):
        load_ruleset(p)


def test_load_ruleset_rejects_duplicate_rule_ref(tmp_path):
    data = _ruleset_dict()
    data["rules"].append(data["rules"][0])
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="rule_ref"):
        load_ruleset(p)


def test_load_ruleset_rejects_empty_match(tmp_path):
    data = _ruleset_dict()
    data["rules"][0]["match"] = {}
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="без единого условия"):
        load_ruleset(p)


def test_ruleset_hash_stable_under_key_reorder(tmp_path):
    data = _ruleset_dict()
    p1 = tmp_path / "r1.json"
    p1.write_text(json.dumps(data), encoding="utf-8")
    reordered = dict(reversed(list(data.items())))
    p2 = tmp_path / "r2.json"
    p2.write_text(json.dumps(reordered), encoding="utf-8")
    assert load_ruleset(p1).ruleset_hash == load_ruleset(p2).ruleset_hash


def _write_ruleset(tmp_path, **over):
    data = _ruleset_dict(**over)
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return load_ruleset(p)


def test_match_is_conjunctive_across_dimensions(tmp_path):
    rs = _write_ruleset(tmp_path)
    rule = rs.rules[0]
    assert rule_matches(rule, ProductFacts(product_id=1, original_name="Шплинт 6,4х76"))
    assert not rule_matches(rule, ProductFacts(product_id=2, original_name="Гвоздь 6х100"))


def test_match_normalization_yo_and_case(tmp_path):
    rs = _write_ruleset(tmp_path)
    rule = rs.rules[0]
    # keyword "шплинт" должен матчить "ШПЛИНТ" и ё-варианты после фолдинга
    assert rule_matches(rule, ProductFacts(product_id=1, original_name="ШПЛИНТ 3,2х50"))


def test_brand_dimension_and_negative_keyword(tmp_path):
    rs = _write_ruleset(
        tmp_path,
        rules=[
            {
                "rule_ref": "tt-brand-001",
                "option_slug": "siz-ochki",
                "match": {"brand_any": ["Hitachi"], "name_keywords_any": ["очки"]},
                "negative_keywords": ["чехол"],
            }
        ],
    )
    rule = rs.rules[0]
    ok = ProductFacts(product_id=1, original_name="Очки защитные", brand="HITACHI")
    wrong_brand = ProductFacts(product_id=2, original_name="Очки защитные", brand="Зубр")
    negated = ProductFacts(product_id=3, original_name="Чехол для очков", brand="Hitachi")
    assert rule_matches(rule, ok)
    assert not rule_matches(rule, wrong_brand)
    assert not rule_matches(rule, negated)


def test_evaluate_excludes_existing_tool_type(tmp_path):
    rs = _write_ruleset(tmp_path)
    verdict = evaluate_product(
        rs.rules, ProductFacts(product_id=1, original_name="Шплинт", has_tool_type=True)
    )
    assert verdict.status == "excluded_existing_tool_type"


def test_evaluate_same_slug_multi_rule_single_prediction(tmp_path):
    rs = _write_ruleset(
        tmp_path,
        rules=[
            {
                "rule_ref": "tt-a-001",
                "option_slug": "krep-shplinty",
                "match": {"name_keywords_any": ["шплинт"]},
            },
            {
                "rule_ref": "tt-a-002",
                "option_slug": "krep-shplinty",
                "match": {"article_prefix_any": ["DIN94"]},
            },
        ],
    )
    verdict = evaluate_product(
        rs.rules, ProductFacts(product_id=1, original_name="Шплинт", article="DIN94-6X76")
    )
    assert verdict.status == "prediction"
    assert verdict.option_slug == "krep-shplinty"
    assert verdict.rule_refs == ("tt-a-001", "tt-a-002")


def test_evaluate_different_slugs_is_collision(tmp_path):
    rs = _write_ruleset(
        tmp_path,
        rules=[
            {
                "rule_ref": "tt-a-001",
                "option_slug": "krep-shplinty",
                "match": {"name_keywords_any": ["шплинт"]},
            },
            {
                "rule_ref": "tt-b-001",
                "option_slug": "krep-gvozdi",
                "match": {"name_keywords_any": ["шплинт"]},
            },
        ],
    )
    verdict = evaluate_product(rs.rules, ProductFacts(product_id=1, original_name="Шплинт"))
    assert verdict.status == "collision"
    assert verdict.slugs == ("krep-gvozdi", "krep-shplinty")
    assert verdict.rule_refs == ("tt-a-001", "tt-b-001")


def test_validate_against_taxonomy(tmp_path):
    rs = _write_ruleset(tmp_path)
    assert validate_against_taxonomy(rs, {"krep-shplinty"}) == []
    assert validate_against_taxonomy(rs, {"other"}) == ["krep-shplinty"]


def test_check_negative_fixtures(tmp_path):
    rs = _write_ruleset(
        tmp_path,
        negative_fixtures=[
            {"name": "Пассатижи комбинированные", "note": "не шплинт"},
        ],
    )
    assert check_negative_fixtures(rs) == []
    rs_bad = _write_ruleset(
        tmp_path,
        negative_fixtures=[{"name": "Шплинт оцинкованный"}],
    )
    violations = check_negative_fixtures(rs_bad)
    assert len(violations) == 1
    assert "tt-test-001" in violations[0]
