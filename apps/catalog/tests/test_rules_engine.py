import json

import pytest

from apps.catalog.rules_engine import (
    ProductFacts,
    check_negative_fixtures,
    describe_match,
    evaluate_product,
    keyword_matches_text,
    load_ruleset,
    rule_matches,
    tokenize,
    validate_against_taxonomy,
)


def _ruleset_dict(**over):
    data = {
        "version": 1,
        "ruleset_id": "tool_type.v1",
        "rules": [
            {
                "rule_ref": "tt-krep-shplinty-001",
                "option_slug": "krep-shplinty",
                "match": {
                    "source_group_any": ["Крепёж"],
                    "original_name_keywords_any": ["шплинт"],
                },
                "negative_keywords": [],
                "derived_from": [26864, 26865],
            }
        ],
        "negative_fixtures": [
            {
                "fixture_ref": "nf-shplinty-001",
                "rule_refs": ["tt-krep-shplinty-001"],
                "name": "Гвоздь строительный 6х100",
                "source_group": "Крепёж",
            }
        ],
    }
    data.update(over)
    return data


def _rule(rule_ref, slug, match, **kw):
    """Валидный candidate-правило v2 (≥2 измерения + derived_from)."""
    rule = {
        "rule_ref": rule_ref,
        "option_slug": slug,
        "match": match,
        "negative_keywords": [],
        "derived_from": [26864, 26865],
    }
    rule.update(kw)
    return rule


def _fixture(fixture_ref, rule_refs, **facts):
    fix = {
        "fixture_ref": fixture_ref,
        "rule_refs": rule_refs,
        "name": "Гвоздь строительный 6х100",
    }
    fix.update(facts)
    return fix


def _write_ruleset(tmp_path, **over):
    data = _ruleset_dict(**over)
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return load_ruleset(p)


# --- load_ruleset: schema + семантический валидатор ---


def test_load_ruleset_valid(tmp_path):
    rs = _write_ruleset(tmp_path)
    assert rs.version == 1
    assert rs.ruleset_id == "tool_type.v1"
    assert len(rs.rules) == 1
    assert rs.rules[0].rule_ref == "tt-krep-shplinty-001"
    assert rs.rules[0].tier == "candidate"  # default
    assert len(rs.ruleset_hash) == 64


def test_candidate_requires_two_dimensions(tmp_path):
    data = _ruleset_dict()
    data["rules"][0]["match"] = {"original_name_keywords_any": ["шплинт"]}
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="измерен"):
        load_ruleset(p)


def test_any_tier_requires_one_dimension(tmp_path):
    # shadow_regression с пустым match тоже обязана иметь ≥1 непустое измерение
    data = _ruleset_dict()
    data["rules"][0]["tier"] = "shadow_regression"
    data["rules"][0]["derived_from"] = []
    data["rules"][0]["match"] = {}
    data["negative_fixtures"] = []
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="непустых измерений"):
        load_ruleset(p)


def test_keyword_only_must_be_regression_tier(tmp_path):
    data = _ruleset_dict()
    data["rules"][0]["match"] = {"original_name_keywords_any": ["шплинт"]}
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="shadow_regression"):
        load_ruleset(p)
    # то же правило с tier=shadow_regression валидно (derived_from/fixture не нужны)
    data["rules"][0]["tier"] = "shadow_regression"
    data["rules"][0]["derived_from"] = []
    data["negative_fixtures"] = []
    p.write_text(json.dumps(data), encoding="utf-8")
    rs = load_ruleset(p)
    assert rs.rules[0].tier == "shadow_regression"


def test_candidate_requires_two_derived_from(tmp_path):
    for bad in ([26864], [26864, 26864]):
        data = _ruleset_dict()
        data["rules"][0]["derived_from"] = bad
        p = tmp_path / "ruleset.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="derived_from"):
            load_ruleset(p)


def test_dimension_values_normalized_unique(tmp_path):
    data = _ruleset_dict()
    data["rules"][0]["match"]["original_name_keywords_any"] = ["Шплинт", "шплинт"]
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="дубли"):
        load_ruleset(p)


def test_keyword_min_length(tmp_path):
    data = _ruleset_dict()
    data["rules"][0]["match"]["original_name_keywords_any"] = ["оч"]
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="символ"):
        load_ruleset(p)


