import json

import pytest

from apps.catalog.rules_engine import load_ruleset


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
