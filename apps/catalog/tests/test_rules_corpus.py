import json

import pytest

from apps.catalog.processing import canonical_hash
from apps.catalog.rules_engine import (
    load_corpus,
    validate_gate_labels,
    validate_gate_sample,
)


def _item(product_id, **kw):
    facts = {
        "name": f"Шплинт 6,4х76 ({product_id})",
        "original_name": f"Шплинт оцинкованный {product_id}",
        "brand": "",
        "source_group": "Крепёж",
        "article": f"A{product_id}",
    }
    item = {
        "product_id": product_id,
        "change_id": f"ch-{product_id}",
        "pav_id": 1000 + product_id,
        "applied_option_slug": "krep-shplinty",
        "facts_hash": canonical_hash(facts),
        **facts,
    }
    item.update(kw)
    return item


def _corpus_dict(**over):
    data = {
        "version": 1,
        "corpus_id": "applied-tool-type.v1",
        "counters": {
            "raw_applied_changes": 3,
            "distinct_products": 2,
            "current_label_corpus": 2,
            "historical_label_collisions": 0,
        },
        "items": [_item(101), _item(102)],
    }
    data.update(over)
    return data


def _write_corpus(tmp_path, **over):
    p = tmp_path / "corpus.json"
    p.write_text(json.dumps(_corpus_dict(**over)), encoding="utf-8")
    return load_corpus(p)


def _sample(product_ids=(201, 202), **kw):
    sample = {
        "ruleset_hash": "r" * 64,
        "matcher_version": "1.0",
        "taxonomy_hash": "t" * 64,
        "seed": 42,
        "pool": "in-stock",
        "pool_filter_version": "v1",
        "rows": [
            {
                "product_id": pid,
                "facts_hash": "f" * 64,
                "predicted_option_slug": "krep-shplinty",
                "rule_refs": ["tt-a-001"],
            }
            for pid in product_ids
        ],
    }
    sample.update(kw)
    return sample


def _labels(sample, **kw):
    labels = {
        "sample_hash": canonical_hash(sample),
        "ruleset_hash": sample["ruleset_hash"],
        "matcher_version": sample["matcher_version"],
        "labels": [
            {
                "product_id": r["product_id"],
                "decision": "correct",
                "reviewer_id": "reviewer-1",
                "reviewed_at": "2026-07-21T00:00:00Z",
            }
            for r in sample["rows"]
        ],
    }
    labels.update(kw)
    return labels


# --- load_corpus ---


def test_load_corpus_valid(tmp_path):
    corpus = _write_corpus(tmp_path)
    assert corpus.corpus_id == "applied-tool-type.v1"
    assert len(corpus.items) == 2
    assert corpus.product_ids == frozenset({101, 102})
    # счётчики согласованы с items
    assert corpus.counters["current_label_corpus"] == len(corpus.items)
    assert corpus.counters["raw_applied_changes"] >= corpus.counters["distinct_products"]
    assert corpus.items[0].original_name


def test_corpus_duplicate_product_id_rejected(tmp_path):
    data = _corpus_dict()
    data["items"] = [data["items"][0], dict(data["items"][0])]
    p = tmp_path / "corpus.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Дубли product_id"):
        load_corpus(p)


def test_corpus_facts_hash_mismatch_rejected(tmp_path):
    data = _corpus_dict()
    data["items"][0]["facts_hash"] = "0" * 64
    p = tmp_path / "corpus.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="facts_hash"):
        load_corpus(p)


def test_corpus_counters_inconsistent_rejected(tmp_path):
    data = _corpus_dict()
    data["counters"]["distinct_products"] = 5  # > raw_applied_changes=3
    p = tmp_path / "corpus.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="counters"):
        load_corpus(p)


# --- validate_gate_sample ---


def test_validate_gate_sample_excludes_corpus(tmp_path):
    corpus = _write_corpus(tmp_path)
    violations = validate_gate_sample(_sample((101, 201)), corpus)
    assert any("corpus" in v for v in violations)
    # без пересечения с corpus violations нет
    assert validate_gate_sample(_sample((201, 202)), corpus) == []


def test_validate_gate_sample_unique_ids():
    violations = validate_gate_sample(_sample((201, 201)), None)
    assert any("дубли" in v for v in violations)


# --- validate_gate_labels ---


def test_validate_gate_labels_complete():
    sample = _sample((201, 202))
    assert validate_gate_labels(_labels(sample), sample) == []


def test_validate_gate_labels_missing_label():
    sample = _sample((201, 202))
    labels = _labels(sample)
    labels["labels"] = labels["labels"][:1]
    violations = validate_gate_labels(labels, sample)
    assert any("без label" in v for v in violations)


def test_wrong_sample_hash():
    sample = _sample((201, 202))
    labels = _labels(sample, sample_hash="0" * 64)
    violations = validate_gate_labels(labels, sample)
    assert any("sample_hash" in v for v in violations)


def test_unknown_decision():
    sample = _sample((201, 202))
    labels = _labels(sample)
    labels["labels"][0]["decision"] = "maybe"
    violations = validate_gate_labels(labels, sample)
    assert any("decision" in v for v in violations)
