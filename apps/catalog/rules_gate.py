"""Independent machine gate (Wave 7.1 / Stage H2).

Gate НЕ доверяет производным полям sample/labels/report: predictions,
rule_refs, facts_hash, overlap, collision_count, taxonomy/ruleset hashes и
метрики независимо пересчитываются из первичных versioned inputs —
ruleset, applied corpus и canonical taxonomy manifest (H1). Declared-поля
артефактов — только объект сравнения (structured mismatches), никогда не
source of truth.

Pipeline: manifest → ruleset (+taxonomy/fixtures) → corpus → sample/labels
(schema, uniqueness, coverage) → hash binding → matcher replay по каждой
строке sample (facts_hash, slug, rule_refs, collisions) → overlap (вычисляемый)
→ metrics (decisions, precision, Wilson 95%) → declared-поля как comparison
→ gate policy → machine report.

Exit codes: 0 — gate passed; 1 — валидно оценён, thresholds не пройдены;
2 — invalid inputs/schema/hash/provenance/blocking; 3 — internal error.
Команда не пишет в БД и не применяет predictions.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.catalog.processing import canonical_hash
from apps.catalog.rules_engine import (
    ProductFacts,
    check_negative_fixtures,
    evaluate_product,
    load_corpus,
    load_ruleset,
    validate_against_taxonomy,
    validate_gate_labels,
    validate_gate_sample,
)
from apps.catalog.taxonomy_manifest import load_manifest

DEFAULT_CORPUS_PATH = (
    Path(settings.BASE_DIR)
    / "data"
    / "catalog_processing_rules"
    / "applied_corpus_tool_type.v1.json"
)

GATE_VERSION = "2.0"
REPORT_SCHEMA_VERSION = 1
PRECISION_GATE = 0.99
MIN_ROWS_GATE = 100
WILSON_Z = 1.96

EXIT_PASSED = 0
EXIT_THRESHOLD_FAILED = 1
EXIT_INVALID = 2
EXIT_INTERNAL = 3

_FACT_KEYS = ("name", "original_name", "brand", "source_group", "article")

# severities declared-mismatch: blocking — отказ gate; warning — фиксируется;
# legacy_recipe — ожидаемое расхождение legacy-артефакта, допущенное явным флагом.
SEVERITY_BLOCKING = "blocking"
SEVERITY_WARNING = "warning"
SEVERITY_LEGACY = "legacy_recipe"


@dataclass(frozen=True)
class GateMismatch:
    field_path: str
    declared_value: object
    recomputed_value: object
    severity: str


@dataclass(frozen=True)
class GateOutcome:
    gate_passed: bool
    exit_code: int
    report: dict
    blocking_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    mismatches: tuple[GateMismatch, ...] = ()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json(path: Path, kind: str) -> dict:
    try:
        with Path(path).open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise ValueError(f"Файл не найден ({kind}): {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Невалидный JSON ({kind}): {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"Файл не UTF-8 ({kind}): {exc}") from exc


def wilson_interval(correct: int, n: int, z: float = WILSON_Z) -> tuple[float, float]:
    """Wilson score interval для доли (независимый пересчёт метрик gate)."""
    if n == 0:
        return (0.0, 0.0)
    p = correct / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom))


class _GateBuilder:
    def __init__(self) -> None:
        self.blocking: list[str] = []
        self.warnings: list[str] = []
        self.mismatches: list[GateMismatch] = []

    def mismatch(self, field_path: str, declared, recomputed, severity: str) -> None:
        self.mismatches.append(GateMismatch(field_path, declared, recomputed, severity))
        if severity == SEVERITY_BLOCKING:
            self.blocking.append(
                f"declared mismatch {field_path}: declared={declared!r} != recomputed={recomputed!r}"
            )
        elif severity == SEVERITY_WARNING:
            self.warnings.append(
                f"declared mismatch {field_path}: declared={declared!r} != recomputed={recomputed!r}"
            )


def run_independent_gate(
    *,
    ruleset_path: Path | None,
    corpus_path: Path | None,
    manifest_path: Path | None,
    sample_path: Path,
    labels_path: Path,
    allow_legacy_taxonomy_hash: str | None = None,
) -> GateOutcome:
    """Независимый пересчёт machine gate. Возвращает GateOutcome (report + exit code)."""
    b = _GateBuilder()
    sample_path = Path(sample_path)
    labels_path = Path(labels_path)

    # --- primary inputs ---
    try:
        manifest = load_manifest(manifest_path)
    except (ValueError, FileNotFoundError) as exc:
        b.blocking.append(f"taxonomy manifest: {exc}")
        manifest = None
    try:
        ruleset = load_ruleset(ruleset_path)
    except ValueError as exc:
        b.blocking.append(f"ruleset: {exc}")
        ruleset = None
    try:
        corpus = load_corpus(corpus_path) if corpus_path else None
    except ValueError as exc:
        b.blocking.append(f"corpus: {exc}")
        corpus = None
    try:
        sample = _load_json(sample_path, "gate_sample")
    except ValueError as exc:
        b.blocking.append(str(exc))
        sample = None
    try:
        labels = _load_json(labels_path, "labels")
    except ValueError as exc:
        b.blocking.append(str(exc))
        labels = None

    validations: dict = {}
    replay_summary: dict = {"rows": 0, "checked": 0, "collisions_recomputed": 0}

    if manifest is not None and ruleset is not None:
        unknown_rules = validate_against_taxonomy(ruleset, manifest.slugs)
        if unknown_rules:
            b.blocking.append(f"ruleset slugs вне canonical manifest: {unknown_rules}")
        fixture_violations = check_negative_fixtures(ruleset)
        if fixture_violations:
            b.blocking.append(f"negative fixtures: {fixture_violations}")
        validations["ruleset"] = {
            "ruleset_id": ruleset.ruleset_id,
            "rules": len(ruleset.rules),
            "unknown_slugs": unknown_rules,
            "negative_fixtures_violations": fixture_violations,
        }

    if corpus is not None and manifest is not None:
        corpus_unknown = sorted({i.applied_option_slug for i in corpus.items} - manifest.slugs)
        if corpus_unknown:
            b.blocking.append(f"corpus slugs вне canonical manifest: {corpus_unknown}")
        validations["corpus"] = {
            "corpus_id": corpus.corpus_id,
            "items": len(corpus.items),
            "unknown_slugs": corpus_unknown,
        }

    if sample is not None:
        sample_violations = validate_gate_sample(sample, corpus)
        for v in sample_violations:
            b.blocking.append(f"sample: {v}")
        validations["sample"] = {
            "rows": len(sample.get("rows", [])),
            "violations": sample_violations,
        }

    if sample is not None and labels is not None:
        label_violations = validate_gate_labels(labels, sample)
        for v in label_violations:
            b.blocking.append(f"labels: {v}")
        decisions = Counter(lb.get("decision") for lb in labels.get("labels", []))
        validations["labels"] = {
            "labels": len(labels.get("labels", [])),
            "decisions": dict(decisions),
        }
    else:
        decisions = Counter()

    # --- hash binding (declared vs recomputed) ---
    if ruleset is not None and sample is not None:
        if sample.get("ruleset_hash") != ruleset.ruleset_hash:
            b.mismatch(
                "sample.ruleset_hash",
                sample.get("ruleset_hash"),
                ruleset.ruleset_hash,
                SEVERITY_BLOCKING,
            )
        if sample.get("matcher_version") != ruleset.matcher_version:
            b.mismatch(
                "sample.matcher_version",
                sample.get("matcher_version"),
                ruleset.matcher_version,
                SEVERITY_BLOCKING,
            )
    if ruleset is not None and labels is not None:
        if labels.get("ruleset_hash") != ruleset.ruleset_hash:
            b.mismatch(
                "labels.ruleset_hash",
                labels.get("ruleset_hash"),
                ruleset.ruleset_hash,
                SEVERITY_BLOCKING,
            )
    if manifest is not None and sample is not None:
        declared_tax = sample.get("taxonomy_hash")
        if declared_tax != manifest.identity_hash:
            if allow_legacy_taxonomy_hash and declared_tax == allow_legacy_taxonomy_hash:
                b.mismatch(
                    "sample.taxonomy_hash",
                    declared_tax,
                    manifest.identity_hash,
                    SEVERITY_LEGACY,
                )
            else:
                b.mismatch(
                    "sample.taxonomy_hash",
                    declared_tax,
                    manifest.identity_hash,
                    SEVERITY_BLOCKING,
                )

    # --- matcher replay (независимые predictions/provenance/collisions) ---
    collisions_recomputed = 0
    if ruleset is not None and manifest is not None and sample is not None:
        ruleset_refs = {r.rule_ref for r in ruleset.rules}
        for row in sample.get("rows", []):
            pid = row.get("product_id")
            facts = {k: row.get(k, "") for k in _FACT_KEYS}
            if canonical_hash(facts) != row.get("facts_hash"):
                b.blocking.append(f"row {pid}: facts_hash не совпадает с пересчитанным")
                continue
            verdict = evaluate_product(ruleset.rules, ProductFacts(product_id=pid, **facts))
            replay_summary["checked"] += 1
            if verdict.status == "collision":
                collisions_recomputed += 1
                b.blocking.append(
                    f"row {pid}: declared prediction, recomputed collision {verdict.slugs}"
                )
                continue
            if verdict.status != "prediction":
                b.blocking.append(
                    f"row {pid}: recomputed status={verdict.status}, ожидался prediction"
                )
                continue
            if verdict.option_slug != row.get("predicted_option_slug"):
                b.mismatch(
                    f"rows[{pid}].predicted_option_slug",
                    row.get("predicted_option_slug"),
                    verdict.option_slug,
                    SEVERITY_BLOCKING,
                )
            recomputed_refs = tuple(sorted(verdict.rule_refs))
            declared_refs = tuple(sorted(row.get("rule_refs", [])))
            if declared_refs != recomputed_refs:
                b.mismatch(
                    f"rows[{pid}].rule_refs",
                    list(declared_refs),
                    list(recomputed_refs),
                    SEVERITY_BLOCKING,
                )
            if not set(declared_refs) <= ruleset_refs:
                b.blocking.append(
                    f"row {pid}: rule_refs вне ruleset: {sorted(set(declared_refs) - ruleset_refs)}"
                )
            if verdict.option_slug not in manifest.slugs:
                b.blocking.append(
                    f"row {pid}: predicted slug {verdict.option_slug!r} вне canonical manifest"
                )
        replay_summary["rows"] = len(sample.get("rows", []))
        replay_summary["collisions_recomputed"] = collisions_recomputed
        declared_coll = sample.get("collision_count")
        if declared_coll is None:
            b.warnings.append(
                "sample.collision_count отсутствует — используется пересчитанное значение"
            )
        elif declared_coll != collisions_recomputed:
            b.mismatch(
                "sample.collision_count",
                declared_coll,
                collisions_recomputed,
                SEVERITY_BLOCKING,
            )

    # --- overlap (вычисляемый, не доверенный) ---
    overlap: list[int] = []
    if sample is not None and corpus is not None:
        overlap = sorted({r.get("product_id") for r in sample.get("rows", [])} & corpus.product_ids)
        if overlap:
            b.blocking.append(f"sample пересекается с training corpus: {overlap[:10]}")
        if sample.get("corpus_overlap_checked") is not True:
            b.warnings.append(
                "sample.corpus_overlap_checked не true — поле игнорируется, overlap пересчитан"
            )

    # --- metrics (независимый пересчёт) ---
    rows_n = len(sample.get("rows", [])) if sample is not None else 0
    correct = decisions.get("correct", 0)
    precision = correct / rows_n if rows_n else 0.0
    wilson_lo, wilson_hi = wilson_interval(correct, rows_n)
    metrics = {
        "rows": rows_n,
        "correct": correct,
        "decisions": dict(decisions),
        "precision": precision,
        "wilson95": [wilson_lo, wilson_hi],
    }
    thresholds = {"precision_gate": PRECISION_GATE, "min_rows_gate": MIN_ROWS_GATE}

    # --- gate policy ---
    gate_passed = not b.blocking and precision >= PRECISION_GATE and rows_n >= MIN_ROWS_GATE
    if b.blocking:
        exit_code = EXIT_INVALID
    elif not gate_passed:
        exit_code = EXIT_THRESHOLD_FAILED
    else:
        exit_code = EXIT_PASSED

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "gate_version": GATE_VERSION,
        "generated_at": timezone.now().isoformat(),
        "primary_inputs": {
            "ruleset": str(ruleset_path) if ruleset_path else None,
            "corpus": str(corpus_path) if corpus_path else None,
            "taxonomy_manifest": str(manifest.path) if manifest is not None else str(manifest_path),
            "gate_sample": str(sample_path),
            "labels": str(labels_path),
        },
        "hashes": {
            "ruleset_hash": ruleset.ruleset_hash if ruleset is not None else None,
            "taxonomy_identity_hash": manifest.identity_hash if manifest is not None else None,
            "manifest_semantic_hash": manifest.semantic_hash if manifest is not None else None,
            "sample_hash_recomputed": canonical_hash(sample) if sample is not None else None,
            "artifact_sha256": {
                "gate_sample": _sha256_file(sample_path) if sample_path.exists() else None,
                "labels": _sha256_file(labels_path) if labels_path.exists() else None,
                "ruleset": (
                    _sha256_file(ruleset_path)
                    if ruleset_path and Path(ruleset_path).exists()
                    else None
                ),
                "corpus": (
                    _sha256_file(corpus_path)
                    if corpus_path and Path(corpus_path).exists()
                    else None
                ),
            },
        },
        "validations": validations,
        "replay": replay_summary,
        "overlap": {"computed_overlap": overlap, "computed_empty": not overlap},
        "metrics": metrics,
        "thresholds": thresholds,
        "declared_mismatches": [
            {
                "field_path": m.field_path,
                "declared_value": m.declared_value,
                "recomputed_value": m.recomputed_value,
                "severity": m.severity,
            }
            for m in b.mismatches
        ],
        "blocking_errors": b.blocking,
        "warnings": b.warnings,
        "gate_passed": gate_passed,
    }
    return GateOutcome(
        gate_passed=gate_passed,
        exit_code=exit_code,
        report=report,
        blocking_errors=tuple(b.blocking),
        warnings=tuple(b.warnings),
        mismatches=tuple(b.mismatches),
    )
