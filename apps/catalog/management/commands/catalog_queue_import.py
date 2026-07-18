"""Импорт result JSON в CatalogChange(status=proposed).

Пример:

    python manage.py catalog_queue_import \\
        --file var/catalog-processing/inbox/<run-id>.result.json \\
        --dry-run

Commit:

    python manage.py catalog_queue_import \\
        --file var/catalog-processing/inbox/<run-id>.result.json \\
        --commit
"""

from __future__ import annotations

import hashlib
import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from jsonschema import Draft7Validator, FormatChecker

from apps.catalog.models import (
    Attribute,
    CatalogChange,
    CatalogProcessingItem,
    CatalogProcessingItemStatus,
    CatalogProcessingRun,
    CatalogProcessingRunStatus,
    Product,
)
from apps.catalog.processing import (
    CatalogChangeCommand,
    canonical_hash,
    create_catalog_change,
    tool_type_snapshot,
)
from apps.catalog.queue_contract import (
    _allowed_tool_type_options,
    _product_snapshot,
    _taxonomy_hash,
)

SCHEMA_VERSION = "1.0"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
INBOX_DIR = Path(settings.BASE_DIR) / "var" / "catalog-processing" / "inbox"
WORKABLE_ITEM_STATUSES = {
    CatalogProcessingItemStatus.PENDING,
    CatalogProcessingItemStatus.PROCESSING,
    CatalogProcessingItemStatus.NEEDS_REVIEW,
}


class ItemImportError(Exception):
    """Ошибка одного item; соседние items должны продолжить импорт."""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_path(path_str: str, *, allow_external: bool = False) -> Path:
    """Защита от path traversal; по умолчанию читаем только из inbox."""
    path = Path(path_str)
    if ".." in path.parts:
        raise CommandError(f"Path traversal запрещён: {path}")
    path = path.resolve()
    inbox = INBOX_DIR.resolve()
    if not allow_external and not path.is_relative_to(inbox):
        raise CommandError(f"Файл должен находиться внутри {inbox}")
    if not path.exists():
        raise CommandError(f"Файл не найден: {path}")
    if not path.is_file():
        raise CommandError(f"Не файл: {path}")
    return path


