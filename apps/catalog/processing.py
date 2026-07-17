"""Catalog-owned processing: audit/apply foundation.

Публичный контракт для всех новых процессов обогащения каталога
(rule/AI/research). Сервис не изменяет каталог напрямую: каждое решение
фиксируется в ``CatalogChange`` и применяется через ``provenance.apply_sourced_value``.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import provenance
from .read_models import rebuild_attrs_cache

if TYPE_CHECKING:
    from .models import Product

TOOL_TYPE_SLUG = "tool_type"

_EMPTY_TOOL_TYPE_SNAPSHOT = {
    "attribute_slug": TOOL_TYPE_SLUG,
    "option_id": None,
    "option_slug": "",
    "option_value": "",
    "source": "",
    "confidence": None,
}


def tool_type_snapshot(product: Product) -> dict:
    """Канонический snapshot текущего tool_type товара.

    Возвращает ``attribute_slug``, ``option_id``, ``option_slug``,
    ``option_value``, ``source``, ``confidence``. Для пустого значения —
    стабильный envelope.
    """
    pav = (
        product.attribute_values.filter(attribute__slug=TOOL_TYPE_SLUG)
        .select_related("attribute", "value_option")
        .first()
    )
    if pav is None or pav.value_option_id is None:
        return dict(_EMPTY_TOOL_TYPE_SNAPSHOT)
    return {
        "attribute_slug": TOOL_TYPE_SLUG,
        "option_id": pav.value_option_id,
        "option_slug": pav.value_option.slug,
        "option_value": pav.value_option.value,
        "source": pav.source,
        "confidence": pav.confidence,
    }


def _operational_baseline(snapshot: dict) -> dict:
    """Baseline для conflict detection: slug/source/confidence + provenance value_hash.

    ``value_hash`` вычисляется тем же алгоритмом, что и в ``provenance.apply_sourced_value``,
    чтобы baseline-сверка в processing не расходилась со внутренней сверкой provenance.
    """
    option_id = snapshot.get("option_id")
    return {
        "attribute_slug": snapshot.get("attribute_slug"),
        "option_slug": snapshot.get("option_slug"),
        "source": snapshot.get("source"),
        "confidence": snapshot.get("confidence"),
        "value_hash": provenance.value_hash(option_id),
    }


def canonical_hash(value: dict) -> str:
    """Стабильный SHA-256 от канонического JSON со сортировкой ключей."""
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CatalogDecisionCommand:
    item_id: int
    target_kind: str
    proposed_value: dict
    source: str
    confidence: int
    idempotency_key: str
    rule_ref: str = ""
    evidence: dict | None = None
    reviewer_id: int | None = None


@dataclass(frozen=True)
class CatalogDecisionResult:
    status: str
    change_id: uuid.UUID
    reason: str = ""


_FINAL_STATUSES = {
    "applied",
    "skipped",
    "conflict",
    "invalid",
    "failed",
    "rejected",
    "reversed",
}


def _status_from_provenance(result: provenance.ApplyResult) -> tuple[str, str]:
    mapping = {
        "applied": ("applied", ""),
        "conflict": ("conflict", result.reason or "baseline_changed"),
        "priority_blocked": ("skipped", result.reason or "priority_blocked"),
        "skipped_locked": ("skipped", result.reason or "content_locked"),
        "invalid": ("invalid", result.reason or "invalid"),
        "missing_product": ("invalid", "missing_product"),
        "missing_attribute": ("invalid", "missing_attribute"),
    }
    return mapping.get(result.status, ("failed", result.reason or "unknown"))


def apply_catalog_decision(cmd: CatalogDecisionCommand) -> CatalogDecisionResult:
    """Атомарно применить предложенное значение tool_type с audit trail.

    Flow:
    1. Валидация DTO.
    2. Идемпотентность по ``idempotency_key``.
    3. Создание ``CatalogChange(status=proposed)``.
    4. Транзакция с блокировкой change/item/product.
    5. Проверка run, content_locked, baseline.
    6. Поиск option строго по slug.
    7. Применение через ``provenance.apply_sourced_value``.
    8. Пересборка attrs_cache и верификация.
    9. Фиксация результата в change.
    10. При исключении — rollback каталога, change -> failed.
    """
    from .models import (
        Attribute,
        AttributeOption,
        CatalogChange,
        CatalogChangeStatus,
        CatalogProcessingItem,
        CatalogProcessingItemStatus,
        CatalogProcessingRunStatus,
        Product,
    )

    # --- 1. DTO validation ---
    if cmd.target_kind != TOOL_TYPE_SLUG:
        return CatalogDecisionResult("invalid", uuid.UUID(int=0), "unsupported_target_kind")
    option_slug = (cmd.proposed_value or {}).get("option_slug")
    if not option_slug or not isinstance(option_slug, str):
        return CatalogDecisionResult("invalid", uuid.UUID(int=0), "missing_option_slug")
    if not (0 <= cmd.confidence <= 100):
        return CatalogDecisionResult("invalid", uuid.UUID(int=0), "confidence_out_of_range")

    # --- 2. Idempotency ---
    existing = CatalogChange.objects.filter(idempotency_key=cmd.idempotency_key).first()
    if existing is not None and existing.status in _FINAL_STATUSES:
        return CatalogDecisionResult(existing.status, existing.id, existing.reason_detail)

    # --- 3. Load item and product ---
    item = CatalogProcessingItem.objects.filter(pk=cmd.item_id).select_related("run").first()
    if item is None:
        return CatalogDecisionResult("invalid", uuid.UUID(int=0), "item_not_found")
    product = Product.objects.filter(pk=item.product_ref).first()
    if product is None:
        return CatalogDecisionResult("invalid", uuid.UUID(int=0), "product_not_found")

    # --- 4. Create proposed change ---
    before = tool_type_snapshot(product)
    before_baseline = _operational_baseline(before)
    before_hash = canonical_hash(before_baseline)
    try:
        change = CatalogChange.objects.create(
            item=item,
            product_ref=item.product_ref,
            target_kind=cmd.target_kind,
            target_key=cmd.target_kind,
            status=CatalogChangeStatus.PROPOSED,
            idempotency_key=cmd.idempotency_key,
            before_value=before,
            proposed_value=cmd.proposed_value,
            baseline_hash=before_hash,
            source=cmd.source,
            confidence=cmd.confidence,
            rule_ref=cmd.rule_ref or "",
            evidence=cmd.evidence or {},
            reviewed_by_id=cmd.reviewer_id,
            reviewed_at=timezone.now() if cmd.reviewer_id else None,
        )
    except IntegrityError:
        # Race condition: другой поток/процесс уже создал change с этим ключом.
        existing = CatalogChange.objects.filter(idempotency_key=cmd.idempotency_key).first()
        if existing is None:
            return CatalogDecisionResult("failed", uuid.UUID(int=0), "idempotency_lookup_failed")
        # Дождаться финального статуса с разумным таймаутом.
        for _ in range(50):
            if existing.status in _FINAL_STATUSES:
                break
            time.sleep(0.01)
            existing = CatalogChange.objects.filter(idempotency_key=cmd.idempotency_key).first()
            if existing is None:
                return CatalogDecisionResult(
                    "failed", uuid.UUID(int=0), "idempotency_lookup_failed"
                )
        return CatalogDecisionResult(existing.status, existing.id, existing.reason_detail)

    # --- 5. Transactional apply ---
    try:
        with transaction.atomic():
            # Lock change, item, product.
            locked_change = CatalogChange.objects.select_for_update().filter(pk=change.pk).first()
            locked_item = (
                CatalogProcessingItem.objects.select_for_update().filter(pk=item.pk).first()
            )
            locked_product = Product.objects.select_for_update().filter(pk=product.pk).first()
            if locked_change is None or locked_item is None or locked_product is None:
                raise RuntimeError("locked_entity_missing")

            # Run must be running.
            if locked_item.run.status != CatalogProcessingRunStatus.RUNNING:
                locked_change.status = CatalogChangeStatus.INVALID
                locked_change.reason_code = "run_not_running"
                locked_change.reason_detail = "run is not in running state"
                locked_change.save(update_fields=["status", "reason_code", "reason_detail"])
                locked_item.status = CatalogProcessingItemStatus.FAILED
                locked_item.error_code = "run_not_running"
                locked_item.save(update_fields=["status", "error_code"])
                return CatalogDecisionResult("invalid", locked_change.id, "run_not_running")

            # Baseline check.
            current_snapshot = tool_type_snapshot(locked_product)
            current_baseline = _operational_baseline(current_snapshot)
            current_hash = canonical_hash(current_baseline)
            stored_baseline_hash = locked_item.baseline_hashes.get(TOOL_TYPE_SLUG, "")
            if current_hash != stored_baseline_hash:
                locked_change.status = CatalogChangeStatus.CONFLICT
                locked_change.reason_code = "baseline_changed"
                locked_change.reason_detail = "tool_type baseline changed after snapshot"
                locked_change.after_value = current_snapshot
                locked_change.save(
                    update_fields=["status", "reason_code", "reason_detail", "after_value"]
                )
                locked_item.status = CatalogProcessingItemStatus.NEEDS_REVIEW
                locked_item.save(update_fields=["status"])
                return CatalogDecisionResult("conflict", locked_change.id, "baseline_changed")

            # Find attribute and option strictly by slug.
            attr = Attribute.objects.filter(slug=TOOL_TYPE_SLUG).first()
            if attr is None:
                locked_change.status = CatalogChangeStatus.INVALID
                locked_change.reason_code = "missing_attribute"
                locked_change.reason_detail = "tool_type attribute not found"
                locked_change.save(update_fields=["status", "reason_code", "reason_detail"])
                return CatalogDecisionResult("invalid", locked_change.id, "missing_attribute")
            option = AttributeOption.objects.filter(attribute=attr, slug=option_slug).first()
            if option is None:
                locked_change.status = CatalogChangeStatus.INVALID
                locked_change.reason_code = "unknown_option"
                locked_change.reason_detail = f"unknown tool_type option: {option_slug}"
                locked_change.save(update_fields=["status", "reason_code", "reason_detail"])
                return CatalogDecisionResult("invalid", locked_change.id, "unknown_option")

            # Apply through provenance.
            # Используем value_hash из baseline, чтобы совпадал с алгоритмом provenance.
            sourced_cmd = provenance.SourcedValueCommand(
                product_id=locked_product.pk,
                target_kind="attribute",
                attribute_slug=TOOL_TYPE_SLUG,
                value={"type": "option", "value": option_slug},
                source=cmd.source,
                confidence=cmd.confidence / 100.0,
                observed_value_hash=before_baseline["value_hash"],
                observed_source=before_baseline["source"],
                allow_equal_override=True,
            )
            apply_result = provenance.apply_sourced_value(sourced_cmd)

            status, reason = _status_from_provenance(apply_result)
            locked_change.status = status
            locked_change.reason_code = reason or apply_result.status
            locked_change.reason_detail = reason

            if status == "applied":
                # Rebuild attrs_cache and verify.
                rebuild_attrs_cache(locked_product)
                locked_product.refresh_from_db()
                actual_cache_value = (locked_product.attrs_cache or {}).get(TOOL_TYPE_SLUG)
                if actual_cache_value != option.value:
                    raise RuntimeError("attrs_cache_mismatch")
                locked_change.applied_at = timezone.now()
                locked_item.status = CatalogProcessingItemStatus.COMPLETED
                locked_item.finished_at = timezone.now()
            else:
                locked_item.status = CatalogProcessingItemStatus.NEEDS_REVIEW

            after = tool_type_snapshot(locked_product)
            locked_change.after_value = after
            locked_change.save(
                update_fields=[
                    "status",
                    "reason_code",
                    "reason_detail",
                    "after_value",
                    "applied_at",
                ]
            )
            locked_item.save(update_fields=["status", "finished_at"])
            return CatalogDecisionResult(status, locked_change.id, reason)

    except Exception as exc:  # noqa: BLE001 — техническая ошибка, каталог откатывается
        with transaction.atomic():
            failed_change = CatalogChange.objects.filter(pk=change.pk).first()
            if failed_change is not None:
                failed_change.status = CatalogChangeStatus.FAILED
                failed_change.reason_code = "apply_exception"
                failed_change.reason_detail = str(exc)[:255]
                failed_change.save(update_fields=["status", "reason_code", "reason_detail"])
            failed_item = CatalogProcessingItem.objects.filter(pk=item.pk).first()
            if failed_item is not None:
                failed_item.status = CatalogProcessingItemStatus.FAILED
                failed_item.error_code = "apply_exception"
                failed_item.error_detail = str(exc)[:255]
                failed_item.finished_at = timezone.now()
                failed_item.save(
                    update_fields=["status", "error_code", "error_detail", "finished_at"]
                )
        return CatalogDecisionResult("failed", change.id, str(exc)[:255])
