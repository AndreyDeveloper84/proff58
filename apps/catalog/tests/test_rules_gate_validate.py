"""Тесты команды catalog_rules_gate_validate (Wave 7.1/H2): CLI-контракт,
exit codes (0/1/2/3), machine report, backward-compatible вывод."""

import json
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.processing import canonical_hash

TESTS_WORKFLOW = Path(settings.BASE_DIR) / ".github" / "workflows" / "tests.yml"
FIXTURES = Path(__file__).parent / "fixtures"
FROZEN_SAMPLE = FIXTURES / "phase7d-gate-sample-official.json"
FROZEN_LABELS = FIXTURES / "phase7d-labels.json"
LEGACY_TAXONOMY_HASH = "b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b"


def _run(gate_sample, labels, **kwargs):
    buf = StringIO()
    call_command(
        "catalog_rules_gate_validate",
        gate_sample=str(gate_sample),
        labels=str(labels),
        stdout=buf,
        **kwargs,
    )
    return buf.getvalue()


def _frozen():
    """H4: замороженный sample несёт canonical taxonomy binding — без поблажки."""
    return {"gate_sample": FROZEN_SAMPLE, "labels": FROZEN_LABELS}


def test_frozen_sample_passes_without_legacy_flag():
    out = _run(**_frozen())
    assert "rows=103" in out
    assert "correct=102" in out
    assert "unverifiable=1" in out
    assert "observed_precision=0.9903" in out
    assert "wilson95=[0.9470" in out
    assert "collisions_recomputed=0" in out
    assert "gate_passed=true" in out


def test_ci_job_carries_no_legacy_taxonomy_poblazhka():
    """Guard (H4): возврат поблажки в CI обязан падать тестом, а не проходить ревью.

    Пока `--allow-legacy-taxonomy-hash` стоит в джобе, зелёный CI не является
    полным доказательством контура — ровно тот дефект доверия, ради которого
    затевалась Wave 7.1. Проверяется исполняемая часть workflow (env и run),
    комментарии намеренно игнорируются.
    """
    yaml = pytest.importorskip("yaml")
    workflow = yaml.safe_load(TESTS_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["catalog-rules-gate"]
    assert not [k for k in job.get("env", {}) if "LEGACY" in k.upper()]
    for step in job["steps"]:
        assert "allow-legacy-taxonomy-hash" not in step.get("run", ""), step.get("name")
        assert not [k for k in step.get("env", {}) if "LEGACY" in k.upper()], step.get("name")


def test_legacy_taxonomy_binding_blocks_exit_2(tmp_path):
    """Негативная матрица: артефакт с legacy taxonomy_hash без флага — exit 2."""
    sample = json.loads(FROZEN_SAMPLE.read_text(encoding="utf-8"))
    sample["taxonomy_hash"] = LEGACY_TAXONOMY_HASH
    labels = json.loads(FROZEN_LABELS.read_text(encoding="utf-8"))
    labels["sample_hash"] = canonical_hash(sample)
    sample_p = tmp_path / "sample.json"
    labels_p = tmp_path / "labels.json"
    sample_p.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    labels_p.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CommandError) as exc_info:
        _run(gate_sample=sample_p, labels=labels_p)
    assert exc_info.value.returncode == 2
    assert "taxonomy_hash" in str(exc_info.value)


def test_thresholds_failed_exit_1(tmp_path):
    sample = json.loads(FROZEN_SAMPLE.read_text(encoding="utf-8"))
    labels = json.loads(FROZEN_LABELS.read_text(encoding="utf-8"))
    keep = {r["product_id"] for r in sample["rows"][:99]}
    sample["rows"] = sample["rows"][:99]
    labels["labels"] = [lb for lb in labels["labels"] if lb["product_id"] in keep]
    labels["sample_hash"] = canonical_hash(sample)
    sample_p = tmp_path / "sample.json"
    labels_p = tmp_path / "labels.json"
    sample_p.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    labels_p.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CommandError) as exc_info:
        _run(gate_sample=sample_p, labels=labels_p)
    assert exc_info.value.returncode == 1
    assert "thresholds" in str(exc_info.value)


def test_malformed_labels_json_exit_2(tmp_path):
    labels_p = tmp_path / "labels.json"
    labels_p.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(CommandError) as exc_info:
        _run(gate_sample=FROZEN_SAMPLE, labels=labels_p)
    assert exc_info.value.returncode == 2
    assert "Невалидный JSON" in str(exc_info.value)


def test_missing_labels_file_exit_2(tmp_path):
    with pytest.raises(CommandError) as exc_info:
        _run(gate_sample=FROZEN_SAMPLE, labels=tmp_path / "no-such.json")
    assert exc_info.value.returncode == 2
    assert "не найден" in str(exc_info.value)


def test_tampered_rule_refs_exit_2(tmp_path):
    sample = json.loads(FROZEN_SAMPLE.read_text(encoding="utf-8"))
    labels = json.loads(FROZEN_LABELS.read_text(encoding="utf-8"))
    sample["rows"][0]["rule_refs"] = ["tt-ne-sushchestvuet"]
    labels["sample_hash"] = canonical_hash(sample)
    sample_p = tmp_path / "sample.json"
    labels_p = tmp_path / "labels.json"
    sample_p.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    labels_p.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CommandError) as exc_info:
        _run(gate_sample=sample_p, labels=labels_p)
    assert exc_info.value.returncode == 2
    assert "rule_refs" in str(exc_info.value)


def test_out_machine_report_atomic(tmp_path):
    out_p = tmp_path / "report.json"
    _run(**_frozen(), out=out_p)
    report = json.loads(out_p.read_text(encoding="utf-8"))
    assert report["gate_passed"] is True
    assert report["schema_version"] == 1
    assert report["gate_version"] == "2.0"
    assert report["metrics"]["precision"] == 102 / 103
    assert report["blocking_errors"] == []
    # перезапись без --force запрещена
    with pytest.raises(CommandError, match="--force"):
        _run(**_frozen(), out=out_p)
    # с --force — перезаписывается
    _run(**_frozen(), out=out_p, force=True)


def test_format_json_prints_machine_report():
    buf = StringIO()
    call_command(
        "catalog_rules_gate_validate",
        gate_sample=str(FROZEN_SAMPLE),
        labels=str(FROZEN_LABELS),
        format="json",
        stdout=buf,
    )
    report = json.loads(buf.getvalue())
    assert report["gate_passed"] is True
    assert report["metrics"]["rows"] == 103
    assert report["hashes"]["taxonomy_identity_hash"]
    assert report["overlap"]["computed_empty"] is True


def test_missing_gate_sample_file_exit_2(tmp_path):
    with pytest.raises(CommandError) as exc_info:
        _run(gate_sample=tmp_path / "no-sample.json", labels=FROZEN_LABELS)
    assert exc_info.value.returncode == 2
