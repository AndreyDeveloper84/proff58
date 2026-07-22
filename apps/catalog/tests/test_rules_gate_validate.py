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
        # hotfix post-#579: официальный sample — overlap проверен, коллизий 0
        "corpus_overlap_checked": True,
        "collision_count": 0,
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


def test_malformed_labels_json_fails(tmp_path):
    sample_p = _write(tmp_path, "sample.json", _sample())
    labels_p = tmp_path / "labels.json"
    labels_p.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(CommandError, match="Невалидный JSON"):
        call_command(
            "catalog_rules_gate_validate",
            gate_sample=str(sample_p),
            labels=str(labels_p),
            stdout=StringIO(),
        )


def test_missing_labels_file_fails(tmp_path):
    sample_p = _write(tmp_path, "sample.json", _sample())
    with pytest.raises(CommandError, match="не найден"):
        call_command(
            "catalog_rules_gate_validate",
            gate_sample=str(sample_p),
            labels=str(tmp_path / "no-such-labels.json"),
            stdout=StringIO(),
        )


# --- hotfix post-#579: fail-closed sample contract ---


def _big_sample(n=100, **kw):
    """Sample, проходящий пороги precision/rows: изолирует sample-контракт
    как единственную причину отказа gate."""
    return _sample(product_ids=tuple(range(900100, 900100 + n)), **kw)


@pytest.mark.parametrize("marker", [False, "missing"])
def test_gate_fails_without_overlap_check(tmp_path, marker):
    """corpus_overlap_checked=false или поле отсутствует → gate НЕ пройден
    (fail-closed): violation в выводе, gate_passed=false, exit не 0."""
    sample = _big_sample()
    if marker == "missing":
        del sample["corpus_overlap_checked"]
    else:
        sample["corpus_overlap_checked"] = False
    sample_p = _write(tmp_path, "sample.json", sample)
    labels_p = _write(tmp_path, "labels.json", _labels(sample))
    buf = StringIO()
    with pytest.raises(CommandError, match="corpus_overlap_checked"):
        call_command(
            "catalog_rules_gate_validate",
            gate_sample=str(sample_p),
            labels=str(labels_p),
            stdout=buf,
        )
    out = buf.getvalue()
    assert "violation" in out
    assert "gate_passed=false" in out  # 100/100 correct не спасают unofficial sample


def test_gate_fails_when_collision_count_missing(tmp_path):
    """collision_count отсутствует → gate НЕ пройден (fail-closed)."""
    sample = _big_sample()
    del sample["collision_count"]
    sample_p = _write(tmp_path, "sample.json", sample)
    labels_p = _write(tmp_path, "labels.json", _labels(sample))
    buf = StringIO()
    with pytest.raises(CommandError, match="collision_count"):
        call_command(
            "catalog_rules_gate_validate",
            gate_sample=str(sample_p),
            labels=str(labels_p),
            stdout=buf,
        )
    assert "gate_passed=false" in buf.getvalue()


def test_gate_fails_when_collision_count_nonzero(tmp_path):
    """collision_count=1 → gate НЕ пройден, violation в выводе."""
    sample = _big_sample(collision_count=1)
    sample_p = _write(tmp_path, "sample.json", sample)
    labels_p = _write(tmp_path, "labels.json", _labels(sample))
    buf = StringIO()
    with pytest.raises(CommandError, match="collision_count"):
        call_command(
            "catalog_rules_gate_validate",
            gate_sample=str(sample_p),
            labels=str(labels_p),
            stdout=buf,
        )
    assert "gate_passed=false" in buf.getvalue()


def test_gate_fails_when_collision_count_bool(tmp_path):
    """collision_count=false (JSON bool) НЕ является валидным нулём: в Python
    False == 0, поэтому fail-closed контракт требует строгой type-проверки
    (review #580). bool отклоняется так же, как отсутствие поля."""
    sample = _big_sample(collision_count=False)
    sample_p = _write(tmp_path, "sample.json", sample)
    labels_p = _write(tmp_path, "labels.json", _labels(sample))
    buf = StringIO()
    with pytest.raises(CommandError, match="collision_count"):
        call_command(
            "catalog_rules_gate_validate",
            gate_sample=str(sample_p),
            labels=str(labels_p),
            stdout=buf,
        )
    assert "gate_passed=false" in buf.getvalue()


def test_gate_passes_with_clean_sample(tmp_path):
    """overlap checked + collision_count=0 + валидные labels (100 rows, все
    correct) → gate пройден."""
    sample = _big_sample()
    out = _run(tmp_path, sample, _labels(sample))
    assert "rows=100" in out
    assert "correct=100" in out
    assert "observed_precision=1.0" in out
    assert "gate_passed=true" in out