def test_keyword_min_length_measured_by_tokens(tmp_path):
    # «оч!» — 3 символа после normalize, но самый длинный токен — 2
    data = _ruleset_dict()
    data["rules"][0]["match"]["original_name_keywords_any"] = ["оч!"]
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="символ"):
        load_ruleset(p)


def test_empty_after_tokenize_rejected(tmp_path):
    data = _ruleset_dict()
    data["rules"][0]["match"]["original_name_keywords_any"] = ["!!!"]
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="tokenize"):
        load_ruleset(p)


def test_candidate_requires_own_fixture(tmp_path):
    rules = [
        _rule(
            "tt-a-001",
            "krep-shplinty",
            {"original_name_keywords_any": ["шплинт"], "source_group_any": ["Крепёж"]},
        ),
        _rule(
            "tt-b-001",
            "krep-gvozdi",
            {"original_name_keywords_any": ["гвоздь"], "source_group_any": ["Крепёж"]},
        ),
    ]
    # fixture ссылается только на tt-b-001 — у tt-a-001 своей fixture нет
    rs = _ruleset_dict(rules=rules, negative_fixtures=[_fixture("nf-b-001", ["tt-b-001"])])
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(rs), encoding="utf-8")
    with pytest.raises(ValueError, match="fixture"):
        load_ruleset(p)


def test_fixture_unknown_rule_ref(tmp_path):
    data = _ruleset_dict()
    data["negative_fixtures"][0]["rule_refs"] = ["tt-ghost-999"]
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="rule_ref"):
        load_ruleset(p)


def test_duplicate_predicates_rejected(tmp_path):
    match = {"original_name_keywords_any": ["шплинт"], "source_group_any": ["Крепёж"]}
    rules = [
        _rule("tt-a-001", "krep-shplinty", dict(match)),
        _rule("tt-b-001", "krep-gvozdi", dict(match)),
    ]
    fixtures = [_fixture("nf-a-001", ["tt-a-001"]), _fixture("nf-b-001", ["tt-b-001"])]
    data = _ruleset_dict(rules=rules, negative_fixtures=fixtures)
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="дубликат"):
        load_ruleset(p)


def test_schema_violation_still_rejected(tmp_path):
    bad = _ruleset_dict()
    del bad["rules"][0]["rule_ref"]
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="схеме"):
        load_ruleset(p)


def test_duplicate_rule_ref_rejected(tmp_path):
    data = _ruleset_dict()
    data["rules"].append(dict(data["rules"][0]))
    p = tmp_path / "ruleset.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="rule_ref"):
        load_ruleset(p)


def test_ruleset_hash_stable_under_key_reorder(tmp_path):
    data = _ruleset_dict()
    p1 = tmp_path / "r1.json"
    p1.write_text(json.dumps(data), encoding="utf-8")
    reordered = dict(reversed(list(data.items())))
    p2 = tmp_path / "r2.json"
    p2.write_text(json.dumps(reordered), encoding="utf-8")
    assert load_ruleset(p1).ruleset_hash == load_ruleset(p2).ruleset_hash


