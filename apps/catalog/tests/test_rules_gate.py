"""Тесты независимого machine gate (Wave 7.1 / Stage H2).

Gate пересчитывает из первичных versioned inputs (ruleset, corpus, canonical
taxonomy manifest): predictions, rule_refs, facts_hash, overlap,
collision_count, hashes и метрики. Declared-поля артефактов — только объект
сравнения. Негативная матрица: подмена любого declared-поля → fail-closed.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings

from apps.catalog.processing import canonical_hash
from apps.catalog.rules_engine import load_ruleset
from apps.catalog.rules_gate import (
    EXIT_INVALID,
    EXIT_PASSED,
    EXIT_THRESHOLD_FAILED,
    run_independent_gate,
)
from apps.catalog.taxonomy_manifest import manifest_semantic_hash, taxonomy_identity_hash

FIXTURES = Path(__file__).parent / "fixtures"
FROZEN_SAMPLE = FIXTURES / "phase7d-gate-sample-official.json"
FROZEN_LABELS = FIXTURES / "phase7d-labels.json"
REAL_RULESET = Path(settings.BASE_DIR) / "data" / "catalog_processing_rules" / "tool_type.v2.json"
REAL_CORPUS = (
    Path(settings.BASE_DIR)
    / "data"
    / "catalog_processing_rules"
    / "applied_corpus_tool_type.v1.json"
)
LEGACY_TAXONOMY_HASH = "b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b"

RULE_REF = "tt-test-pravilo"
KEYWORD = "перфоратор"


# --- mini-world builders ---------------------------------------------------


def _write(tmp_path, name, doc):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return p


def _ruleset_doc(slug="a-slug", ref=RULE_REF, extra_rules=()):
    return {
        "version": 1,
        "ruleset_id": "tool_type.v99",
        "rules": [
            {
                "rule_ref": ref,
                "option_slug": slug,
                "tier": "candidate",
                "match": {
                    "original_name_keywords_any": [KEYWORD],
                    "source_group_any": ["Электроинструмент"],
                },
                "negative_keywords": [],
                "derived_from": [101, 102],
            }
        ]
        + list(extra_rules),
        "negative_fixtures": [
            {"fixture_ref": "nf-1", "rule_refs": [ref], "name": "молоток обычный"}
        ],
    }


def _manifest_doc():
    options = [
        {"slug": "a-slug", "value": "А", "sort_order": 0},
        {"slug": "b-slug", "value": "Б", "sort_order": 1},
        {"slug": "zzz", "value": "З", "sort_order": 2},
    ]
    doc = {
        "schema_version": 1,
        "manifest_version": 1,
        "attribute_slug": "tool_type",
        "status": "canonical",
        "semantic_duplicate_allowlist": [],
        "options": options,
    }
    doc["taxonomy_identity_hash"] = taxonomy_identity_hash(doc["options"])
    doc["manifest_semantic_hash"] = manifest_semantic_hash(doc)
    return doc


DEFAULT_FACTS_NAME = f"{KEYWORD.title()} Makita HR2470"


def _facts(name=DEFAULT_FACTS_NAME):
    return {
        "name": name,
        "original_name": name,
        "brand": "Makita",
        "source_group": "Электроинструмент",
        "article": "HR2470",
    }


def _row(pid, slug="a-slug", refs=(RULE_REF,), facts=None, facts_hash=None):
    facts = facts or _facts()
    row = {
        "product_id": pid,
        "facts_hash": facts_hash or canonical_hash(facts),
        "predicted_option_slug": slug,
        "rule_refs": list(refs),
    }
    row.update(facts)
    return row


def _corpus_doc(pids=(900001,)):
    items = []
    for pid in pids:
        facts = {k: "" for k in ("name", "original_name", "brand", "source_group", "article")}
        facts["name"] = f"Товар {pid}"
        items.append(
            {
                "product_id": pid,
                "change_id": f"chg-{pid}",
                "pav_id": pid,
                "source": "manual",
                "confidence": 100,
                "applied_at": "2026-07-01T00:00:00Z",
                "applied_option_slug": "a-slug",
                **facts,
                "facts_hash": canonical_hash(facts),
            }
        )
    n = len(items)
    return {
        "version": 1,
        "corpus_id": "test-corpus",
        "counters": {
            "raw_applied_changes": n,
            "distinct_products": n,
            "current_label_corpus": n,
            "historical_label_collisions": 0,
        },
        "items": items,
    }


def _sample_doc(ruleset_hash, taxonomy_hash, rows, **kw):
    doc = {
        "ruleset_hash": ruleset_hash,
        "matcher_version": "1.0",
        "taxonomy_hash": taxonomy_hash,
        "seed": 42,
        "pool": "all",
        "pool_filter_version": "1.0",
        "corpus_overlap_checked": True,
        "collision_count": 0,
        "rows": rows,
    }
    doc.update(kw)
    return doc


def _labels_doc(sample, decisions=None):
    rows = sample["rows"]
    return {
        "sample_hash": canonical_hash(sample),
        "ruleset_hash": sample["ruleset_hash"],
        "matcher_version": sample["matcher_version"],
        "labels": [
            {
                "product_id": r["product_id"],
                "decision": decisions[i] if decisions else "correct",
                "reviewer_id": "tester",
                "reviewed_at": "2026-07-23T00:00:00Z",
            }
            for i, r in enumerate(rows)
        ],
    }


@pytest.fixture
def world(tmp_path):
    """Полный mini-world: ruleset+manifest+corpus+sample(100)+labels(100 correct)."""
    manifest = _write(tmp_path, "manifest.json", _manifest_doc())
    ruleset_p = _write(tmp_path, "ruleset.json", _ruleset_doc())
    corpus_p = _write(tmp_path, "corpus.json", _corpus_doc())
    rs = load_ruleset(ruleset_p)
    import apps.catalog.taxonomy_manifest as tm

    identity = tm.load_manifest(manifest).identity_hash
    rows = [_row(pid) for pid in range(1, 101)]
    sample = _write(tmp_path, "sample.json", _sample_doc(rs.ruleset_hash, identity, rows))
    labels = _write(
        tmp_path, "labels.json", _labels_doc(json.loads(Path(sample).read_text(encoding="utf-8")))
    )
    return {
        "manifest": manifest,
        "ruleset": ruleset_p,
        "corpus": corpus_p,
        "sample": sample,
        "labels": labels,
        "ruleset_hash": rs.ruleset_hash,
        "taxonomy_hash": identity,
        "tmp": tmp_path,
    }


def _gate(world, **overrides):
    kwargs = {
        "ruleset_path": world["ruleset"],
        "corpus_path": world["corpus"],
        "manifest_path": world["manifest"],
        "sample_path": world["sample"],
        "labels_path": world["labels"],
    }
    kwargs.update(overrides)
    return run_independent_gate(**kwargs)


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _rewrite(path, doc):
    Path(path).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


# --- positive ---


def test_mini_world_passes(world):
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_PASSED
    assert outcome.gate_passed is True
    assert outcome.report["metrics"]["precision"] == 1.0
    assert outcome.report["metrics"]["rows"] == 100
    assert outcome.report["replay"]["checked"] == 100
    assert outcome.report["overlap"]["computed_empty"] is True
    assert outcome.report["blocking_errors"] == []


def test_deterministic_rerun(world):
    a = _gate(world).report
    b = _gate(world).report
    a.pop("generated_at")
    b.pop("generated_at")
    assert a == b


def test_permutation_of_rows_and_labels_is_invariant(world):
    sample = _read(world["sample"])
    sample["rows"] = list(reversed(sample["rows"]))
    _rewrite(world["sample"], sample)
    labels = _read(world["labels"])
    labels["labels"] = list(reversed(labels["labels"]))
    labels["sample_hash"] = canonical_hash(sample)
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_PASSED
    assert outcome.gate_passed is True


# --- negative: hash/provenance binding ---


def test_tampered_sample_ruleset_hash_blocks(world):
    sample = _read(world["sample"])
    sample["ruleset_hash"] = "0" * 64
    _rewrite(world["sample"], sample)
    labels = _read(world["labels"])
    labels["sample_hash"] = canonical_hash(sample)
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID
    assert any("sample.ruleset_hash" in e for e in outcome.blocking_errors)


def test_tampered_labels_sample_hash_blocks(world):
    labels = _read(world["labels"])
    labels["sample_hash"] = "0" * 64
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID
    assert any("sample_hash" in e for e in outcome.blocking_errors)


def test_tampered_taxonomy_hash_blocks_without_flag(world):
    sample = _read(world["sample"])
    sample["taxonomy_hash"] = "0" * 64
    _rewrite(world["sample"], sample)
    labels = _read(world["labels"])
    labels["sample_hash"] = canonical_hash(sample)
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID
    assert any("sample.taxonomy_hash" in e for e in outcome.blocking_errors)


def test_legacy_taxonomy_hash_allowed_explicitly(world):
    sample = _read(world["sample"])
    sample["taxonomy_hash"] = "0" * 64
    _rewrite(world["sample"], sample)
    labels = _read(world["labels"])
    labels["sample_hash"] = canonical_hash(sample)
    _rewrite(world["labels"], labels)
    outcome = _gate(world, allow_legacy_taxonomy_hash="0" * 64)
    assert outcome.exit_code == EXIT_PASSED
    mm = outcome.report["declared_mismatches"]
    assert any(
        m["severity"] == "legacy_recipe" and m["field_path"] == "sample.taxonomy_hash" for m in mm
    )


def test_tampered_facts_hash_blocks(world):
    sample = _read(world["sample"])
    sample["rows"][0]["facts_hash"] = "0" * 64
    _rewrite(world["sample"], sample)
    labels = _read(world["labels"])
    labels["sample_hash"] = canonical_hash(sample)
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID
    assert any("facts_hash" in e for e in outcome.blocking_errors)


# --- negative: replay (declared prediction/rule подмена) ---


def test_tampered_predicted_slug_blocks(world):
    sample = _read(world["sample"])
    sample["rows"][0]["predicted_option_slug"] = "b-slug"
    _rewrite(world["sample"], sample)
    labels = _read(world["labels"])
    labels["sample_hash"] = canonical_hash(sample)
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID
    assert any("predicted_option_slug" in e for e in outcome.blocking_errors)


def test_tampered_rule_refs_block(world):
    sample = _read(world["sample"])
    sample["rows"][0]["rule_refs"] = ["tt-podmena"]
    _rewrite(world["sample"], sample)
    labels = _read(world["labels"])
    labels["sample_hash"] = canonical_hash(sample)
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID
    assert any("rule_refs" in e for e in outcome.blocking_errors)


def test_declared_slug_unknown_to_manifest_blocks(world):
    sample = _read(world["sample"])
    sample["rows"][0]["predicted_option_slug"] = "zzz-unknown"
    _rewrite(world["sample"], sample)
    labels = _read(world["labels"])
    labels["sample_hash"] = canonical_hash(sample)
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID


# --- negative: ruleset/manifest/corpus ---


def test_ruleset_slug_outside_manifest_blocks(world, tmp_path):
    ruleset_p = _write(tmp_path / "r2", "ruleset.json", _ruleset_doc(slug="zzz-outside"))
    outcome = _gate(world, ruleset_path=ruleset_p)
    assert outcome.exit_code == EXIT_INVALID
    assert any("вне canonical manifest" in e for e in outcome.blocking_errors)


def test_duplicate_rule_ref_blocks(world, tmp_path):
    dup = {
        "rule_ref": RULE_REF,
        "option_slug": "b-slug",
        "tier": "candidate",
        "match": {
            "original_name_keywords_any": ["дубликат"],
            "source_group_any": ["Электроинструмент"],
        },
        "negative_keywords": [],
        "derived_from": [103, 104],
    }
    ruleset_p = _write(tmp_path / "r2", "ruleset.json", _ruleset_doc(extra_rules=[dup]))
    outcome = _gate(world, ruleset_path=ruleset_p)
    assert outcome.exit_code == EXIT_INVALID
    assert any("Дубли rule_ref" in e or "ruleset" in e for e in outcome.blocking_errors)


def test_corrupted_manifest_blocks(world):
    manifest = _read(world["manifest"])
    manifest["taxonomy_identity_hash"] = "0" * 64
    _rewrite(world["manifest"], manifest)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID
    assert any("taxonomy manifest" in e for e in outcome.blocking_errors)


def test_overlap_with_corpus_blocks(world):
    corpus = _read(world["corpus"])
    corpus["items"][0]["product_id"] = 1  # product_id=1 есть в sample
    corpus["items"][0]["change_id"] = "chg-1"
    corpus["items"][0]["pav_id"] = 1
    _rewrite(world["corpus"], corpus)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID
    assert any("пересекается" in e for e in outcome.blocking_errors)


# --- negative: sample/labels contract ---


def test_duplicate_sample_id_blocks(world):
    sample = _read(world["sample"])
    sample["rows"].append(dict(sample["rows"][0]))
    _rewrite(world["sample"], sample)
    labels = _read(world["labels"])
    labels["sample_hash"] = canonical_hash(sample)
    labels["labels"].append(dict(labels["labels"][0]))
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID
    assert any("дубли" in e for e in outcome.blocking_errors)


def test_conflicting_labels_block(world):
    labels = _read(world["labels"])
    twin = dict(labels["labels"][0])
    twin["decision"] = "incorrect"
    labels["labels"].append(twin)
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID
    assert any("дубли labels" in e for e in outcome.blocking_errors)


def test_missing_ground_truth_blocks(world):
    labels = _read(world["labels"])
    labels["labels"] = labels["labels"][:-1]
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID
    assert any("без label" in e for e in outcome.blocking_errors)


def test_unknown_decision_blocks(world):
    labels = _read(world["labels"])
    labels["labels"][0]["decision"] = "maybe"
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID


# --- declared fields vs recomputed ---


def test_declared_collision_count_mismatch_blocks(world):
    sample = _read(world["sample"])
    sample["collision_count"] = 1
    _rewrite(world["sample"], sample)
    labels = _read(world["labels"])
    labels["sample_hash"] = canonical_hash(sample)
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID
    assert any("collision_count" in e for e in outcome.blocking_errors)


def test_declared_collision_count_missing_warns(world):
    sample = _read(world["sample"])
    del sample["collision_count"]
    _rewrite(world["sample"], sample)
    labels = _read(world["labels"])
    labels["sample_hash"] = canonical_hash(sample)
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_PASSED
    assert any("collision_count" in w for w in outcome.warnings)


def test_declared_overlap_flag_false_warns(world):
    sample = _read(world["sample"])
    sample["corpus_overlap_checked"] = False
    _rewrite(world["sample"], sample)
    labels = _read(world["labels"])
    labels["sample_hash"] = canonical_hash(sample)
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_PASSED
    assert any("corpus_overlap_checked" in w for w in outcome.warnings)


def test_overlap_computed_not_trusted(world):
    """Declared corpus_overlap_checked=true не спасает реальное пересечение."""
    corpus = _read(world["corpus"])
    corpus["items"][0]["product_id"] = 5
    corpus["items"][0]["change_id"] = "chg-5"
    corpus["items"][0]["pav_id"] = 5
    _rewrite(world["corpus"], corpus)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_INVALID


# --- thresholds (exit 1: валидная оценка, thresholds не пройдены) ---


def test_precision_below_gate_fails_thresholds(world):
    labels = _read(world["labels"])
    for i in range(3):
        labels["labels"][i]["decision"] = "unverifiable"
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_THRESHOLD_FAILED
    assert outcome.gate_passed is False
    assert outcome.report["metrics"]["precision"] == pytest.approx(0.97)


def test_rows_below_minimum_fails_thresholds(world):
    sample = _read(world["sample"])
    sample["rows"] = sample["rows"][:99]
    _rewrite(world["sample"], sample)
    labels = _read(world["labels"])
    labels["labels"] = labels["labels"][:99]
    labels["sample_hash"] = canonical_hash(sample)
    _rewrite(world["labels"], labels)
    outcome = _gate(world)
    assert outcome.exit_code == EXIT_THRESHOLD_FAILED
    assert outcome.report["metrics"]["rows"] == 99


# --- frozen Phase 7D sample (versioned fixtures) ---


def _frozen_gate(**kw):
    kwargs = {
        "ruleset_path": REAL_RULESET,
        "corpus_path": REAL_CORPUS,
        "manifest_path": None,
        "sample_path": FROZEN_SAMPLE,
        "labels_path": FROZEN_LABELS,
    }
    kwargs.update(kw)
    return run_independent_gate(**kwargs)


def test_frozen_sample_blocks_without_legacy_flag():
    outcome = _frozen_gate()
    assert outcome.exit_code == EXIT_INVALID
    assert any("sample.taxonomy_hash" in e for e in outcome.blocking_errors)


def test_frozen_sample_passes_with_legacy_flag():
    outcome = _frozen_gate(allow_legacy_taxonomy_hash=LEGACY_TAXONOMY_HASH)
    assert outcome.exit_code == EXIT_PASSED, outcome.blocking_errors
    assert outcome.gate_passed is True
    metrics = outcome.report["metrics"]
    assert metrics["rows"] == 103
    assert metrics["correct"] == 102
    assert metrics["precision"] == 102 / 103
    lo, hi = metrics["wilson95"]
    assert lo == pytest.approx(0.947042, abs=1e-5)
    assert hi == pytest.approx(0.998284, abs=1e-5)
    assert outcome.report["replay"]["checked"] == 103
    assert outcome.report["replay"]["collisions_recomputed"] == 0
    mm = outcome.report["declared_mismatches"]
    assert any(m["severity"] == "legacy_recipe" for m in mm)


def test_frozen_sample_deterministic():
    a = _frozen_gate(allow_legacy_taxonomy_hash=LEGACY_TAXONOMY_HASH).report
    b = _frozen_gate(allow_legacy_taxonomy_hash=LEGACY_TAXONOMY_HASH).report
    a.pop("generated_at")
    b.pop("generated_at")
    assert a == b
