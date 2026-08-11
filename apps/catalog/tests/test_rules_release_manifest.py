"""Тесты команды catalog_rules_release_manifest (Wave 7.1/H3): режимы
генерации и --check, exit codes, идемпотентность записи, детекция дрейфа."""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.processing import canonical_hash
from apps.catalog.rules_release import (
    DEFAULT_GATE_SAMPLE_PATH,
    DEFAULT_LABELS_PATH,
    RELEASE_MANIFEST_PATH,
    build_release_manifest,
    canonical_bytes,
    canonical_hash_of,
)

LEGACY_TAXONOMY_HASH = "b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b"


def _run(**kwargs):
    """H4: команда вызывается без поблажки — входы на canonical binding."""
    buf = StringIO()
    call_command("catalog_rules_release_manifest", stdout=buf, **kwargs)
    return buf.getvalue()


def _document():
    doc, _ = build_release_manifest()
    return doc


def _legacy_bound_inputs(tmp_path):
    """Копия default-входов с legacy taxonomy_hash (labels перепривязаны)."""
    sample = json.loads(DEFAULT_GATE_SAMPLE_PATH.read_text(encoding="utf-8"))
    sample["taxonomy_hash"] = LEGACY_TAXONOMY_HASH
    labels = json.loads(DEFAULT_LABELS_PATH.read_text(encoding="utf-8"))
    labels["sample_hash"] = canonical_hash(sample)
    sample_p = tmp_path / "sample.json"
    labels_p = tmp_path / "labels.json"
    sample_p.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    labels_p.write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    return {"gate_sample": str(sample_p), "labels": str(labels_p)}


# --- режим --check (контур CI) ---


def test_check_committed_manifest_passes():
    out = _run(check=True)
    assert "check=ok" in out
    assert "gate rows=103 correct=102" in out


def test_check_on_legacy_binding_fails_exit_2(tmp_path):
    """Артефакт с legacy taxonomy_hash без явного флага — exit 2 (blocking gate)."""
    with pytest.raises(CommandError) as exc_info:
        call_command(
            "catalog_rules_release_manifest",
            "--check",
            **_legacy_bound_inputs(tmp_path),
            stdout=StringIO(),
        )
    assert exc_info.value.returncode == 2
    assert "blocking gate errors" in str(exc_info.value)


def test_check_detects_drift_in_consistent_manifest(tmp_path):
    doc = _document()
    doc["canonical"]["inputs"]["ruleset"]["rules"] = 999
    doc["canonical_hash"] = canonical_hash_of(doc["canonical"])
    path = tmp_path / "release.json"
    path.write_bytes(canonical_bytes(doc))
    buf = StringIO()
    with pytest.raises(CommandError) as exc_info:
        call_command(
            "catalog_rules_release_manifest",
            "--check",
            manifest=str(path),
            stdout=buf,
        )
    assert exc_info.value.returncode == 2
    assert "не соответствует пересчитанному" in str(exc_info.value)
    assert "drift: canonical.inputs.ruleset.rules: зафиксировано=999" in buf.getvalue()


def test_check_detects_tampered_canonical_hash(tmp_path):
    doc = _document()
    doc["canonical"]["gate"]["metrics"]["precision"] = 1.0  # canonical_hash не пересчитан
    path = tmp_path / "release.json"
    path.write_bytes(canonical_bytes(doc))
    with pytest.raises(CommandError) as exc_info:
        _run(check=True, manifest=str(path))
    assert exc_info.value.returncode == 2
    assert "canonical_hash" in str(exc_info.value)


def test_check_missing_manifest_exit_2(tmp_path):
    with pytest.raises(CommandError) as exc_info:
        _run(check=True, manifest=str(tmp_path / "no-such.json"))
    assert exc_info.value.returncode == 2
    assert "не найден" in str(exc_info.value)


# --- режим генерации ---


def test_write_creates_byte_stable_file(tmp_path):
    path = tmp_path / "release.json"
    out = _run(manifest=str(path))
    assert f"written={path}" in out
    assert path.read_bytes() == RELEASE_MANIFEST_PATH.read_bytes()
    assert json.loads(path.read_text(encoding="utf-8"))["canonical_hash"]


def test_rewrite_is_idempotent_noop(tmp_path):
    path = tmp_path / "release.json"
    _run(manifest=str(path))
    before = path.read_bytes()
    out = _run(manifest=str(path))
    assert "unchanged=" in out
    assert path.read_bytes() == before


def test_differing_file_requires_force(tmp_path):
    path = tmp_path / "release.json"
    path.write_text('{"canonical": {}, "canonical_hash": "x"}', encoding="utf-8")
    with pytest.raises(CommandError) as exc_info:
        _run(manifest=str(path))
    assert exc_info.value.returncode == 2
    assert "--force" in str(exc_info.value)
    out = _run(manifest=str(path), force=True)
    assert f"written={path}" in out
    assert path.read_bytes() == RELEASE_MANIFEST_PATH.read_bytes()


def test_generated_at_only_in_stdout_never_in_file(tmp_path):
    path = tmp_path / "release.json"
    out = _run(manifest=str(path))
    assert "generated_at=" in out
    assert "generated_at" not in path.read_text(encoding="utf-8")


def test_format_json_prints_document(tmp_path):
    path = tmp_path / "release.json"
    out = _run(manifest=str(path), format="json")
    printed = json.loads(out[out.index("{") : out.rindex("}") + 1])
    assert printed == json.loads(path.read_text(encoding="utf-8"))


def test_tampered_ruleset_blocks_release(tmp_path):
    data = json.loads(
        (RELEASE_MANIFEST_PATH.parent / "tool_type.v2.json").read_text(encoding="utf-8")
    )
    data["rules"][0]["match"].setdefault("name_keywords_any", []).append("tampered-h3")
    tampered = tmp_path / "tool_type.v2.tampered.json"
    tampered.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CommandError) as exc_info:
        _run(manifest=str(tmp_path / "release.json"), ruleset=str(tampered))
    assert exc_info.value.returncode == 2
    assert "ruleset_hash" in str(exc_info.value)
    assert not (tmp_path / "release.json").exists()
