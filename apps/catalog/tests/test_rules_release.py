"""Тесты release manifest контура tool_type (Wave 7.1/H3): детерминизм,
canonical-контракт, самосогласованность и fail-closed на непройденном gate."""

import json
from pathlib import Path

import pytest
from django.conf import settings

from apps.catalog.processing import canonical_hash
from apps.catalog.rules_release import (
    DEFAULT_GATE_SAMPLE_PATH,
    DEFAULT_LABELS_PATH,
    RELEASE_MANIFEST_PATH,
    ReleaseManifestError,
    build_release_manifest,
    canonical_bytes,
    canonical_hash_of,
    diff_canonical,
    load_release_manifest,
)

LEGACY_TAXONOMY_HASH = "b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b"
CANONICAL_TAXONOMY_HASH = "ddf4b949b38265b1fde3f7e2caa0cf5bb4fe4e82fd23980676ac93c8bf844874"
RULESET_SRC = Path(settings.BASE_DIR) / "data" / "catalog_processing_rules" / "tool_type.v2.json"


def _build(**kwargs):
    """H4: входы по умолчанию — canonical binding, поблажка не передаётся."""
    return build_release_manifest(**kwargs)


def _iter_keys(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_keys(item)


# --- контракт документа ---


def test_build_returns_self_consistent_document():
    doc, outcome = _build()
    assert outcome.gate_passed is True
    assert set(doc) == {"canonical", "canonical_hash"}
    assert doc["canonical_hash"] == canonical_hash_of(doc["canonical"])
    assert doc["canonical"]["schema_version"] == 1
    assert doc["canonical"]["gate_version"] == "2.0"
    assert doc["canonical"]["matcher_version"] == "1.0"


def test_canonical_has_no_timestamp_fields():
    doc, _ = _build()
    keys = set(_iter_keys(doc))
    assert "generated_at" not in keys
    assert not {k for k in keys if "timestamp" in k or k.endswith("_at")}


def test_two_builds_are_byte_identical():
    first, _ = _build()
    second, _ = _build()
    assert canonical_bytes(first) == canonical_bytes(second)
    assert first["canonical_hash"] == second["canonical_hash"]


def test_paths_are_repo_relative_posix():
    doc, _ = _build()
    for name, block in doc["canonical"]["inputs"].items():
        path = block["path"]
        assert "\\" not in path, name
        assert not path.startswith("/") and ":" not in path, name
        assert (Path(settings.BASE_DIR) / path).exists(), name


def test_inputs_bind_all_primary_hashes():
    doc, outcome = _build()
    inputs = doc["canonical"]["inputs"]
    report = outcome.report
    assert inputs["ruleset"]["ruleset_hash"] == report["hashes"]["ruleset_hash"]
    tax = inputs["taxonomy_manifest"]
    assert tax["taxonomy_identity_hash"] == CANONICAL_TAXONOMY_HASH
    assert tax["manifest_semantic_hash"] == report["hashes"]["manifest_semantic_hash"]
    assert tax["options"] == 360
    for key in ("ruleset", "corpus", "gate_sample", "labels", "taxonomy_manifest"):
        digest = inputs[key]["artifact_sha256"]
        assert isinstance(digest, str) and len(digest) == 64


def test_gate_metrics_are_recorded_unrounded():
    doc, outcome = _build()
    gate = doc["canonical"]["gate"]
    assert gate["gate_passed"] is True
    assert gate["metrics"] == outcome.report["metrics"]
    assert gate["metrics"]["rows"] == 103
    assert gate["metrics"]["correct"] == 102
    assert gate["metrics"]["precision"] == 102 / 103
    assert gate["thresholds"] == {"precision_gate": 0.99, "min_rows_gate": 100}
    assert gate["legacy_taxonomy_hash_allowed"] is None
    assert gate["declared_mismatches"] == []


def test_primary_inputs_are_lf_pinned():
    """artifact_sha256 — sha256 сырых байтов; CRLF ломает его портабельность
    Windows ↔ CI (см. .gitattributes: ``-text`` на этих артефактах)."""
    doc, _ = _build()
    for name, block in doc["canonical"]["inputs"].items():
        data = (Path(settings.BASE_DIR) / block["path"]).read_bytes()
        assert b"\r\n" not in data, name


def test_committed_manifest_matches_recomputed():
    """Зафиксированный в репозитории manifest = текущее состояние контура."""
    doc, _ = _build()
    recorded = load_release_manifest(RELEASE_MANIFEST_PATH)
    assert diff_canonical(recorded["canonical"], doc["canonical"]) == []
    assert RELEASE_MANIFEST_PATH.read_bytes() == canonical_bytes(doc)


# --- fail-closed: manifest не выпускается поверх непройденного gate ---


def test_no_manifest_on_legacy_taxonomy_binding(tmp_path):
    """Artifact с legacy taxonomy_hash без явного флага — manifest не выпускается."""
    sample = json.loads(DEFAULT_GATE_SAMPLE_PATH.read_text(encoding="utf-8"))
    sample["taxonomy_hash"] = LEGACY_TAXONOMY_HASH
    labels = json.loads(DEFAULT_LABELS_PATH.read_text(encoding="utf-8"))
    labels["sample_hash"] = canonical_hash(sample)
    sample_p = tmp_path / "sample.json"
    labels_p = tmp_path / "labels.json"
    sample_p.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    labels_p.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    doc, outcome = build_release_manifest(sample_path=sample_p, labels_path=labels_p)
    assert doc is None
    assert outcome.exit_code == 2
    assert any("taxonomy_hash" in e for e in outcome.blocking_errors)


def test_no_manifest_on_tampered_ruleset(tmp_path):
    data = json.loads(RULESET_SRC.read_text(encoding="utf-8"))
    data["rules"][0]["match"].setdefault("name_keywords_any", []).append("tampered-h3")
    tampered = tmp_path / "tool_type.v2.tampered.json"
    tampered.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    doc, outcome = _build(ruleset_path=tampered)
    assert doc is None
    assert outcome.exit_code == 2
    assert any("ruleset_hash" in e for e in outcome.blocking_errors)


def test_no_manifest_on_threshold_failure(tmp_path):
    sample = json.loads(DEFAULT_GATE_SAMPLE_PATH.read_text(encoding="utf-8"))
    labels = json.loads(DEFAULT_LABELS_PATH.read_text(encoding="utf-8"))
    keep = {r["product_id"] for r in sample["rows"][:99]}
    sample["rows"] = sample["rows"][:99]
    labels["labels"] = [lb for lb in labels["labels"] if lb["product_id"] in keep]
    labels["sample_hash"] = canonical_hash(sample)
    sample_p = tmp_path / "sample.json"
    labels_p = tmp_path / "labels.json"
    sample_p.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    labels_p.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    doc, outcome = _build(sample_path=sample_p, labels_path=labels_p)
    assert doc is None
    assert outcome.exit_code == 1


# --- чтение зафиксированного manifest ---


def test_load_rejects_broken_canonical_hash(tmp_path):
    doc, _ = _build()
    doc["canonical"]["inputs"]["ruleset"]["ruleset_hash"] = "0" * 64
    path = tmp_path / "release.json"
    path.write_bytes(canonical_bytes(doc))
    with pytest.raises(ReleaseManifestError, match="canonical_hash"):
        load_release_manifest(path)


def test_load_rejects_missing_file(tmp_path):
    with pytest.raises(ReleaseManifestError, match="не найден"):
        load_release_manifest(tmp_path / "no-such.json")


def test_load_rejects_malformed_json(tmp_path):
    path = tmp_path / "release.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ReleaseManifestError, match="не валидный JSON"):
        load_release_manifest(path)


def test_load_rejects_document_without_canonical(tmp_path):
    path = tmp_path / "release.json"
    path.write_text(json.dumps({"canonical_hash": "x"}), encoding="utf-8")
    with pytest.raises(ReleaseManifestError, match="без секции canonical"):
        load_release_manifest(path)


# --- diff ---


def test_diff_canonical_empty_for_equal():
    doc, _ = _build()
    assert diff_canonical(doc["canonical"], json.loads(json.dumps(doc["canonical"]))) == []


def test_diff_canonical_reports_nested_changes_and_missing_keys():
    recorded = {"a": {"b": 1, "only_recorded": True}, "c": [1, 2]}
    recomputed = {"a": {"b": 2, "only_recomputed": 5}, "c": [1, 3]}
    diffs = diff_canonical(recorded, recomputed)
    assert diffs == [
        "canonical.a.b: зафиксировано=1, пересчитано=2",
        "canonical.a.only_recomputed: нет в зафиксированном, пересчитано=5",
        "canonical.a.only_recorded: зафиксировано=True, нет в пересчитанном",
        "canonical.c: зафиксировано=[1, 2], пересчитано=[1, 3]",
    ]
