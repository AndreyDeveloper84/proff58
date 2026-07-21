import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.processing import canonical_hash


def _sample(product_ids=(201, 202), **kw):
    sample = {
        "ruleset_hash": "r" * 64,
        "matcher_version": "1.0",
        "taxonomy_hash": "t" * 64,
        "seed": 42,
        "pool": "in-stock",
        "pool_filter_version": "1.0",
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


def _labels(sample, decisions=None, **kw):
    labels = {
        "sample_hash": canonical_hash(sample),
        "ruleset_hash": sample["ruleset_hash"],
        "matcher_version": sample["matcher_version"],
        "labels": [
            {
                "product_id": row["product_id"],
                "decision": decisions[i] if decisions else "correct",
                "reviewer_id": "reviewer-1",
                "reviewed_at": "2026-07-21T00:00:00Z",
            }
            for i, row in enumerate(sample["rows"])
        ],
    }
    labels.update(kw)
    return labels


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _run(tmp_path, sample, labels):
    sample_p = _write(tmp_path, "sample.json", sample)
    labels_p = _write(tmp_path, "labels.json", labels)
    buf = StringIO()
    call_command(
        "catalog_rules_gate_validate",
        gate_sample=str(sample_p),
        labels=str(labels_p),
        stdout=buf,
    )
    return buf.getvalue()


def test_valid_labels_pass(tmp_path):
    sample = _sample()
    out = _run(tmp_path, sample, _labels(sample))
    # выход 0 + сводка decisions
    assert "rows=2" in out
    assert "correct=2" in out
    assert "incorrect=0" in out
    assert "observed_precision=1.0" in out
    assert "gate_passed=false" in out  # rows < 100


def test_missing_label_fails(tmp_path):
    sample = _sample()
    labels = _labels(sample)
    labels["labels"] = labels["labels"][:1]
    with pytest.raises(CommandError, match="без label"):
        _run(tmp_path, sample, labels)


def test_unknown_decision_fails(tmp_path):
    sample = _sample()
    labels = _labels(sample, decisions=["maybe", "correct"])
    with pytest.raises(CommandError, match="decision"):
        _run(tmp_path, sample, labels)


def test_wrong_sample_hash_fails(tmp_path):
    sample = _sample()
    labels = _labels(sample, sample_hash="0" * 64)
    with pytest.raises(CommandError, match="sample_hash"):
        _run(tmp_path, sample, labels)
