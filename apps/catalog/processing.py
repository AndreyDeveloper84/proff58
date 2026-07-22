"""Catalog-owned processing: audit/apply foundation.

Публичный контракт для всех новых процессов обогащения каталога
(rule/AI/research). Сервис не изменяет каталог напрямую: каждое решение
фиксируется в ``CatalogChange`` и применяется через ``provenance.apply_sourced_value``.

API разделён на фазы:

1. ``create_catalog_change`` — валидация + создание ``CatalogChange(status=proposed)``.
2. ``validate_catalog_change`` — повторная доменная проверка без изменений.
3. ``review_catalog_change`` — модерация ``proposed -> approved/rejected``.
4. ``apply_catalog_change`` — атомарное применение ``approved``-решения к каталогу.

В v1 все источники (``web``, ``llm``, ``manual``, ``rules``) проходят модерацию
перед apply. Auto-apply не допускается.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import provenance
from .read_models import rebuild_attrs_cache

if TYPE_CHECKING:
    from .models import Product

TOOL_TYPE_SLUG = "tool_type"

# Разрешённые источники для processing-контура (V2 §9).
_PROCESSING_SOURCES = frozenset({"manual", "rules", "web", "llm"})

_EMPTY_TOOL_TYPE_SNAPSHOT = {
    "attribute_slug": TOOL_TYPE_SLUG,
    "option_id": None,
    "option_slug": "",
    "option_value": "",
    "source": "",
    "confidence": None,
}

# Статусы item, в которых допустимо создавать или применять решение.
_WORKABLE_ITEM_STATUSES = {"pending", "processing", "needs_review"}

# Финальные статусы change, после которых повторный вызов возвращает сохранённый результат.
_FINAL_CHANGE_STATUSES = {
    "applied",
    "skipped",
    "conflict",
    "invalid",
    "failed",
    "rejected",
    "reversed",
}

# Финальные статусы item, которые нельзя понижать при ошибках.
_FINAL_ITEM_STATUSES = {"completed", "failed"}


def _feature_enabled() -> bool:
    return bool(settings.FEATURES.get("catalog_processing", False))


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
    """Baseline для conflict detection: только slug/source/confidence.

    ``option_id`` и ``option_value`` не входят: переименование отображаемого
    значения или пересоздание option с тем же slug не должны давать ложный
    conflict (V2 §10).
    """
    return {
        "attribute_slug": snapshot.get("attribute_slug"),
        "option_slug": snapshot.get("option_slug"),
        "source": snapshot.get("source"),
        "confidence": snapshot.get("confidence"),
    }


def _provenance_value_hash(snapshot: dict) -> str:
    """Хеш текущего значения для сверки внутри provenance.apply_sourced_value."""
    return provenance.value_hash(snapshot.get("option_id"))


def canonical_hash(value: dict) -> str:
    """Стабильный SHA-256 от канонического JSON со сортировкой ключей."""
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CatalogChangeCommand:
    item_id: int
    target_kind: str
    proposed_value: dict
    source: str
    confidence: int
    idempotency_key: str
    rule_ref: str = ""
    evidence: dict | None = None


@dataclass(frozen=True)
class CatalogChangeResult:
    status: str
    change_id: uuid.UUID
    reason: str = ""


@dataclass(frozen=True)
class CatalogValidationResult:
    valid: bool
    reason: str = ""


@dataclass(frozen=True)
class CatalogDecisionResult:
    status: str
    change_id: uuid.UUID
    reason: str = ""


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


def _invalid_result(reason: str) -> CatalogChangeResult:
    return CatalogChangeResult("invalid", uuid.UUID(int=0), reason)


def _validate_command(cmd: CatalogChangeCommand) -> CatalogValidationResult:
    """Быстрая валидация DTO без обращения к БД."""
    if cmd.target_kind != TOOL_TYPE_SLUG:
        return CatalogValidationResult(False, "unsupported_target_kind")
    option_slug = (cmd.proposed_value or {}).get("option_slug")
    if not option_slug or not isinstance(option_slug, str):
        return CatalogValidationResult(False, "missing_option_slug")
    if not (0 <= cmd.confidence <= 100):
        return CatalogValidationResult(False, "confidence_out_of_range")
    if cmd.source not in _PROCESSING_SOURCES:
        return CatalogValidationResult(False, "invalid_source")
    return CatalogValidationResult(True, "")


def _resolve_product_for_item(item) -> tuple[Product | None, str]:
    """Возвращает (product, error_reason) с проверкой identity item.product/product_ref."""
    from .models import Product

    # Identity: product_ref должен совпадать с реальным товаром item.product.
    product_id = item.product_id or item.product_ref
    product = Product.objects.filter(pk=product_id).first()
    if product is None:
        return None, "product_not_found"
    if item.product_ref != product.pk:
        return None, "product_identity_mismatch"
    if item.product_id is not None and item.product_id != product.pk:
        return None, "product_identity_mismatch"
    return product, ""


def create_catalog_change(cmd: CatalogChangeCommand) -> CatalogChangeResult:
    """Создать предложение изменения каталога без его применения.

    Flow:
    1. Проверка feature flag.
    2. Валидация DTO (target, option, confidence, source).
    3. Идемпотентность по ``idempotency_key``.
    4. Блокировка run + item и повторная проверка состояния.
    5. Проверка identity товара и создание ``CatalogChange(status=proposed)``.
    """
    from .models import (
        CatalogChange,
        CatalogChangeStatus,
        CatalogProcessingItem,
        CatalogProcessingRun,
        CatalogProcessingRunStatus,
    )

    if not _feature_enabled():
        return _invalid_result("feature_disabled")

    validation = _validate_command(cmd)
    if not validation.valid:
        return _invalid_result(validation.reason)

    # --- Idempotency (cheap check outside transaction) ---
    existing = CatalogChange.objects.filter(idempotency_key=cmd.idempotency_key).first()
    if existing is not None:
        return CatalogChangeResult(existing.status, existing.id, existing.reason_detail)

    # --- Load and lock item + run, re-check state, create change atomically ---
    try:
        with transaction.atomic():
            item = CatalogProcessingItem.objects.select_for_update().filter(pk=cmd.item_id).first()
            if item is None:
                return _invalid_result("item_not_found")

            run = CatalogProcessingRun.objects.select_for_update().filter(pk=item.run_id).first()
            if run is None:
                return _invalid_result("run_not_found")
            if run.status != CatalogProcessingRunStatus.RUNNING:
                return _invalid_result("run_not_running")
            if item.status not in _WORKABLE_ITEM_STATUSES:
                return _invalid_result("item_not_workable")
            if cmd.target_kind not in (item.needed_targets or []):
                return _invalid_result("target_not_needed")

            product, error_reason = _resolve_product_for_item(item)
            if product is None:
                return _invalid_result(error_reason)

            before = tool_type_snapshot(product)
            before_baseline = _operational_baseline(before)
            before_hash = canonical_hash(before_baseline)
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
            )
            return CatalogChangeResult("proposed", change.id, "")
    except IntegrityError:
        existing = CatalogChange.objects.filter(idempotency_key=cmd.idempotency_key).first()
        if existing is None:
            return CatalogChangeResult("failed", uuid.UUID(int=0), "idempotency_lookup_failed")
        return CatalogChangeResult(existing.status, existing.id, existing.reason_detail)


def validate_catalog_change(change_id: uuid.UUID) -> CatalogValidationResult:
    """Доменная валидация предложения без его изменения.

    Проверяет: run в работе, item workable, target нужен, продукт существует,
    option существует, baseline не изменился. Не применяет решение.
    """
    from .models import (
        Attribute,
        AttributeOption,
        CatalogChange,
        CatalogChangeStatus,
        CatalogProcessingRunStatus,
    )

    if not _feature_enabled():
        return CatalogValidationResult(False, "feature_disabled")

    change = CatalogChange.objects.filter(pk=change_id).select_related("item__run").first()
    if change is None:
        return CatalogValidationResult(False, "change_not_found")
    if change.status in _FINAL_CHANGE_STATUSES:
        return CatalogValidationResult(False, "change_final")
    if change.status not in {CatalogChangeStatus.PROPOSED, CatalogChangeStatus.APPROVED}:
        return CatalogValidationResult(False, "change_not_reviewable")

    item = change.item
    if item is None:
        return CatalogValidationResult(False, "item_missing")
    if item.run.status != CatalogProcessingRunStatus.RUNNING:
        return CatalogValidationResult(False, "run_not_running")
    if item.status not in _WORKABLE_ITEM_STATUSES:
        return CatalogValidationResult(False, "item_not_workable")
    if change.target_kind not in (item.needed_targets or []):
        return CatalogValidationResult(False, "target_not_needed")

    product, error_reason = _resolve_product_for_item(item)
    if product is None:
        return CatalogValidationResult(False, error_reason)

    current_snapshot = tool_type_snapshot(product)
    current_baseline = _operational_baseline(current_snapshot)
    current_hash = canonical_hash(current_baseline)
    stored_baseline_hash = item.baseline_hashes.get(TOOL_TYPE_SLUG, "")
    if current_hash != stored_baseline_hash:
        return CatalogValidationResult(False, "baseline_changed")

    try:
        attr = Attribute.objects.get(slug=TOOL_TYPE_SLUG)
    except Attribute.DoesNotExist:
        return CatalogValidationResult(False, "missing_attribute")
    option_slug = change.proposed_value.get("option_slug")
    try:
        AttributeOption.objects.get(attribute=attr, slug=option_slug)
    except AttributeOption.DoesNotExist:
        return CatalogValidationResult(False, "unknown_option")
    except AttributeOption.MultipleObjectsReturned:
        return CatalogValidationResult(False, "option_slug_conflict")

    return CatalogValidationResult(True, "")


def review_catalog_change(
    change_id: uuid.UUID,
    decision: str,
    reviewer_id: int,
    comment: str = "",
) -> CatalogChangeResult:
    """Модерация: ``proposed`` -> ``approved``/``rejected``.

    Записывает ``reviewed_by``, ``reviewed_at`` и ``comment``. Только
    ``approved``-решения могут быть применены ``apply_catalog_change``.
    Блокирует change и повторно проверяет статус под блокировкой.

    При ``rejected``: если у item не осталось открытых (``proposed``/``approved``)
    changes и item ещё не финальный, item переводится в ``needs_review`` с
    ``error_code="rejected"`` — иначе item навсегда оставался бы ``processing``
    и блокировал finalize run. Replay по уже ``rejected`` change лечит такой
    stranded item, оставшийся от решений до этого исправления.
    """
    from .models import CatalogChange, CatalogChangeStatus

    if not _feature_enabled():
        return _invalid_result("feature_disabled")

    if decision not in {CatalogChangeStatus.APPROVED, CatalogChangeStatus.REJECTED}:
        return _invalid_result("invalid_review_decision")
    if not reviewer_id:
        return _invalid_result("missing_reviewer")

    try:
        with transaction.atomic():
            change = CatalogChange.objects.select_for_update().filter(pk=change_id).first()
            if change is None:
                return _invalid_result("change_not_found")
            if change.status in _FINAL_CHANGE_STATUSES:
                if (
                    decision == CatalogChangeStatus.REJECTED
                    and change.status == CatalogChangeStatus.REJECTED
                ):
                    _close_item_after_reject(change)
                return CatalogChangeResult(change.status, change.id, change.reason_detail)
            if change.status != CatalogChangeStatus.PROPOSED:
                return _invalid_result("change_not_proposed")

            change.status = decision
            change.reviewed_by_id = reviewer_id
            change.reviewed_at = timezone.now()
            change.comment = comment or ""
            change.save(update_fields=["status", "reviewed_by_id", "reviewed_at", "comment"])
            if decision == CatalogChangeStatus.REJECTED:
                _close_item_after_reject(change)
            return CatalogChangeResult(decision, change.id, "")
    except Exception as exc:  # noqa: BLE001
        return CatalogChangeResult("failed", uuid.UUID(int=0), str(exc)[:255])


def _close_item_after_reject(change) -> None:
    """Завершает item после reject, если открытых changes не осталось.

    Вызывается внутри транзакции ``review_catalog_change`` под блокировкой
    change; item блокируется здесь. Финальные item (``completed``/``failed``)
    не понижаются. Причина берётся из moderator comment change.
    """
    from .models import CatalogChange, CatalogProcessingItem

    item = CatalogProcessingItem.objects.select_for_update().filter(pk=change.item_id).first()
    if item is None or item.status in _FINAL_ITEM_STATUSES:
        return
    has_open = (
        CatalogChange.objects.filter(item=item, status__in=_NON_FINAL_CHANGE_STATUSES)
        .exclude(pk=change.pk)
        .exists()
    )
    if has_open:
        return
    detail = (change.comment or "") or (change.reason_detail or "")
    _mark_item_needs_review(item, "rejected", detail)


def _mark_item_needs_review(item, error_code: str, error_detail: str) -> None:
    """Переводит item в needs_review и фиксирует error_code/detail."""
    from .models import CatalogProcessingItemStatus

    if item.status not in _FINAL_ITEM_STATUSES:
        item.status = CatalogProcessingItemStatus.NEEDS_REVIEW
        item.error_code = error_code
        item.error_detail = error_detail[:255]
        item.save(update_fields=["status", "error_code", "error_detail"])


def apply_catalog_change(
    change_id: uuid.UUID,
    actor_id: int | None = None,
) -> CatalogDecisionResult:
    """Атомарно применить одобренное решение к каталогу.

    Flow:
    1. Проверка feature flag.
    2. Транзакция с блокировкой change/item/product/run.
    3. Проверка статуса change (idempotent: финальный статус возвращается как есть).
    4. Повторная проверка run/item/target и identity товара.
    5. Проверка operational baseline.
    6. Поиск option строго по slug.
    7. Применение через ``provenance.apply_sourced_value``.
       ``allow_equal_override=True`` разрешается, потому что change уже approved.
    8. Пересборка attrs_cache и верификация.
    9. Фиксация результата в change.
    10. При исключении — rollback каталога и failed audit только если change всё ещё approved.
    """
    from .models import (
        Attribute,
        AttributeOption,
        CatalogChange,
        CatalogChangeStatus,
        CatalogProcessingItem,
        CatalogProcessingItemStatus,
        CatalogProcessingRun,
        CatalogProcessingRunStatus,
        Product,
    )

    if not _feature_enabled():
        return CatalogDecisionResult("invalid", uuid.UUID(int=0), "feature_disabled")

    # --- Transactional apply ---
    item_id: int | None = None
    try:
        with transaction.atomic():
            # Status is checked only after locking the change. This makes repeated
            # and concurrent apply calls idempotent.
            locked_change = CatalogChange.objects.select_for_update().filter(pk=change_id).first()
            if locked_change is None:
                return CatalogDecisionResult("invalid", uuid.UUID(int=0), "change_not_found")
            if locked_change.status in _FINAL_CHANGE_STATUSES:
                return CatalogDecisionResult(
                    locked_change.status,
                    locked_change.id,
                    locked_change.reason_detail,
                )
            if locked_change.status != CatalogChangeStatus.APPROVED:
                return CatalogDecisionResult("invalid", locked_change.id, "change_not_approved")

            locked_item = (
                CatalogProcessingItem.objects.select_for_update()
                .filter(pk=locked_change.item_id)
                .first()
            )
            if locked_item is None:
                raise RuntimeError("locked_entity_missing")
            item_id = locked_item.pk

            locked_run = (
                CatalogProcessingRun.objects.select_for_update()
                .filter(pk=locked_item.run_id)
                .first()
            )
            if locked_run is None:
                raise RuntimeError("locked_run_missing")

            # Load and lock product explicitly. item.product FK nullable,
            # поэтому select_related + select_for_update недопустим в PostgreSQL.
            product_id = locked_item.product_id or locked_item.product_ref
            locked_product = Product.objects.select_for_update().filter(pk=product_id).first()
            if locked_product is None:
                locked_change.status = CatalogChangeStatus.INVALID
                locked_change.reason_code = "product_not_found"
                locked_change.reason_detail = "product was deleted after proposal"
                locked_change.save(update_fields=["status", "reason_code", "reason_detail"])
                locked_item.status = CatalogProcessingItemStatus.FAILED
                locked_item.error_code = "product_not_found"
                locked_item.save(update_fields=["status", "error_code"])
                return CatalogDecisionResult("invalid", locked_change.id, "product_not_found")

            # Re-check state machine under lock.
            if locked_run.status != CatalogProcessingRunStatus.RUNNING:
                locked_change.status = CatalogChangeStatus.INVALID
                locked_change.reason_code = "run_not_running"
                locked_change.reason_detail = "run is not in running state"
                locked_change.save(update_fields=["status", "reason_code", "reason_detail"])
                locked_item.status = CatalogProcessingItemStatus.FAILED
                locked_item.error_code = "run_not_running"
                locked_item.save(update_fields=["status", "error_code"])
                return CatalogDecisionResult("invalid", locked_change.id, "run_not_running")

            if locked_item.status not in _WORKABLE_ITEM_STATUSES:
                locked_change.status = CatalogChangeStatus.INVALID
                locked_change.reason_code = "item_not_workable"
                locked_change.reason_detail = f"item status is {locked_item.status}"
                locked_change.save(update_fields=["status", "reason_code", "reason_detail"])
                _mark_item_needs_review(
                    locked_item, "item_not_workable", locked_change.reason_detail
                )
                return CatalogDecisionResult("invalid", locked_change.id, "item_not_workable")

            if locked_item.product_ref != locked_product.pk:
                locked_change.status = CatalogChangeStatus.INVALID
                locked_change.reason_code = "product_identity_mismatch"
                locked_change.reason_detail = "item.product_ref does not match locked product"
                locked_change.save(update_fields=["status", "reason_code", "reason_detail"])
                locked_item.status = CatalogProcessingItemStatus.FAILED
                locked_item.error_code = "product_identity_mismatch"
                locked_item.save(update_fields=["status", "error_code"])
                return CatalogDecisionResult(
                    "invalid", locked_change.id, "product_identity_mismatch"
                )

            if locked_change.product_ref != locked_product.pk:
                locked_change.status = CatalogChangeStatus.INVALID
                locked_change.reason_code = "product_identity_mismatch"
                locked_change.reason_detail = "change.product_ref does not match locked product"
                locked_change.save(update_fields=["status", "reason_code", "reason_detail"])
                locked_item.status = CatalogProcessingItemStatus.FAILED
                locked_item.error_code = "product_identity_mismatch"
                locked_item.save(update_fields=["status", "error_code"])
                return CatalogDecisionResult(
                    "invalid", locked_change.id, "product_identity_mismatch"
                )

            # Baseline check (operational: slug/source/confidence).
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
            try:
                attr = Attribute.objects.get(slug=TOOL_TYPE_SLUG)
            except Attribute.DoesNotExist:
                locked_change.status = CatalogChangeStatus.INVALID
                locked_change.reason_code = "missing_attribute"
                locked_change.reason_detail = "tool_type attribute not found"
                locked_change.save(update_fields=["status", "reason_code", "reason_detail"])
                _mark_item_needs_review(
                    locked_item, "missing_attribute", locked_change.reason_detail
                )
                return CatalogDecisionResult("invalid", locked_change.id, "missing_attribute")
            option_slug = locked_change.proposed_value.get("option_slug")
            try:
                option = AttributeOption.objects.get(attribute=attr, slug=option_slug)
            except AttributeOption.DoesNotExist:
                locked_change.status = CatalogChangeStatus.INVALID
                locked_change.reason_code = "unknown_option"
                locked_change.reason_detail = f"unknown tool_type option: {option_slug}"
                locked_change.save(update_fields=["status", "reason_code", "reason_detail"])
                _mark_item_needs_review(locked_item, "unknown_option", locked_change.reason_detail)
                return CatalogDecisionResult("invalid", locked_change.id, "unknown_option")
            except AttributeOption.MultipleObjectsReturned:
                locked_change.status = CatalogChangeStatus.INVALID
                locked_change.reason_code = "option_slug_conflict"
                locked_change.reason_detail = f"multiple tool_type options for slug: {option_slug}"
                locked_change.save(update_fields=["status", "reason_code", "reason_detail"])
                _mark_item_needs_review(
                    locked_item, "option_slug_conflict", locked_change.reason_detail
                )
                return CatalogDecisionResult("invalid", locked_change.id, "option_slug_conflict")

            # Apply through provenance.
            # Change уже approved — equal-priority override разрешён.
            sourced_cmd = provenance.SourcedValueCommand(
                product_id=locked_product.pk,
                target_kind="attribute",
                attribute_slug=TOOL_TYPE_SLUG,
                value={"type": "option", "value": option_slug},
                source=locked_change.source,
                confidence=locked_change.confidence / 100.0,
                observed_value_hash=_provenance_value_hash(current_snapshot),
                observed_source=current_baseline["source"],
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
                locked_change.applied_by_id = actor_id
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
                    "applied_by_id",
                ]
            )
            locked_item.save(update_fields=["status", "finished_at"])
            return CatalogDecisionResult(status, locked_change.id, reason)

    except Exception as exc:  # noqa: BLE001 — техническая ошибка, каталог откатывается
        # Race-safe recovery: lock change and item, fail only if change is still approved.
        # If another apply already succeeded, return its final status.
        try:
            with transaction.atomic():
                failed_change = (
                    CatalogChange.objects.select_for_update().filter(pk=change_id).first()
                )
                if failed_change is None:
                    return CatalogDecisionResult("failed", change_id, str(exc)[:255])
                if failed_change.status in _FINAL_CHANGE_STATUSES:
                    return CatalogDecisionResult(
                        failed_change.status, failed_change.id, failed_change.reason_detail
                    )
                if failed_change.status != CatalogChangeStatus.APPROVED:
                    return CatalogDecisionResult(
                        "invalid", failed_change.id, f"change status is {failed_change.status}"
                    )

                failed_change.status = CatalogChangeStatus.FAILED
                failed_change.reason_code = "apply_exception"
                failed_change.reason_detail = str(exc)[:255]
                failed_change.save(update_fields=["status", "reason_code", "reason_detail"])

                failed_item = (
                    CatalogProcessingItem.objects.select_for_update().filter(pk=item_id).first()
                    if item_id is not None
                    else None
                )
                if failed_item is not None and failed_item.status not in _FINAL_ITEM_STATUSES:
                    failed_item.status = CatalogProcessingItemStatus.FAILED
                    failed_item.error_code = "apply_exception"
                    failed_item.error_detail = str(exc)[:255]
                    failed_item.finished_at = timezone.now()
                    failed_item.save(
                        update_fields=["status", "error_code", "error_detail", "finished_at"]
                    )
                return CatalogDecisionResult("failed", change_id, str(exc)[:255])
        except Exception as inner_exc:  # noqa: BLE001
            return CatalogDecisionResult("failed", change_id, str(inner_exc)[:255])


@dataclass(frozen=True)
class CatalogFinalizeResult:
    """Результат ``finalize_catalog_processing_run``."""

    status: str  # "completed" | "invalid"
    run_id: uuid.UUID
    reason: str = ""
    already_finalized: bool = False
    outcome: str = ""


# Item-статусы, при которых run ещё нельзя финализировать.
_NON_FINAL_ITEM_STATUSES = {"pending", "processing"}

# Change-статусы, при которых run ещё нельзя финализировать.
_NON_FINAL_CHANGE_STATUSES = {"proposed", "approved"}


def finalize_catalog_processing_run(run_id: uuid.UUID) -> CatalogFinalizeResult:
    """Финализация run: ``running`` -> ``completed``.

    Блокирует run/items/changes. Запрещена при ``pending``/``processing``
    items и ``proposed``/``approved`` changes — т.е. допускает смешанный
    итог вида ``completed`` + ``needs_review`` (+ ``failed``). Идемпотентна:
    повторный вызов по ``completed`` run возвращает
    ``already_finalized=True``. Product/PAV не изменяет.
    """
    from collections import Counter

    from .models import (
        CatalogChange,
        CatalogProcessingItem,
        CatalogProcessingRun,
        CatalogProcessingRunStatus,
    )

    if not _feature_enabled():
        return CatalogFinalizeResult("invalid", run_id, "feature_disabled")

    with transaction.atomic():
        run = CatalogProcessingRun.objects.select_for_update().filter(pk=run_id).first()
        if run is None:
            return CatalogFinalizeResult("invalid", run_id, "run_not_found")
        if run.status == CatalogProcessingRunStatus.COMPLETED:
            return CatalogFinalizeResult("completed", run.id, already_finalized=True)
        if run.status != CatalogProcessingRunStatus.RUNNING:
            return CatalogFinalizeResult("invalid", run.id, f"run_not_running:{run.status}")

        items = list(CatalogProcessingItem.objects.select_for_update().filter(run=run))
        if any(i.status in _NON_FINAL_ITEM_STATUSES for i in items):
            return CatalogFinalizeResult("invalid", run.id, "items_not_final")
        changes = list(CatalogChange.objects.select_for_update().filter(item__run=run))
        if any(c.status in _NON_FINAL_CHANGE_STATUSES for c in changes):
            return CatalogFinalizeResult("invalid", run.id, "changes_not_final")

        counts = Counter(i.status for i in items)
        if counts.get("failed"):
            outcome = "completed_with_errors"
        elif counts.get("needs_review"):
            outcome = "completed_with_review"
        else:
            outcome = "completed"

        now = timezone.now()
        stats = dict(run.stats or {})
        stats.update(
            {
                "outcome": outcome,
                "items_total": len(items),
                "items_completed": counts.get("completed", 0),
                "items_needs_review": counts.get("needs_review", 0),
                "items_failed": counts.get("failed", 0),
                "changes_total": len(changes),
                "changes_applied": sum(1 for c in changes if c.status == "applied"),
                "finalized_at": now.isoformat(),
            }
        )
        run.status = CatalogProcessingRunStatus.COMPLETED
        run.finished_at = now
        run.stats = stats
        run.save(update_fields=["status", "finished_at", "stats"])
        return CatalogFinalizeResult("completed", run.id, outcome=outcome)