def test_load_ruleset_invalid_json(tmp_path):
    # битый JSON — понятный ValueError (P1.9), а не голый JSONDecodeError traceback
    p = tmp_path / "ruleset.json"
    p.write_text("{ не json", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON"):
        load_ruleset(p)


def test_load_ruleset_missing_file(tmp_path):
    # отсутствующий файл — понятный ValueError с путём (P1.9), а не FileNotFoundError
    with pytest.raises(ValueError, match="не найден"):
        load_ruleset(tmp_path / "no-such-ruleset.json")


def test_empty_ruleset_valid(tmp_path):
    # пустой ruleset ("rules": []) валиден (P1.9): ни схема, ни семантика не требуют ≥1 правила
    rs = _write_ruleset(tmp_path, rules=[], negative_fixtures=[])
    assert rs.rules == ()
    assert rs.negative_fixtures == ()
    assert len(rs.ruleset_hash) == 64


# --- Токены и keyword-семантика (P1.2) ---


def test_tokenize_separators():
    assert tokenize("Шплинт 6,4х76 (DIN 94)") == ["шплинт", "6", "4х76", "din", "94"]


def test_keyword_prefix_matches_morphology():
    assert keyword_matches_text("шплинт", "Шплинты 6,4х76")


def test_keyword_no_substring_match():
    assert not keyword_matches_text("болгарка", "Гайка болгарская М8")


def test_phrase_keyword_consecutive():
    assert keyword_matches_text("ключ динамометрический", "Ключ динамометрический 1/2")
    # порядок токенов важен
    assert not keyword_matches_text("ключ динамометрический", "динамометрический ключ")


# --- matching: раздельные поля, evidence, veto ---


def test_field_separation(tmp_path):
    rs = _write_ruleset(
        tmp_path,
        rules=[
            _rule(
                "tt-orig-001",
                "krep-shplinty",
                {"original_name_keywords_any": ["шплинт"], "source_group_any": ["Крепёж"]},
            ),
            _rule(
                "tt-name-001",
                "krep-shplinty",
                {"name_keywords_any": ["шплинт"], "source_group_any": ["Крепёж"]},
            ),
        ],
        negative_fixtures=[
            _fixture("nf-orig-001", ["tt-orig-001"]),
            _fixture("nf-name-001", ["tt-name-001"]),
        ],
    )
    orig_rule, name_rule = rs.rules
    only_name = ProductFacts(
        product_id=1, name="Шплинт 6,4х76", original_name="", source_group="Крепёж"
    )
    only_orig = ProductFacts(
        product_id=2, name="", original_name="Шплинт 6,4х76", source_group="Крепёж"
    )
    # keyword original_name_keywords_any НЕ матчит слово, которое только в name
    assert not rule_matches(orig_rule, only_name)
    assert rule_matches(orig_rule, only_orig)
    # и наоборот
    assert rule_matches(name_rule, only_name)
    assert not rule_matches(name_rule, only_orig)


def test_match_evidence_records_field(tmp_path):
    rs = _write_ruleset(tmp_path)
    rule = rs.rules[0]
    facts = ProductFacts(product_id=1, original_name="Шплинты 6,4х76", source_group="Крепёж")
    detail = describe_match(rule, facts)
    assert detail["matched"] is True
    assert "original_name_keywords_any" in detail["dimensions"]
    assert "source_group_any" in detail["dimensions"]
    assert detail["keywords"]["original_name"] == ["шплинт"]


def test_brand_and_negative_veto(tmp_path):
    rs = _write_ruleset(
        tmp_path,
        rules=[
            _rule(
                "tt-brand-001",
                "siz-ochki",
                {"brand_any": ["Hitachi"], "original_name_keywords_any": ["очки"]},
                negative_keywords=["чехол"],
            )
        ],
        negative_fixtures=[
            _fixture("nf-brand-001", ["tt-brand-001"], name="Перчатки рабочие", brand="Hitachi")
        ],
    )
    rule = rs.rules[0]
    ok = ProductFacts(product_id=1, original_name="Очки защитные", brand="HITACHI")
    wrong_brand = ProductFacts(product_id=2, original_name="Очки защитные", brand="Зубр")
    negated = ProductFacts(product_id=3, original_name="Чехол для очков", brand="Hitachi")
    assert rule_matches(rule, ok)
    assert not rule_matches(rule, wrong_brand)
    assert not rule_matches(rule, negated)
    assert describe_match(rule, negated)["vetoed_by"] == "чехол"


# --- evaluate_product ---


def test_evaluate_excludes_existing_tool_type(tmp_path):
    rs = _write_ruleset(tmp_path)
    verdict = evaluate_product(
        rs.rules,
        ProductFacts(
            product_id=1, original_name="Шплинт", source_group="Крепёж", has_tool_type=True
        ),
    )
    assert verdict.status == "excluded_existing_tool_type"


def test_same_slug_multi_rule(tmp_path):
    rs = _write_ruleset(
        tmp_path,
        rules=[
            _rule(
                "tt-a-001",
                "krep-shplinty",
                {"original_name_keywords_any": ["шплинт"], "source_group_any": ["Крепёж"]},
            ),
            _rule(
                "tt-a-002",
                "krep-shplinty",
                {"article_prefix_any": ["DIN94"], "source_group_any": ["Крепёж"]},
            ),
        ],
        negative_fixtures=[
            _fixture("nf-a-001", ["tt-a-001"]),
            _fixture("nf-a-002", ["tt-a-002"]),
        ],
    )
    verdict = evaluate_product(
        rs.rules,
        ProductFacts(
            product_id=1,
            original_name="Шплинт 6,4х76",
            article="DIN94-6X76",
            source_group="Крепёж",
        ),
    )
    assert verdict.status == "prediction"
    assert verdict.option_slug == "krep-shplinty"
    assert verdict.rule_refs == ("tt-a-001", "tt-a-002")
    assert set(verdict.evidence) == {"tt-a-001", "tt-a-002"}
    assert all(d["matched"] for d in verdict.evidence.values())


def test_collision(tmp_path):
    rs = _write_ruleset(
        tmp_path,
        rules=[
            _rule(
                "tt-a-001",
                "krep-shplinty",
                {"original_name_keywords_any": ["шплинт"], "source_group_any": ["Крепёж"]},
            ),
            _rule(
                "tt-b-001",
                "krep-gvozdi",
                {
                    "original_name_keywords_any": ["шплинт", "гвоздь"],
                    "source_group_any": ["Крепёж"],
                },
            ),
        ],
        negative_fixtures=[
            _fixture("nf-a-001", ["tt-a-001"]),
            _fixture("nf-b-001", ["tt-b-001"]),
        ],
    )
    verdict = evaluate_product(
        rs.rules, ProductFacts(product_id=1, original_name="Шплинт", source_group="Крепёж")
    )
    assert verdict.status == "collision"
    assert verdict.slugs == ("krep-gvozdi", "krep-shplinty")
    assert verdict.rule_refs == ("tt-a-001", "tt-b-001")


def test_validate_against_taxonomy(tmp_path):
    rs = _write_ruleset(tmp_path)
    assert validate_against_taxonomy(rs, {"krep-shplinty"}) == []
    assert validate_against_taxonomy(rs, {"other"}) == ["krep-shplinty"]


def test_check_negative_fixtures_scoped(tmp_path):
    rules = [
        _rule(
            "tt-a-001",
            "krep-shplinty",
            {"original_name_keywords_any": ["шплинт"], "source_group_any": ["Крепёж"]},
        ),
        _rule(
            "tt-b-001",
            "instr-passatizhi",
            {"original_name_keywords_any": ["пассатижи"], "source_group_any": ["Крепёж"]},
        ),
    ]
    # tt-a-001 матчит nf-b-001 («Шплинт…»), но не связан с ней → violation нет;
    # tt-b-001 матчит nf-a-001 («Пассатижи…»), но тоже не связан → violation нет.
    fixtures = [
        _fixture("nf-a-001", ["tt-a-001"], name="Пассатижи комбинированные", source_group="Крепёж"),
        _fixture("nf-b-001", ["tt-b-001"], name="Шплинт 6,4х76", source_group="Крепёж"),
    ]
    rs = _write_ruleset(tmp_path, rules=rules, negative_fixtures=fixtures)
    assert check_negative_fixtures(rs) == []
    # связываем nf-a-001 с tt-b-001 → связанное правило матчит fixture → violation
    fixtures[0] = dict(fixtures[0], rule_refs=["tt-a-001", "tt-b-001"])
    rs_bad = _write_ruleset(tmp_path, rules=rules, negative_fixtures=fixtures)
    violations = check_negative_fixtures(rs_bad)
    assert len(violations) == 1
    assert "tt-b-001" in violations[0]


def test_fixture_name_populates_both_name_fields(tmp_path):
    # keyword из name_keywords_any матчит fixture по полю name → ровно 1 violation
    rules = [
        _rule(
            "tt-name-001",
            "siz-ochki",
            {"brand_any": ["Hitachi"], "name_keywords_any": ["очки"]},
        )
    ]
    fixtures = [_fixture("nf-name-001", ["tt-name-001"], name="Очки защитные", brand="Hitachi")]
    rs = _write_ruleset(tmp_path, rules=rules, negative_fixtures=fixtures)
    violations = check_negative_fixtures(rs)
    assert len(violations) == 1
    assert "tt-name-001" in violations[0]
