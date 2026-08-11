"""Independent machine gate для human labels против gate_sample (Wave 7.1/H2).

Команда — тонкий caller над ``apps.catalog.rules_gate.run_independent_gate``:
все проверки (ruleset/corpus/manifest/schema/hashes/replay/overlap/metrics)
пересчитываются независимо из первичных versioned inputs. Declared-поля
артефактов не являются source of truth (Wave 7 finding B: ранее команда
доверяла самодекларированным ``corpus_overlap_checked``/``collision_count``
и self-consistent парам sample↔labels — negative probe воспроизведён и закрыт).

Exit codes: 0 — gate passed; 1 — валидно оценён, thresholds не пройдены;
2 — invalid inputs/schema/hash/provenance/blocking; 3 — internal error.
Команда ничего не пишет в БД и не применяет predictions.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.rules_gate import (
    DEFAULT_CORPUS_PATH,
    EXIT_INTERNAL,
    EXIT_PASSED,
    EXIT_THRESHOLD_FAILED,
    MIN_ROWS_GATE,
    PRECISION_GATE,
    run_independent_gate,
)


def _write_json_atomic(payload: dict, path: Path, force: bool) -> str:
    """Атомарная запись report (конвенция shadow): tempfile + os.replace,
    защита от перезаписи без --force. Возвращает sha256 записанных байтов."""
    import hashlib

    path = Path(path)
    if path.exists() and not force:
        raise CommandError(f"отчёт уже существует (используйте --force): {path}")
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return hashlib.sha256(data).hexdigest()


class Command(BaseCommand):
    help = (
        "Независимая gate-валидация labels против gate_sample (per-rule replay, hashes, metrics)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--gate-sample", type=str, required=True, help="Путь к gate_sample JSON."
        )
        parser.add_argument("--labels", type=str, required=True, help="Путь к labels JSON.")
        parser.add_argument(
            "--ruleset",
            type=str,
            default=None,
            help="Путь к ruleset JSON (default: default RULESET_PATH).",
        )
        parser.add_argument(
            "--corpus",
            type=str,
            default=None,
            help="Путь к applied corpus JSON (default: applied_corpus_tool_type.v1.json).",
        )
        parser.add_argument(
            "--taxonomy-manifest",
            type=str,
            default=None,
            help="Путь к canonical taxonomy manifest (default: tool_type_taxonomy.v1.json).",
        )
        parser.add_argument(
            "--allow-legacy-taxonomy-hash",
            type=str,
            default=None,
            metavar="HASH",
            help="Явно допустить legacy taxonomy_hash sample (DB-order recipe, "
            "артефакты до H1). Без флага расхождение — blocking.",
        )
        parser.add_argument("--format", choices=["text", "json"], default="text")
        parser.add_argument("--out", type=str, default=None, help="Путь для machine report JSON.")
        parser.add_argument("--force", action="store_true", help="Разрешить перезапись --out.")

    def handle(self, *args, **options):
        try:
            outcome = run_independent_gate(
                ruleset_path=options["ruleset"],
                corpus_path=options["corpus"] or DEFAULT_CORPUS_PATH,
                manifest_path=options["taxonomy_manifest"],
                sample_path=Path(options["gate_sample"]),
                labels_path=Path(options["labels"]),
                allow_legacy_taxonomy_hash=options["allow_legacy_taxonomy_hash"],
            )
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"internal gate error: {exc}", returncode=EXIT_INTERNAL) from exc

        report = outcome.report
        if options["out"]:
            digest = _write_json_atomic(report, Path(options["out"]), options["force"])
            self.stdout.write(f"artifact={options['out']} sha256={digest}")
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            self._emit_text(report, outcome.exit_code)

        if outcome.exit_code == EXIT_PASSED:
            return
        metrics = report["metrics"]
        if outcome.exit_code == EXIT_THRESHOLD_FAILED:
            raise CommandError(
                f"gate_passed=false: thresholds не пройдены "
                f"(precision={metrics['precision']:.6f} < {PRECISION_GATE} "
                f"или rows={metrics['rows']} < {MIN_ROWS_GATE})",
                returncode=EXIT_THRESHOLD_FAILED,
            )
        raise CommandError(
            "gate_passed=false: blocking validation errors: "
            + "; ".join(report["blocking_errors"][:5]),
            returncode=outcome.exit_code,
        )

    def _emit_text(self, report: dict, exit_code: int) -> None:
        metrics = report["metrics"]
        decisions = metrics["decisions"]
        summary = " ".join(f"{d}={decisions.get(d, 0)}" for d in sorted(decisions))
        self.stdout.write(f"rows={metrics['rows']} decisions: {summary}")
        self.stdout.write(
            f"observed_precision={round(metrics['precision'], 4)} "
            f"(recomputed: correct={metrics['correct']} / rows={metrics['rows']}; "
            f"unrounded={metrics['precision']})"
        )
        lo, hi = metrics["wilson95"]
        self.stdout.write(f"wilson95=[{lo:.6f}, {hi:.6f}]")
        replay = report["replay"]
        self.stdout.write(
            f"independent replay: rows={replay['rows']} checked={replay['checked']} "
            f"collisions_recomputed={replay['collisions_recomputed']} | "
            f"overlap computed_empty={report['overlap']['computed_empty']}"
        )
        for m in report["declared_mismatches"]:
            self.stdout.write(
                f"mismatch[{m['severity']}] {m['field_path']}: "
                f"declared={m['declared_value']!r} recomputed={m['recomputed_value']!r}"
            )
        for w in report["warnings"]:
            self.stdout.write(self.style.WARNING(f"warning: {w}"))
        for e in report["blocking_errors"]:
            self.stdout.write(f"blocking: {e}")
        rule = (
            f"recomputed precision>={PRECISION_GATE} and rows>={MIN_ROWS_GATE} "
            "and blocking_errors==0"
        )
        self.stdout.write(f"gate_passed={'true' if report['gate_passed'] else 'false'} ({rule})")