def _load_json(path: Path) -> Any:
    size = path.stat().st_size
    if size > MAX_FILE_SIZE:
        raise CommandError(f"Файл слишком большой: {size} > {MAX_FILE_SIZE}")
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise CommandError(f"Невалидный JSON: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise CommandError(f"Файл не UTF-8: {exc}") from exc


@lru_cache(maxsize=1)
def _schema_validator() -> Draft7Validator:
    schema_path = (
        Path(settings.BASE_DIR) / "apps" / "catalog" / "schemas" / "catalog_research_result_v1.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema, format_checker=FormatChecker())


def _schema_validation(data: Any) -> None:
    """Полная проверка result-файла по versioned JSON Schema."""
    errors = sorted(
        _schema_validator().iter_errors(data),
        key=lambda error: tuple(str(part) for part in error.path),
    )
    if not errors:
        return
    first = errors[0]
    location = ".".join(str(part) for part in first.absolute_path) or "<root>"
    raise CommandError(f"JSON Schema: {location}: {first.message}")


def _domain_validation(data: dict) -> None:
    """Проверки, которые нельзя выразить одной JSON Schema."""
    items = data["items"]

    refs = set()
    for idx, item in enumerate(items):
        pref = item["product_ref"]
        if pref in refs:
            raise CommandError(f"items[{idx}]: duplicate product_ref {pref}")
        refs.add(pref)
        changes = item.get("changes") or []
        identity_status = item["identity"]["status"]
        if changes and identity_status != "matched":
            raise CommandError(f"items[{idx}]: changes запрещены без identity.status=matched")
        for cidx, change in enumerate(changes):
            source = change.get("source", "web")
            evidence_items = change.get("evidence") or []
            if source in {"web", "llm"} and not evidence_items:
                raise CommandError(
                    f"items[{idx}].changes[{cidx}]: evidence обязателен для {source}"
                )
            for evidence in evidence_items:
                url = evidence["url"]
                parsed = urlparse(url)
                if parsed.scheme != "https" or not parsed.hostname:
                    raise CommandError(f"evidence.url должен быть абсолютным HTTPS URL: {url}")


def _change_idempotency_key(
    *, result_checksum: str, run_id: uuid.UUID, product_ref: int, option_slug: str
) -> str:
    payload = f"{result_checksum}:{run_id}:{product_ref}:tool_type:{option_slug}"
    return f"catalog-import:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


class Command(BaseCommand):
    help = "Импортировать result JSON как CatalogChange(status=proposed)."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, required=True, help="Путь к result JSON.")
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Создать изменения в БД. Без флага — только dry-run.",
        )
        parser.add_argument(
            "--run",
            type=str,
            default=None,
            help="UUID run для дополнительной сверки с JSON.",
        )
        parser.add_argument(
            "--allow-external-path",
            action="store_true",
            help="Разрешить файл вне var/catalog-processing/inbox (только для доверенного оператора).",
        )

    def handle(self, *args, **options):
        if not settings.FEATURES.get("catalog_processing", False):
            raise CommandError("Feature catalog_processing выключен.")

        file_path = _validate_path(options["file"], allow_external=options["allow_external_path"])
        commit = options["commit"]
        run_id_override = options["run"]

        result_checksum = _sha256_file(file_path)
        data = _load_json(file_path)
        _schema_validation(data)
        _domain_validation(data)

        try:
            run_id = uuid.UUID(data["run_id"])
        except (TypeError, ValueError) as exc:
            raise CommandError("run_id не является UUID") from exc
        if run_id_override:
            try:
                override_uuid = uuid.UUID(run_id_override)
            except (TypeError, ValueError) as exc:
                raise CommandError("--run не является UUID") from exc
            if override_uuid != run_id:
                raise CommandError("--run не совпадает с run_id внутри JSON")

        run = CatalogProcessingRun.objects.filter(pk=run_id).first()
        if run is None:
            raise CommandError(f"Run {run_id} не найден")
        if run.status != CatalogProcessingRunStatus.RUNNING:
            raise CommandError(f"Run {run_id} не находится в status=running")

        expected_export_checksum = (run.stats or {}).get("last_export_checksum")
        if not expected_export_checksum:
            raise CommandError("Run ещё не был экспортирован")
        if data["export_checksum"] != expected_export_checksum:
            raise CommandError("export_checksum не совпадает с последним export run")

        items_by_ref = {
            item.product_ref: item
            for item in CatalogProcessingItem.objects.filter(run=run)
            .select_related("product")
            .order_by("product_ref")
        }

        attr = Attribute.objects.filter(slug="tool_type").first()
        if attr is None:
            raise CommandError("Атрибут tool_type не найден")
        option_payload = _allowed_tool_type_options()
        current_taxonomy_hash = _taxonomy_hash(option_payload)
        if not run.taxonomy_hash or data["taxonomy_hash"] != run.taxonomy_hash:
            raise CommandError("taxonomy_hash result не совпадает с run")
        if current_taxonomy_hash != run.taxonomy_hash:
            raise CommandError("Текущая taxonomy изменилась после export")
        allowed_options = {option["slug"] for option in option_payload}

        stats = {
            "total": len(data["items"]),
            "created": 0,
            "would_create": 0,
            "existing": 0,
            "skipped": 0,
            "errors": 0,
            "dry_run": not commit,
            "result_checksum": result_checksum,
            "export_checksum": expected_export_checksum,
        }
        errors: list[str] = []

        for item_data in data["items"]:
            try:
                with transaction.atomic():
                    result = self._process_item(
                        item_data,
                        items_by_ref,
                        allowed_options,
                        run,
                        commit,
                        result_checksum,
                    )
            except ItemImportError as exc:
                result = {"error": str(exc)}
            if result.get("error"):
                stats["errors"] += 1
                errors.append(result["error"])
                if commit:
                    self._record_item_error(
                        items_by_ref.get(item_data["product_ref"]),
                        result["error"],
                    )
            else:
                stats["created"] += result.get("created", 0)
                stats["would_create"] += result.get("would_create", 0)
                stats["existing"] += result.get("existing", 0)
                if result.get("skipped"):
                    stats["skipped"] += 1

        if commit:
            with transaction.atomic():
                locked_run = CatalogProcessingRun.objects.select_for_update().get(pk=run.pk)
                run_stats = dict(locked_run.stats or {})
                imports = list(run_stats.get("recent_imports") or [])
                imports.append(
                    {
                        "result_checksum": result_checksum,
                        "created": stats["created"],
                        "existing": stats["existing"],
                        "errors": stats["errors"],
                    }
                )
                run_stats["recent_imports"] = imports[-20:]
                locked_run.stats = run_stats
                locked_run.save(update_fields=["stats"])

        payload = json.dumps(stats, ensure_ascii=False, indent=2)
        self.stdout.write(payload)
        if errors:
            self.stdout.write(self.style.WARNING("Ошибки:"))
            for err in errors[:20]:
                self.stdout.write(self.style.WARNING(f"  - {err}"))

        if commit:
            self.stdout.write(self.style.SUCCESS(f"Импорт завершён: {stats}"))
        else:
            self.stdout.write(self.style.NOTICE("Dry-run завершён"))
        return payload

    @staticmethod
    def _record_item_error(
        item: CatalogProcessingItem | None,
        detail: str,
    ) -> None:
        if item is None:
            return
        with transaction.atomic():
            locked_item = CatalogProcessingItem.objects.select_for_update().get(pk=item.pk)
            if locked_item.status not in WORKABLE_ITEM_STATUSES:
                return
            locked_item.status = CatalogProcessingItemStatus.NEEDS_REVIEW
            locked_item.error_code = "import_error"
            locked_item.error_detail = detail[:255]
            locked_item.save(update_fields=["status", "error_code", "error_detail"])

    def _process_item(
        self,
        item_data: dict,
        items_by_ref: dict[int, CatalogProcessingItem],
        allowed_options: set[str],
        run: CatalogProcessingRun,
        commit: bool,
        result_checksum: str,
    ) -> dict[str, Any]:
        product_ref = item_data["product_ref"]
        item = items_by_ref.get(product_ref)
        if item is None:
            return {"error": f"product_ref {product_ref}: item не найден"}

        if commit:
            item = CatalogProcessingItem.objects.select_for_update().get(pk=item.pk)
            locked_run = CatalogProcessingRun.objects.select_for_update().get(pk=run.pk)
            if locked_run.status != CatalogProcessingRunStatus.RUNNING:
                raise ItemImportError(f"product_ref {product_ref}: run_not_running")

        if item.input_hash != item_data["input_hash"]:
            return {"error": f"product_ref {product_ref}: input_hash не совпадает"}
        if item.status not in WORKABLE_ITEM_STATUSES:
            return {"error": f"product_ref {product_ref}: item status {item.status} нерабочий"}
        product = Product.objects.filter(pk=item.product_id).first()
        if product is None or product.pk != item.product_ref:
            return {"error": f"product_ref {product_ref}: product identity mismatch"}
        current_input_hash = canonical_hash(_product_snapshot(product))
        if current_input_hash != item.input_hash:
            return {"error": f"product_ref {product_ref}: current input snapshot изменился"}
        baseline = tool_type_snapshot(product)
        current_baseline_hash = canonical_hash(
            {
                "attribute_slug": baseline.get("attribute_slug"),
                "option_slug": baseline.get("option_slug"),
                "source": baseline.get("source"),
                "confidence": baseline.get("confidence"),
            }
        )
        if current_baseline_hash != item.baseline_hashes.get("tool_type", ""):
            return {"error": f"product_ref {product_ref}: baseline изменился"}

        status = item_data.get("status")
        if status in {"unknown", "identity_failed"}:
            if commit:
                item.status = CatalogProcessingItemStatus.NEEDS_REVIEW
                item.error_code = status
                item.error_detail = item_data.get("reason_detail", "")[:255]
                item.save(update_fields=["status", "error_code", "error_detail"])
            return {"skipped": True, "created": 0, "would_create": 0, "existing": 0}

        changes = item_data.get("changes") or []
        if not changes:
            return {"skipped": True, "created": 0, "would_create": 0, "existing": 0}

        for change_data in changes:
            option_slug = change_data["proposed_value"]["option_slug"]
            if option_slug not in allowed_options:
                return {"error": f"product_ref {product_ref}: unknown option {option_slug}"}

        created_count = 0
        existing_count = 0
        would_create_count = 0
        for change_data in changes:
            option_slug = change_data["proposed_value"]["option_slug"]
            source = change_data.get("source", "web")
            confidence = change_data["confidence"]
            idempotency_key = _change_idempotency_key(
                result_checksum=result_checksum,
                run_id=run.pk,
                product_ref=product_ref,
                option_slug=option_slug,
            )
            already_exists = CatalogChange.objects.filter(idempotency_key=idempotency_key).exists()
            if already_exists:
                existing_count += 1
                continue
            if not commit:
                would_create_count += 1
                continue

            cmd = CatalogChangeCommand(
                item_id=item.pk,
                target_kind="tool_type",
                proposed_value={"option_slug": option_slug},
                source=source,
                confidence=confidence,
                idempotency_key=idempotency_key,
                rule_ref="",
                evidence={
                    "identity": item_data.get("identity", {}),
                    "evidence": change_data.get("evidence", []),
                    "reason_code": change_data.get("reason_code", ""),
                    "reason_detail": change_data.get("reason_detail", ""),
                    "result_checksum": result_checksum,
                    "export_checksum": (run.stats or {}).get("last_export_checksum", ""),
                },
            )
            result = create_catalog_change(cmd)
            if result.status == "proposed":
                created_count += 1
            elif result.change_id != uuid.UUID(int=0):
                existing_count += 1
            else:
                raise ItemImportError(f"product_ref {product_ref}: {result.reason}")

        if commit and created_count:
            item.status = CatalogProcessingItemStatus.PROCESSING
            item.error_code = ""
            item.error_detail = ""
            item.save(update_fields=["status", "error_code", "error_detail"])

        return {
            "created": created_count,
            "would_create": would_create_count,
            "existing": existing_count,
            "skipped": not (created_count or would_create_count),
        }
