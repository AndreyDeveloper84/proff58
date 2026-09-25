"""Снимок текущего состояния ``tool_type`` — точка отката (Wave 7.1 / Stage H5).

Read-only по БД: команда только читает каталог и пишет канонический артефакт.
Снимается ДО записи (снимок «до») и повторно ПОСЛЕ (снимок «после»); откат
исполняется по паре — см. ``catalog_tool_type_rollback`` и
``docs/catalog/operations/rollback.md``.

Ровно один селектор: ``--product-ids`` (явные id — предпочтительно, rollback-map
должна быть явной), ``--option-slug`` (все товары на этих типах) или
``--all-with-tool-type``.

Exit codes: 0 — снимок записан; 2 — невалидный селектор / отказ перезаписи;
3 — internal.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.tool_type_rollback import (
    EXIT_INTERNAL,
    EXIT_INVALID,
    RollbackError,
    build_snapshot,
    snapshot_bytes,
)

from ._h5_io import write_bytes_atomic


class Command(BaseCommand):
    help = "Снимок состояния tool_type по товарам (артефакт отката). В БД не пишет."

    def add_arguments(self, parser):
        parser.add_argument("--product-ids", default=None, help="Явные id товаров через запятую.")
        parser.add_argument(
            "--option-slug",
            action="append",
            default=None,
            help="Все товары, несущие этот tool_type (можно повторять).",
        )
        parser.add_argument(
            "--all-with-tool-type",
            action="store_true",
            help="Все товары, у которых проставлен tool_type.",
        )
        parser.add_argument("--out", default=None, help="Файл артефакта (иначе — stdout).")
        parser.add_argument(
            "--force", action="store_true", help="Разрешить перезапись отличающегося файла."
        )
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def handle(self, *args, **options):
        product_ids = _parse_ids(options["product_ids"])
        try:
            document = build_snapshot(
                product_ids=product_ids,
                option_slugs=options["option_slug"],
                all_with_tool_type=options["all_with_tool_type"],
            )
        except RollbackError as exc:
            raise CommandError(str(exc), returncode=EXIT_INVALID) from exc
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"internal snapshot error: {exc}", returncode=EXIT_INTERNAL) from exc

        data = snapshot_bytes(document)
        if options["out"]:
            _write(Path(options["out"]), data, options["force"])
        canonical = document["canonical"]
        if options["format"] == "json":
            self.stdout.write(data.decode("utf-8").rstrip("\n"))
        else:
            self.stdout.write(
                f"selector={canonical['selector']['kind']} rows={canonical['rows_count']} "
                f"taxonomy_identity={canonical['live_taxonomy_identity_hash'][:12]}… "
                f"canonical_hash={document['canonical_hash']}"
            )
        if options["out"]:
            self.stdout.write(f"written={options['out']}")


def _parse_ids(raw: str | None) -> list[int] | None:
    if raw is None:
        return None
    try:
        return [int(chunk) for chunk in raw.replace(",", " ").split()]
    except ValueError as exc:
        raise CommandError(f"--product-ids: ожидались целые id: {raw!r}", returncode=2) from exc


def _write(path: Path, data: bytes, force: bool) -> None:
    existing = path.read_bytes() if path.exists() else None
    if existing == data:
        return
    if existing is not None and not force:
        raise CommandError(
            f"снимок уже существует и отличается (используйте --force): {path}",
            returncode=EXIT_INVALID,
        )
    write_bytes_atomic(data, path)
