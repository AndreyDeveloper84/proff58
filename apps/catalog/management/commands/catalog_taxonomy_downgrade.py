"""Понижение версии canonical taxonomy manifest: N → N-1 (Wave 7.1 / Stage H5).

Read-only по умолчанию: строит план понижения и, при необходимости, выдаёт пару
снимков для ``catalog_tool_type_rollback`` (перенос товаров с исчезающих опций).
Запись — только с ``--apply`` и только один вид: удаление освободившихся опций
(``--drop-options``), которое fail-closed по usage.

Штатный порядок понижения (см. `docs/catalog/tool-type-reverse-migration.md`):

1. план (эта команда, read-only) → убедиться, что ``feasible=True``;
2. ``--emit-from/--emit-to`` → ``catalog_tool_type_rollback --apply`` (перенос товаров);
3. ``--drop-options --apply`` (удаление опций, которых нет в N-1);
4. ``load_tool_types --manifest <N-1>`` (возврат ``reappearing`` опций).

Exit codes: 0 — план исполним (и выполненные шаги прошли); 1 — план не исполним
(blocking: осиротевшие товары, смена value, live не на манифесте N);
2 — невалидные артефакты / несмежные версии; 3 — internal.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.taxonomy_manifest import MANIFEST_PATH
from apps.catalog.taxonomy_reverse import (
    ReverseMigrationError,
    build_downgrade_plan,
    drop_disappearing_options,
    plan_bytes,
    snapshot_pair_for_remap,
)
from apps.catalog.tool_type_rollback import (
    EXIT_CONFLICT,
    EXIT_INTERNAL,
    EXIT_INVALID,
    RollbackError,
    snapshot_bytes,
)

from ._h5_io import write_bytes_atomic


class Command(BaseCommand):
    help = "План понижения версии словаря tool_type (N → N-1). Read-only без --apply."

    def add_arguments(self, parser):
        parser.add_argument(
            "--from-manifest",
            default=str(MANIFEST_PATH),
            help="Манифест версии N (default: canonical).",
        )
        parser.add_argument("--to-manifest", required=True, help="Манифест версии N-1.")
        parser.add_argument(
            "--remap",
            default=None,
            help="JSON {исчезающий_slug: целевой_slug} — явные решения владельца.",
        )
        parser.add_argument("--out", default=None, help="Файл плана (канонический артефакт).")
        parser.add_argument("--emit-from", default=None, help="Куда записать снимок from.")
        parser.add_argument("--emit-to", default=None, help="Куда записать снимок to.")
        parser.add_argument(
            "--drop-options",
            action="store_true",
            help="Шаг удаления опций, отсутствующих в N-1 (запись только с --apply).",
        )
        parser.add_argument("--apply", action="store_true", help="Разрешить запись в БД.")
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def handle(self, *args, **options):
        remap = _load_remap(options["remap"])
        try:
            plan = build_downgrade_plan(
                from_manifest=options["from_manifest"],
                to_manifest=options["to_manifest"],
                remap=remap,
            )
        except (ReverseMigrationError, ValueError, FileNotFoundError) as exc:
            raise CommandError(str(exc), returncode=EXIT_INVALID) from exc
        except Exception as exc:  # noqa: BLE001
            raise CommandError(
                f"internal downgrade error: {exc}", returncode=EXIT_INTERNAL
            ) from exc

        if options["out"]:
            write_bytes_atomic(plan_bytes(plan.document), Path(options["out"]))
        self._emit(plan, options["format"])

        if not plan.feasible:
            raise CommandError(
                f"понижение не исполнимо: {len(plan.blocking)} blocking "
                "(см. отчёт выше) — нужен явный remap или решение владельца",
                returncode=EXIT_CONFLICT,
            )

        if options["emit_from"] or options["emit_to"]:
            self._emit_pair(plan, options)
        if options["drop_options"]:
            self._drop(plan, options["apply"])

    # --- шаги ---

    def _emit_pair(self, plan, options) -> None:
        if not (options["emit_from"] and options["emit_to"]):
            raise CommandError(
                "--emit-from и --emit-to задаются только вместе", returncode=EXIT_INVALID
            )
        try:
            from_doc, to_doc = snapshot_pair_for_remap(plan)
        except (ReverseMigrationError, RollbackError) as exc:
            raise CommandError(str(exc), returncode=EXIT_INVALID) from exc
        write_bytes_atomic(snapshot_bytes(from_doc), Path(options["emit_from"]))
        write_bytes_atomic(snapshot_bytes(to_doc), Path(options["emit_to"]))
        self.stdout.write(
            f"snapshot pair: rows={from_doc['canonical']['rows_count']} "
            f"from={options['emit_from']} to={options['emit_to']}"
        )

    def _drop(self, plan, apply: bool) -> None:
        try:
            result = drop_disappearing_options(plan, apply=apply)
        except ReverseMigrationError as exc:
            raise CommandError(str(exc), returncode=EXIT_CONFLICT) from exc
        if apply:
            self.stdout.write(
                f"drop: dropped={result['dropped']} already_absent={result['already_absent']}"
            )
        else:
            self.stdout.write(f"drop: mode=dry-run would_drop={result['would_drop']}")

    # --- вывод ---

    def _emit(self, plan, fmt: str) -> None:
        if fmt == "json":
            self.stdout.write(plan_bytes(plan.document).decode("utf-8").rstrip("\n"))
            return
        canonical = plan.document["canonical"]
        summary = plan.summary
        self.stdout.write(
            f"downgrade v{canonical['from']['manifest_version']} → "
            f"v{canonical['to']['manifest_version']}: feasible={plan.feasible}"
        )
        self.stdout.write(
            f"  keep={summary['keep']} reappearing={summary['reappearing']} "
            f"drop={summary['drop']} remap={summary['remap']} blocked={summary['blocked']} "
            f"affected_products={summary['affected_products']}"
        )
        for entry in plan.entries:
            if entry["disposition"] == "keep":
                continue
            self.stdout.write(
                f"  [{entry['disposition']}] {entry['slug']} pav={entry['pav_count']} "
                f"remap_to={entry['remap_to']!r} reason={entry['reason']}"
            )
        for block in plan.blocking:
            self.stdout.write(f"  !! {block['code']} {block['slug']}: {block['detail']}")


def _load_remap(path: str | None) -> dict | None:
    if path is None:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CommandError(f"--remap: файл не найден: {path}", returncode=EXIT_INVALID) from exc
    except json.JSONDecodeError as exc:
        raise CommandError(f"--remap: не валидный JSON: {exc}", returncode=EXIT_INVALID) from exc
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise CommandError(
            "--remap: ожидается объект {исчезающий_slug: целевой_slug}", returncode=EXIT_INVALID
        )
    return data
