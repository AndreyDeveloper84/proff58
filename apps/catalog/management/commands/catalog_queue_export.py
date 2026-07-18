"""Экспорт CatalogProcessingRun в версионированный JSON.

Пример:

    python manage.py catalog_queue_export --run <uuid>

Файл пишется в ``var/catalog-processing/outbox/<run-id>.json``.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    CatalogProcessingRun,
    CatalogProcessingRunStatus,
)

SCHEMA_VERSION = "1.0"
BASE_DIR = Path(settings.BASE_DIR) / "var" / "catalog-processing"
OUTBOX_DIR = BASE_DIR / "outbox"


def _ensure_dirs() -> None:
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)


def _allowed_tool_type_options() -> list[dict[str, Any]]:
    attr = Attribute.objects.filter(slug="tool_type").first()
    if attr is None:
        return []
    return [
        {
            "slug": opt.slug,
            "value": opt.value,
        }
        for opt in AttributeOption.objects.filter(attribute=attr).order_by("slug")
    ]


def _taxonomy_hash(options: list[dict[str, Any]]) -> str:
    payload = json.dumps(options, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_export(run: CatalogProcessingRun) -> dict[str, Any]:
    options = _allowed_tool_type_options()
    taxonomy_hash = _taxonomy_hash(options)
    if run.taxonomy_hash and run.taxonomy_hash != taxonomy_hash:
        raise CommandError("Taxonomy изменилась после предыдущего export; создайте новый run.")
    items = []
    for item in run.items.select_related("product").order_by("product_ref"):
        items.append(
            {
                "product_ref": item.product_ref,
                "product_id": item.product_id,
                "article": item.input_snapshot.get("article", ""),
                "code_1c": item.input_snapshot.get("code_1c", ""),
                "barcode": item.input_snapshot.get("barcode", ""),
                "original_name": item.input_snapshot.get("original_name", ""),
                "name": item.input_snapshot.get("name", ""),
                "brand": item.input_snapshot.get("brand", ""),
                "category_id": item.input_snapshot.get("category_id"),
                "category_path": item.input_snapshot.get("category_path", ""),
                "source_group": item.input_snapshot.get("source_group", ""),
                "input_snapshot": item.input_snapshot,
                "input_hash": item.input_hash,
                "baseline_hash": item.baseline_hashes.get("tool_type", ""),
                "needed_targets": item.needed_targets,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(run.pk),
        "taxonomy_hash": taxonomy_hash,
        "target_kind": run.mode,
        "allowed_options": options,
        "items": items,
    }


class Command(BaseCommand):
    help = "Экспортировать CatalogProcessingRun в JSON."

    def add_arguments(self, parser):
        parser.add_argument("--run", type=str, required=True, help="UUID run.")
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Путь к выходному файлу (по умолчанию var/catalog-processing/outbox/<run-id>.json).",
        )
        parser.add_argument(
            "--pretty",
            action="store_true",
            help="Форматировать JSON с отступами (по умолчанию compact).",
        )

    def handle(self, *args, **options):
        if not settings.FEATURES.get("catalog_processing", False):
            raise CommandError("Feature catalog_processing выключен.")

        run_id = options["run"]
        output_path = options["output"]
        pretty = options["pretty"]

        run = CatalogProcessingRun.objects.filter(pk=run_id).first()
        if run is None:
            raise CommandError(f"Run {run_id} не найден.")
        if run.status not in {CatalogProcessingRunStatus.DRAFT, CatalogProcessingRunStatus.RUNNING}:
            raise CommandError(f"Run {run_id} в статусе {run.status}, экспорт невозможен.")

        export_data = _build_export(run)
        separators = (",", ":") if not pretty else (",", ": ")
        indent = 2 if pretty else None

        # Checksum от payload без exported_at/checksum: временная метка
        # не должна ломать детерминированность повторного export.
        checksum_payload_data = {k: v for k, v in export_data.items() if k != "exported_at"}
        checksum_payload = json.dumps(
            checksum_payload_data,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        checksum = hashlib.sha256(checksum_payload.encode("utf-8")).hexdigest()
        export_data["checksum"] = checksum
        export_data["exported_at"] = timezone.now().isoformat()
        final_payload = json.dumps(
            export_data,
            sort_keys=True,
            ensure_ascii=False,
            indent=indent,
            separators=separators,
            default=str,
        )

        _ensure_dirs()
        if output_path is None:
            output_path = str(OUTBOX_DIR / f"{run_id}.json")
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write через tempfile.
        fd, temp_name = tempfile.mkstemp(dir=str(output_path.parent), suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(final_payload)
            os.replace(temp_name, output_path)
        except Exception:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
            raise

        run.taxonomy_hash = export_data["taxonomy_hash"]
        run_stats = dict(run.stats or {})
        run_stats.update(
            {
                "last_export_checksum": checksum,
                "last_exported_at": export_data["exported_at"],
            }
        )
        run.stats = run_stats
        run.save(update_fields=["taxonomy_hash", "stats"])

        self.stdout.write(self.style.SUCCESS(f"Экспортировано: {output_path}"))
        self.stdout.write(f"items: {len(export_data['items'])}, checksum: {checksum}")
        return str(output_path)
