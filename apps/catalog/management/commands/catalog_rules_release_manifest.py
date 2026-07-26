"""Генерация и проверка release manifest контура ``tool_type`` (Wave 7.1/H3).

Два режима:

- по умолчанию — пересчитать manifest из первичных входов и записать его
  (идемпотентно: байт-идентичный файл переписывается как no-op, отличия
  требуют ``--force``);
- ``--check`` — пересчитать и сравнить с зафиксированным файлом; любое
  расхождение (включая самосогласованность ``canonical_hash``) → exit 2.
  Это режим CI: он ловит дрейф ruleset / corpus / манифеста таксономии /
  matcher / метрик gate относительно зафиксированной версии контура.

Manifest выпускается только поверх пройденного independent gate (H2):
если gate не прошёл, команда завершается его же exit code (1 или 2).

Exit codes: 0 — ok; 1 — gate thresholds не пройдены; 2 — invalid inputs /
blocking gate errors / расхождение с зафиксированным manifest; 3 — internal.
Команда ничего не пишет в БД и не применяет predictions.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.catalog.rules_gate import (
    EXIT_INTERNAL,
    EXIT_INVALID,
    EXIT_THRESHOLD_FAILED,
    MIN_ROWS_GATE,
    PRECISION_GATE,
)
from apps.catalog.rules_release import (
    RELEASE_MANIFEST_PATH,
    ReleaseManifestError,
    build_release_manifest,
    canonical_bytes,
    diff_canonical,
    load_release_manifest,
)


class Command(BaseCommand):
    help = (
        "Release manifest контура tool_type: генерация из первичных входов "
        "или проверка зафиксированного (--check) на дрейф."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--manifest",
            type=str,
            default=str(RELEASE_MANIFEST_PATH),
            help="Файл release manifest (цель записи или источник --check).",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Не писать: сравнить пересчитанный manifest с зафиксированным.",
        )
        parser.add_argument(
            "--force", action="store_true", help="Разрешить перезапись отличающегося файла."
        )
        parser.add_argument("--format", choices=["text", "json"], default="text")
        parser.add_argument("--ruleset", type=str, default=None, help="Путь к ruleset JSON.")
        parser.add_argument("--corpus", type=str, default=None, help="Путь к applied corpus JSON.")
        parser.add_argument(
            "--taxonomy-manifest", type=str, default=None, help="Путь к canonical manifest."
        )
        parser.add_argument(
            "--gate-sample", type=str, default=None, help="Путь к замороженному gate_sample."
        )
        parser.add_argument("--labels", type=str, default=None, help="Путь к labels JSON.")
        parser.add_argument(
            "--allow-legacy-taxonomy-hash",
            type=str,
            default=None,
            metavar="HASH",
            help="Явно допустить legacy taxonomy_hash sample (артефакты до H1).",
        )

    def handle(self, *args, **options):
        try:
            document, outcome = build_release_manifest(
                ruleset_path=options["ruleset"],
                corpus_path=options["corpus"],
                manifest_path=options["taxonomy_manifest"],
                sample_path=options["gate_sample"],
                labels_path=options["labels"],
                allow_legacy_taxonomy_hash=options["allow_legacy_taxonomy_hash"],
            )
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CommandError(
                f"internal release manifest error: {exc}", returncode=EXIT_INTERNAL
            ) from exc

        if document is None:
            self._fail_gate(outcome)

        path = Path(options["manifest"])
        if options["check"]:
            self._check(document, path, options["format"])
        else:
            self._write(document, path, options["force"], options["format"])

    # --- режимы ---

    def _check(self, document: dict, path: Path, fmt: str) -> None:
        try:
            recorded = load_release_manifest(path)
        except ReleaseManifestError as exc:
            raise CommandError(str(exc), returncode=EXIT_INVALID) from exc
        diffs = diff_canonical(recorded["canonical"], document["canonical"])
        if recorded["canonical_hash"] != document["canonical_hash"] and not diffs:
            diffs.append(
                f"canonical_hash: зафиксирован {recorded['canonical_hash']!r}, "
                f"пересчитан {document['canonical_hash']!r}"
            )
        self._emit(document, fmt, mode="check", path=path)
        if diffs:
            for d in diffs:
                self.stdout.write(f"drift: {d}")
            raise CommandError(
                f"release manifest не соответствует пересчитанному ({len(diffs)} расхождений): "
                f"{path}",
                returncode=EXIT_INVALID,
            )
        self.stdout.write("check=ok (зафиксированный manifest совпадает с пересчитанным)")

    def _write(self, document: dict, path: Path, force: bool, fmt: str) -> None:
        data = canonical_bytes(document)
        existing = path.read_bytes() if path.exists() else None
        if existing == data:
            self._emit(document, fmt, mode="unchanged", path=path)
            self.stdout.write(f"unchanged={path} (байт-идентичен)")
            return
        if existing is not None and not force:
            raise CommandError(
                f"release manifest уже существует и отличается (используйте --force): {path}",
                returncode=EXIT_INVALID,
            )
        _write_bytes_atomic(data, path)
        self._emit(document, fmt, mode="written", path=path)
        self.stdout.write(f"written={path}")

    # --- вывод ---

    def _emit(self, document: dict, fmt: str, *, mode: str, path: Path) -> None:
        if fmt == "json":
            self.stdout.write(canonical_bytes(document).decode("utf-8").rstrip("\n"))
            return
        c = document["canonical"]
        inputs = c["inputs"]
        metrics = c["gate"]["metrics"]
        lo, hi = metrics["wilson95"]
        # generated_at — non-canonical: в файл не пишется, только в вывод
        self.stdout.write(f"mode={mode} generated_at={timezone.now().isoformat()}")
        self.stdout.write(
            f"matcher_version={c['matcher_version']} gate_version={c['gate_version']} "
            f"schema_version={c['schema_version']}"
        )
        self.stdout.write(
            f"ruleset={inputs['ruleset']['path']} id={inputs['ruleset']['ruleset_id']} "
            f"rules={inputs['ruleset']['rules']} hash={inputs['ruleset']['ruleset_hash']}"
        )
        self.stdout.write(
            f"corpus={inputs['corpus']['path']} id={inputs['corpus']['corpus_id']} "
            f"items={inputs['corpus']['items']}"
        )
        self.stdout.write(
            f"taxonomy identity={inputs['taxonomy_manifest']['taxonomy_identity_hash']} "
            f"semantic={inputs['taxonomy_manifest']['manifest_semantic_hash']} "
            f"options={inputs['taxonomy_manifest']['options']}"
        )
        self.stdout.write(
            f"gate rows={metrics['rows']} correct={metrics['correct']} "
            f"precision={metrics['precision']} wilson95=[{lo:.6f}, {hi:.6f}]"
        )
        self.stdout.write(f"canonical_hash={document['canonical_hash']}")

    def _fail_gate(self, outcome) -> None:
        metrics = outcome.report["metrics"]
        if outcome.exit_code == EXIT_THRESHOLD_FAILED:
            raise CommandError(
                "release manifest не выпущен: gate thresholds не пройдены "
                f"(precision={metrics['precision']:.6f} < {PRECISION_GATE} "
                f"или rows={metrics['rows']} < {MIN_ROWS_GATE})",
                returncode=EXIT_THRESHOLD_FAILED,
            )
        raise CommandError(
            "release manifest не выпущен: blocking gate errors: "
            + "; ".join(outcome.report["blocking_errors"][:5]),
            returncode=outcome.exit_code or EXIT_INVALID,
        )


def _write_bytes_atomic(data: bytes, path: Path) -> None:
    """Атомарная запись (конвенция shadow/gate): tempfile + os.replace."""
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
