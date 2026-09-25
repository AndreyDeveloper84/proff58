"""Release manifest контура распознавания ``tool_type`` (Wave 7.1 / Stage H3).

Release manifest — единый детерминированный артефакт версии контура: он
связывает первичные входы (ruleset, applied corpus, canonical taxonomy
manifest), версии matcher/gate и метрики последнего **пройденного**
independent gate (H2) в один документ с собственным ``canonical_hash``.

Контракт документа::

    {"canonical": {...}, "canonical_hash": "<sha256 canonical>"}

- ``canonical`` — всё, что зависит только от входов; байт-стабилен;
- ``canonical_hash`` — sha256 канонической сериализации ``canonical``;
- ``generated_at`` в файл **не пишется**: время прогона — non-canonical
  метаданные, команда выводит его в stdout. Поэтому два прогона на
  неизменных входах дают побайтово идентичный файл.

Манифест выпускается только если gate пройден (``gate_passed=true``):
release-артефакт не фиксирует состояние, которое не прошло проверку.
Модуль ничего не пишет в БД и не применяет predictions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.conf import settings

from apps.catalog.rules_engine import RULESET_PATH, load_corpus, load_ruleset
from apps.catalog.rules_gate import (
    DEFAULT_CORPUS_PATH,
    GATE_VERSION,
    REPORT_SCHEMA_VERSION,
    GateOutcome,
    run_independent_gate,
)
from apps.catalog.taxonomy_manifest import load_manifest

RELEASE_MANIFEST_SCHEMA_VERSION = 1

RELEASE_MANIFEST_PATH = (
    Path(settings.BASE_DIR) / "data" / "catalog_processing_rules" / "rules_release_manifest.v1.json"
)

# Замороженный официальный gate-sample 7D — release evidence (H2 §5).
_FIXTURES = Path(settings.BASE_DIR) / "apps" / "catalog" / "tests" / "fixtures"
DEFAULT_GATE_SAMPLE_PATH = _FIXTURES / "phase7d-gate-sample-official.json"
DEFAULT_LABELS_PATH = _FIXTURES / "phase7d-labels.json"


class ReleaseManifestError(ValueError):
    """Некорректный/нечитаемый release manifest."""


def _repo_relative(path: Path | str) -> str:
    """POSIX-путь относительно BASE_DIR (портабельность Windows ↔ CI).

    Путь вне репозитория портабельным быть не может — записывается как есть
    (только ad-hoc прогоны с временными артефактами).
    """
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(settings.BASE_DIR).resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def canonical_bytes(value) -> bytes:
    """Каноническая сериализация — единственная точка правды по байтам."""
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def canonical_hash_of(canonical: dict) -> str:
    return hashlib.sha256(canonical_bytes(canonical)).hexdigest()


def _sha256_file(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_release_manifest(
    *,
    ruleset_path: Path | str | None = None,
    corpus_path: Path | str | None = None,
    manifest_path: Path | str | None = None,
    sample_path: Path | str | None = None,
    labels_path: Path | str | None = None,
    allow_legacy_taxonomy_hash: str | None = None,
) -> tuple[dict | None, GateOutcome]:
    """Пересчитать release manifest из первичных входов.

    Возвращает ``(document | None, GateOutcome)``. Документ ``None``, если
    gate не пройден: exit code берётся вызывающей стороной из ``outcome``.
    """
    ruleset_path = Path(ruleset_path) if ruleset_path else RULESET_PATH
    corpus_path = Path(corpus_path) if corpus_path else DEFAULT_CORPUS_PATH
    sample_path = Path(sample_path) if sample_path else DEFAULT_GATE_SAMPLE_PATH
    labels_path = Path(labels_path) if labels_path else DEFAULT_LABELS_PATH

    outcome = run_independent_gate(
        ruleset_path=ruleset_path,
        corpus_path=corpus_path,
        manifest_path=manifest_path,
        sample_path=sample_path,
        labels_path=labels_path,
        allow_legacy_taxonomy_hash=allow_legacy_taxonomy_hash,
    )
    if not outcome.gate_passed:
        return None, outcome

    # gate пройден ⇒ входы валидны; повторная загрузка даёт метаданные версии
    ruleset = load_ruleset(ruleset_path)
    corpus = load_corpus(corpus_path)
    manifest = load_manifest(Path(manifest_path) if manifest_path else None)
    report = outcome.report
    sha = report["hashes"]["artifact_sha256"]

    canonical = {
        "schema_version": RELEASE_MANIFEST_SCHEMA_VERSION,
        "gate_version": GATE_VERSION,
        "matcher_version": ruleset.matcher_version,
        "inputs": {
            "ruleset": {
                "path": _repo_relative(ruleset_path),
                "ruleset_id": ruleset.ruleset_id,
                "version": ruleset.version,
                "rules": len(ruleset.rules),
                "ruleset_hash": ruleset.ruleset_hash,
                "artifact_sha256": sha["ruleset"],
            },
            "corpus": {
                "path": _repo_relative(corpus_path),
                "corpus_id": corpus.corpus_id,
                "items": len(corpus.items),
                "artifact_sha256": sha["corpus"],
            },
            "taxonomy_manifest": {
                "path": _repo_relative(manifest.path),
                "manifest_version": manifest.manifest_version,
                "options": len(manifest.options),
                "taxonomy_identity_hash": manifest.identity_hash,
                "manifest_semantic_hash": manifest.semantic_hash,
                "artifact_sha256": _sha256_file(manifest.path),
            },
            "gate_sample": {
                "path": _repo_relative(sample_path),
                "rows": report["validations"]["sample"]["rows"],
                "artifact_sha256": sha["gate_sample"],
            },
            "labels": {
                "path": _repo_relative(labels_path),
                "labels": report["validations"]["labels"]["labels"],
                "artifact_sha256": sha["labels"],
            },
        },
        "gate": {
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "gate_passed": True,
            "legacy_taxonomy_hash_allowed": allow_legacy_taxonomy_hash,
            "metrics": report["metrics"],
            "thresholds": report["thresholds"],
            "declared_mismatches": report["declared_mismatches"],
            "warnings": report["warnings"],
        },
    }
    return {"canonical": canonical, "canonical_hash": canonical_hash_of(canonical)}, outcome


def load_release_manifest(path: Path | str) -> dict:
    """Прочитать зафиксированный manifest с проверкой самосогласованности."""
    path = Path(path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReleaseManifestError(f"release manifest не найден: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReleaseManifestError(f"release manifest не валидный JSON ({path}): {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("canonical"), dict):
        raise ReleaseManifestError(f"release manifest без секции canonical: {path}")
    recorded_hash = doc.get("canonical_hash")
    actual_hash = canonical_hash_of(doc["canonical"])
    if recorded_hash != actual_hash:
        raise ReleaseManifestError(
            "canonical_hash не соответствует содержимому canonical: "
            f"записан {recorded_hash!r}, пересчитан {actual_hash!r}"
        )
    return doc


def diff_canonical(recorded, recomputed, prefix: str = "canonical") -> list[str]:
    """Плоский структурный дифф canonical-секций (стабильный порядок ключей)."""
    diffs: list[str] = []
    if isinstance(recorded, dict) and isinstance(recomputed, dict):
        for key in sorted(set(recorded) | set(recomputed)):
            path = f"{prefix}.{key}"
            if key not in recorded:
                diffs.append(f"{path}: нет в зафиксированном, пересчитано={recomputed[key]!r}")
            elif key not in recomputed:
                diffs.append(f"{path}: зафиксировано={recorded[key]!r}, нет в пересчитанном")
            else:
                diffs.extend(diff_canonical(recorded[key], recomputed[key], path))
        return diffs
    if recorded != recomputed:
        diffs.append(f"{prefix}: зафиксировано={recorded!r}, пересчитано={recomputed!r}")
    return diffs
