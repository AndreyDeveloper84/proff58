import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.catalog import processing
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    CatalogChange,
    CatalogChangeStatus,
    CatalogProcessingItem,
    CatalogProcessingItemStatus,
    CatalogProcessingRun,
    CatalogProcessingRunStatus,
    Category,
    Product,
    ProductAttributeValue,
    ProductStatus,
    Source,
)
from apps.catalog.processing import canonical_hash, tool_type_snapshot


def _category():
    return Category.add_root(
        name=f"Перф-{uuid.uuid4().hex[:8]}", slug=f"perf-{uuid.uuid4().hex[:8]}"
    )


def _product(**kw):
    cat = _category()
    defaults = dict(
        category=cat,
        name="",
        slug="p",
        original_name="Перфоратор Makita HR2470",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
    )
    defaults.update(kw)
    return Product.objects.create(**defaults)


def _tool_type_attr():
    attr, _ = Attribute.objects.get_or_create(
        slug="tool_type",
        defaults={"name": "Тип инструмента", "attribute_type": AttributeType.SELECT},
    )
    return attr


def _option(attr, value, slug):
    return AttributeOption.objects.get_or_create(
        attribute=attr, value=value, defaults={"slug": slug}
    )[0]


def _set_tool_type(product, option, source=Source.MANUAL, confidence=100):
    attr = _tool_type_attr()
    pav, _ = ProductAttributeValue.objects.get_or_create(
        product=product, attribute=attr, defaults={"source": source, "confidence": confidence}
    )
    pav.value_option = option
    pav.source = source
    pav.confidence = confidence
    pav.save(update_fields=["value_option", "source", "confidence"])
    from apps.catalog.read_models import rebuild_attrs_cache

    rebuild_attrs_cache(product)


def _run(status=CatalogProcessingRunStatus.RUNNING):
    return CatalogProcessingRun.objects.create(
        kind="manual",
        mode="tool_type",
        status=status,
        idempotency_key=f"run-{CatalogProcessingRun.objects.count()}",
    )


def _item(run, product, **kw):
    snapshot = tool_type_snapshot(product)
    baseline = {"tool_type": canonical_hash(processing._operational_baseline(snapshot))}
    defaults = dict(
        run=run,
        product=product,
        product_ref=product.pk,
        status=CatalogProcessingItemStatus.PENDING,
        input_snapshot=snapshot,
        input_hash=canonical_hash(snapshot),
        baseline_hashes=baseline,
        needed_targets=["tool_type"],
    )
    defaults.update(kw)
    return CatalogProcessingItem.objects.create(**defaults)


def _cmd(item, option_slug, **kw):
    defaults = dict(
        item_id=item.pk,
        target_kind="tool_type",
        proposed_value={"option_slug": option_slug},
        source="manual",
        confidence=100,
        idempotency_key=str(uuid.uuid4()),
    )
    defaults.update(kw)
    return processing.CatalogChangeCommand(**defaults)


def _propose(cmd):
    return processing.create_catalog_change(cmd)


def _approve(change_id, reviewer):
    return processing.review_catalog_change(change_id, CatalogChangeStatus.APPROVED, reviewer.pk)


def _propose_approve_apply(item, option_slug, reviewer, **kw):
    cmd = _cmd(item, option_slug, **kw)
    proposed = _propose(cmd)
    assert proposed.status == "proposed"
    reviewed = _approve(proposed.change_id, reviewer)
    assert reviewed.status == "approved"
    return processing.apply_catalog_change(proposed.change_id)


@pytest.fixture
def feature_enabled():
    old = settings.FEATURES.get("catalog_processing")
    settings.FEATURES["catalog_processing"] = True
    yield
    settings.FEATURES["catalog_processing"] = old


@pytest.fixture
def reviewer():
    User = get_user_model()
    return User.objects.create(phone="+79990000001")


@pytest.fixture
def attr():
    return _tool_type_attr()


@pytest.fixture
def drill_option(attr):
    return _option(attr, "Дрели и шуруповёрты", "dreli-shurupoverty")


@pytest.fixture
def perforator_option(attr):
    return _option(attr, "Перфораторы", "perforatory")


@pytest.mark.django_db
def test_create_does_not_modify_product(feature_enabled, attr, drill_option):
    p = _product(slug="p1")
    run = _run()
    item = _item(run, p)
    result = _propose(_cmd(item, drill_option.slug))

    assert result.status == "proposed"
    assert not ProductAttributeValue.objects.filter(product=p).exists()
    change = CatalogChange.objects.get(pk=result.change_id)
    assert change.status == CatalogChangeStatus.PROPOSED


@pytest.mark.django_db
def test_empty_to_known_option_applied(feature_enabled, reviewer, attr, drill_option):
    p = _product(slug="p1")
    run = _run()
    item = _item(run, p)
    result = _propose_approve_apply(item, drill_option.slug, reviewer)

    p.refresh_from_db()
    assert result.status == "applied"
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    assert pav.value_option == drill_option
    assert pav.source == "manual"
    assert p.attrs_cache.get("tool_type") == drill_option.value


@pytest.mark.django_db
def test_weaker_existing_source_overwritten_by_stronger(
    feature_enabled, reviewer, attr, drill_option, perforator_option
):
    p = _product(slug="p2")
    _set_tool_type(p, drill_option, source=Source.LLM, confidence=60)
    run = _run()
    item = _item(run, p)
    result = _propose_approve_apply(
        item, perforator_option.slug, reviewer, source="manual", confidence=100
    )

    assert result.status == "applied"
    p.refresh_from_db()
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    assert pav.value_option == perforator_option
    assert pav.source == "manual"


@pytest.mark.django_db
def test_manual_existing_blocks_weaker_source(
    feature_enabled, reviewer, attr, drill_option, perforator_option
):
    p = _product(slug="p3")
    _set_tool_type(p, drill_option, source=Source.MANUAL, confidence=100)
    run = _run()
    item = _item(run, p)
    result = _propose_approve_apply(
        item, perforator_option.slug, reviewer, source="web", confidence=90
    )

    assert result.status == "skipped"
    p.refresh_from_db()
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    assert pav.value_option == drill_option


@pytest.mark.django_db
def test_equal_priority_requires_approval(
    feature_enabled, reviewer, attr, drill_option, perforator_option
):
    """Proposed web со слабым источником не применяется без одобрения модератора."""
    p = _product(slug="p3-equal")
    _set_tool_type(p, drill_option, source=Source.WEB, confidence=80)
    run = _run()
    item = _item(run, p)
    cmd = _cmd(item, perforator_option.slug, source="web", confidence=90)
    proposed = _propose(cmd)
    assert proposed.status == "proposed"

    # Даже approved change с равным приоритетом применяется только потому,
    # что модератор дал approve (allow_equal_override=True).
    reviewed = _approve(proposed.change_id, reviewer)
    assert reviewed.status == "approved"
    result = processing.apply_catalog_change(proposed.change_id)
    assert result.status == "applied"


@pytest.mark.django_db
def test_unapproved_change_cannot_be_applied(feature_enabled, attr, drill_option):
    p = _product(slug="p4")
    run = _run()
    item = _item(run, p)
    proposed = _propose(_cmd(item, drill_option.slug, source="web"))
    assert proposed.status == "proposed"

    result = processing.apply_catalog_change(proposed.change_id)
    assert result.status == "invalid"
    assert result.reason == "change_not_approved"
    assert not ProductAttributeValue.objects.filter(product=p).exists()


@pytest.mark.django_db
def test_unknown_option_invalid(feature_enabled, reviewer, attr):
    p = _product(slug="p5")
    run = _run()
    item = _item(run, p)
    proposed = _propose(_cmd(item, "no-such-option"))
    assert proposed.status == "proposed"

    reviewed = _approve(proposed.change_id, reviewer)
    assert reviewed.status == "approved"
    result = processing.apply_catalog_change(proposed.change_id)

    assert result.status == "invalid"
    assert not ProductAttributeValue.objects.filter(product=p).exists()


@pytest.mark.django_db
def test_changed_baseline_returns_conflict(
    feature_enabled, reviewer, attr, drill_option, perforator_option
):
    p = _product(slug="p6")
    run = _run()
    item = _item(run, p)
    # Baseline captured as empty, but we secretly set tool_type before apply.
    proposed = _propose(_cmd(item, drill_option.slug))
    _set_tool_type(p, perforator_option, source=Source.MANUAL, confidence=100)
    _approve(proposed.change_id, reviewer)
    result = processing.apply_catalog_change(proposed.change_id)

    assert result.status == "conflict"
    p.refresh_from_db()
    assert (
        ProductAttributeValue.objects.get(product=p, attribute=attr).value_option
        == perforator_option
    )


@pytest.mark.django_db
def test_content_locked_blocks(feature_enabled, reviewer, attr, drill_option):
    p = _product(slug="p7", content_locked=True)
    run = _run()
    item = _item(run, p)
    result = _propose_approve_apply(item, drill_option.slug, reviewer)

    assert result.status == "skipped"
    assert not ProductAttributeValue.objects.filter(product=p).exists()


@pytest.mark.django_db
def test_missing_product_invalid(feature_enabled, reviewer, attr, drill_option):
    p = _product(slug="p8")
    run = _run()
    item = _item(run, p)
    proposed = _propose(_cmd(item, drill_option.slug))
    p.delete()
    _approve(proposed.change_id, reviewer)
    result = processing.apply_catalog_change(proposed.change_id)

    assert result.status == "invalid"


@pytest.mark.django_db
def test_idempotency_returns_same_result(feature_enabled, attr, drill_option):
    p = _product(slug="p9")
    run = _run()
    item = _item(run, p)
    key = str(uuid.uuid4())
    cmd = _cmd(item, drill_option.slug, idempotency_key=key)
    r1 = _propose(cmd)
    r2 = _propose(cmd)

    assert r1.status == r2.status == "proposed"
    assert r1.change_id == r2.change_id
    assert CatalogChange.objects.filter(idempotency_key=key).count() == 1


@pytest.mark.django_db
def test_run_not_running_blocks_create(feature_enabled, attr, drill_option):
    p = _product(slug="p10")
    run = _run(status=CatalogProcessingRunStatus.COMPLETED)
    item = _item(run, p)
    result = _propose(_cmd(item, drill_option.slug))

    assert result.status == "invalid"
    assert result.reason == "run_not_running"


@pytest.mark.django_db
def test_unrelated_fields_unchanged(feature_enabled, reviewer, attr, drill_option):
    p = _product(slug="p11", description="unchanged")
    run = _run()
    item = _item(run, p)
    _propose_approve_apply(item, drill_option.slug, reviewer)

    p.refresh_from_db()
    assert p.description == "unchanged"


@pytest.mark.django_db
def test_unsupported_target_kind_invalid(feature_enabled):
    p = _product(slug="p12")
    run = _run()
    item = _item(run, p)
    cmd = processing.CatalogChangeCommand(
        item_id=item.pk,
        target_kind="category",
        proposed_value={"slug": "x"},
        source="manual",
        confidence=100,
        idempotency_key=str(uuid.uuid4()),
    )
    result = _propose(cmd)

    assert result.status == "invalid"
    assert result.reason == "unsupported_target_kind"


@pytest.mark.django_db
def test_invalid_source_rejected(feature_enabled, attr, drill_option):
    p = _product(slug="p13")
    run = _run()
    item = _item(run, p)
    cmd = _cmd(item, drill_option.slug, source="not-a-source")
    result = _propose(cmd)

    assert result.status == "invalid"
    assert result.reason == "invalid_source"


@pytest.mark.django_db
def test_rules_source_is_valid(feature_enabled, reviewer, attr, drill_option):
    p = _product(slug="p14")
    run = _run()
    item = _item(run, p)
    result = _propose_approve_apply(item, drill_option.slug, reviewer, source="rules")

    assert result.status == "applied"
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    assert pav.source == "rules"


@pytest.mark.django_db
def test_manual_existing_blocks_approved_rules(
    feature_enabled, reviewer, attr, drill_option, perforator_option
):
    p = _product(slug="p14-manual")
    _set_tool_type(p, drill_option, source=Source.MANUAL, confidence=100)
    run = _run()
    item = _item(run, p)

    result = _propose_approve_apply(
        item, perforator_option.slug, reviewer, source="rules", confidence=100
    )

    assert result.status == "skipped"
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    assert pav.value_option == drill_option
    assert pav.source == Source.MANUAL


@pytest.mark.django_db
def test_feature_flag_disabled_blocks_create(feature_enabled, attr, drill_option):
    settings.FEATURES["catalog_processing"] = False
    p = _product(slug="p15")
    run = _run()
    item = _item(run, p)
    result = _propose(_cmd(item, drill_option.slug))

    assert result.status == "invalid"
    assert result.reason == "feature_disabled"


@pytest.mark.django_db
def test_target_not_needed_rejected(feature_enabled, attr, drill_option):
    p = _product(slug="p16")
    run = _run()
    item = _item(run, p, needed_targets=[])
    result = _propose(_cmd(item, drill_option.slug))

    assert result.status == "invalid"
    assert result.reason == "target_not_needed"


@pytest.mark.django_db
def test_create_rejects_item_product_identity_mismatch(feature_enabled, attr, drill_option):
    """Identity mismatch должен отклоняться до создания change и snapshot."""
    p = _product(slug="p17")
    other = _product(slug="p17-other")
    run = _run()
    item = _item(run, p)
    item.product_ref = other.pk
    item.save(update_fields=["product_ref"])

    result = _propose(_cmd(item, drill_option.slug))

    assert result.status == "invalid"
    assert result.reason == "product_identity_mismatch"
    assert result.change_id == uuid.UUID(int=0)
    assert CatalogChange.objects.filter(item=item).count() == 0
    assert not ProductAttributeValue.objects.filter(product=p).exists()
    assert not ProductAttributeValue.objects.filter(product=other).exists()


@pytest.mark.django_db
def test_validate_catalog_change(feature_enabled, reviewer, attr, drill_option):
    p = _product(slug="p17-validate")
    run = _run()
    item = _item(run, p)
    proposed = _propose(_cmd(item, drill_option.slug))

    assert processing.validate_catalog_change(proposed.change_id).valid is True

    _approve(proposed.change_id, reviewer)
    assert processing.validate_catalog_change(proposed.change_id).valid is True

    result = processing.apply_catalog_change(proposed.change_id)
    assert result.status == "applied"
    validated = processing.validate_catalog_change(proposed.change_id)
    assert validated.valid is False
    assert validated.reason == "change_final"


@pytest.mark.django_db
def test_validate_detects_baseline_change(
    feature_enabled, reviewer, attr, drill_option, perforator_option
):
    p = _product(slug="p17-validate-base")
    run = _run()
    item = _item(run, p)
    proposed = _propose(_cmd(item, drill_option.slug))
    _set_tool_type(p, perforator_option, source=Source.MANUAL, confidence=100)

    validated = processing.validate_catalog_change(proposed.change_id)
    assert validated.valid is False
    assert validated.reason == "baseline_changed"


@pytest.mark.django_db
def test_validate_detects_unknown_option(feature_enabled, attr):
    p = _product(slug="p17-validate-opt")
    run = _run()
    item = _item(run, p)
    proposed = _propose(_cmd(item, "no-such-option"))

    validated = processing.validate_catalog_change(proposed.change_id)
    assert validated.valid is False
    assert validated.reason == "unknown_option"


@pytest.mark.parametrize("bad_source", ["import_1c", "regex", "keyword", "inferred", "marketplace"])
@pytest.mark.django_db
def test_source_allowlist_rejects_global_sources(feature_enabled, attr, drill_option, bad_source):
    p = _product(slug=f"p17-source-{bad_source}")
    run = _run()
    item = _item(run, p)
    result = _propose(_cmd(item, drill_option.slug, source=bad_source))

    assert result.status == "invalid"
    assert result.reason == "invalid_source"


# --- finalize_catalog_processing_run ---


def _finish_item(item, status):
    item.status = status
    item.save(update_fields=["status"])


@pytest.mark.django_db
def test_finalize_success_mixed_completed_and_needs_review(feature_enabled):
    p1 = _product(slug="fin-1")
    p2 = _product(slug="fin-2")
    run = _run()
    item1 = _item(run, p1)
    item2 = _item(run, p2)
    _finish_item(item1, CatalogProcessingItemStatus.COMPLETED)
    _finish_item(item2, CatalogProcessingItemStatus.NEEDS_REVIEW)

    result = processing.finalize_catalog_processing_run(run.id)

    assert result.status == "completed"
    assert result.outcome == "completed_with_review"
    assert not result.already_finalized
    run.refresh_from_db()
    assert run.status == CatalogProcessingRunStatus.COMPLETED
    assert run.finished_at is not None
    assert run.stats["outcome"] == "completed_with_review"
    assert run.stats["items_total"] == 2
    assert run.stats["items_completed"] == 1
    assert run.stats["items_needs_review"] == 1
    assert run.stats["items_failed"] == 0
    assert run.stats["changes_total"] == 0
    assert run.stats["changes_applied"] == 0


@pytest.mark.django_db
def test_finalize_success_all_completed(feature_enabled):
    p = _product(slug="fin-all")
    run = _run()
    _finish_item(_item(run, p), CatalogProcessingItemStatus.COMPLETED)

    result = processing.finalize_catalog_processing_run(run.id)

    assert result.status == "completed"
    assert result.outcome == "completed"


@pytest.mark.django_db
def test_finalize_rejects_pending_item(feature_enabled):
    p = _product(slug="fin-pending")
    run = _run()
    _item(run, p)  # pending

    result = processing.finalize_catalog_processing_run(run.id)

    assert result.status == "invalid"
    assert result.reason == "items_not_final"
    run.refresh_from_db()
    assert run.status == CatalogProcessingRunStatus.RUNNING
    assert run.finished_at is None


@pytest.mark.django_db
def test_finalize_rejects_processing_item(feature_enabled):
    p = _product(slug="fin-processing")
    run = _run()
    _finish_item(_item(run, p), CatalogProcessingItemStatus.PROCESSING)

    result = processing.finalize_catalog_processing_run(run.id)

    assert result.status == "invalid"
    assert result.reason == "items_not_final"


@pytest.mark.django_db
def test_finalize_rejects_proposed_change(feature_enabled, attr, drill_option):
    p = _product(slug="fin-proposed")
    run = _run()
    item = _item(run, p)
    proposed = _propose(_cmd(item, drill_option.slug))
    assert proposed.status == "proposed"
    # change proposed, но item уже в финальном статусе — guard именно по changes.
    _finish_item(item, CatalogProcessingItemStatus.COMPLETED)

    result = processing.finalize_catalog_processing_run(run.id)

    assert result.status == "invalid"
    assert result.reason == "changes_not_final"
    run.refresh_from_db()
    assert run.status == CatalogProcessingRunStatus.RUNNING


@pytest.mark.django_db
def test_finalize_rejects_approved_change(feature_enabled, attr, drill_option, reviewer):
    p = _product(slug="fin-approved")
    run = _run()
    item = _item(run, p)
    proposed = _propose(_cmd(item, drill_option.slug))
    reviewed = _approve(proposed.change_id, reviewer)
    assert reviewed.status == "approved"
    # change approved, но item уже в финальном статусе — guard именно по changes.
    _finish_item(item, CatalogProcessingItemStatus.COMPLETED)

    result = processing.finalize_catalog_processing_run(run.id)

    assert result.status == "invalid"
    assert result.reason == "changes_not_final"


@pytest.mark.django_db
def test_finalize_idempotent_second_call(feature_enabled):
    p = _product(slug="fin-idem")
    run = _run()
    _finish_item(_item(run, p), CatalogProcessingItemStatus.COMPLETED)

    first = processing.finalize_catalog_processing_run(run.id)
    run.refresh_from_db()
    finished_at = run.finished_at
    second = processing.finalize_catalog_processing_run(run.id)

    assert first.status == "completed" and not first.already_finalized
    assert second.status == "completed" and second.already_finalized
    run.refresh_from_db()
    assert run.finished_at == finished_at


@pytest.mark.django_db
def test_finalize_rejects_non_running_run(feature_enabled):
    run = _run(status=CatalogProcessingRunStatus.DRAFT)

    result = processing.finalize_catalog_processing_run(run.id)

    assert result.status == "invalid"
    assert result.reason == "run_not_running:draft"


@pytest.mark.django_db
def test_finalize_unknown_run(feature_enabled):
    result = processing.finalize_catalog_processing_run(uuid.uuid4())

    assert result.status == "invalid"
    assert result.reason == "run_not_found"


@pytest.mark.django_db
def test_finalize_feature_disabled():
    result = processing.finalize_catalog_processing_run(uuid.uuid4())

    assert result.status == "invalid"
    assert result.reason == "feature_disabled"


@pytest.mark.django_db
def test_finalize_does_not_touch_product(feature_enabled, attr, drill_option, reviewer):
    p = _product(slug="fin-no-touch")
    run = _run()
    item = _item(run, p)
    _propose_approve_apply(item, drill_option.slug, reviewer)
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.COMPLETED
    pav_count_before = ProductAttributeValue.objects.count()
    cache_before = dict(Product.objects.get(pk=p.pk).attrs_cache or {})

    result = processing.finalize_catalog_processing_run(run.id)

    assert result.status == "completed"
    assert ProductAttributeValue.objects.count() == pav_count_before
    assert (Product.objects.get(pk=p.pk).attrs_cache or {}) == cache_before


# --- review_catalog_change: rejected ---


def _reject(change_id, reviewer, comment=""):
    return processing.review_catalog_change(
        change_id, CatalogChangeStatus.REJECTED, reviewer.pk, comment
    )


@pytest.mark.django_db
def test_reject_sole_proposal_closes_item_needs_review(
    feature_enabled, attr, drill_option, reviewer
):
    p = _product(slug="rej-sole")
    run = _run()
    item = _item(run, p, status=CatalogProcessingItemStatus.PROCESSING)
    proposed = _propose(_cmd(item, drill_option.slug))
    assert proposed.status == "proposed"

    result = _reject(proposed.change_id, reviewer, "не тот тип инструмента")

    assert result.status == "rejected"
    change = CatalogChange.objects.get(pk=proposed.change_id)
    assert change.status == CatalogChangeStatus.REJECTED
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.NEEDS_REVIEW
    assert item.error_code == "rejected"
    assert item.error_detail == "не тот тип инструмента"


@pytest.mark.django_db
def test_reject_preserves_moderator_audit_and_comment(
    feature_enabled, attr, drill_option, reviewer
):
    p = _product(slug="rej-audit")
    run = _run()
    item = _item(run, p, status=CatalogProcessingItemStatus.PROCESSING)
    proposed = _propose(_cmd(item, drill_option.slug))
    long_comment = "комментарий модератора " + "x" * 300  # <= 512, но > 255

    result = _reject(proposed.change_id, reviewer, long_comment)

    assert result.status == "rejected"
    change = CatalogChange.objects.get(pk=proposed.change_id)
    assert change.reviewed_by_id == reviewer.pk
    assert change.reviewed_at is not None
    assert change.comment == long_comment
    item.refresh_from_db()
    assert item.error_code == "rejected"
    assert item.error_detail == long_comment[:255]


@pytest.mark.django_db
def test_reject_does_not_touch_product(feature_enabled, attr, drill_option, reviewer):
    p = _product(slug="rej-no-touch")
    run = _run()
    item = _item(run, p, status=CatalogProcessingItemStatus.PROCESSING)
    proposed = _propose(_cmd(item, drill_option.slug))
    pav_count_before = ProductAttributeValue.objects.count()
    cache_before = dict(Product.objects.get(pk=p.pk).attrs_cache or {})

    result = _reject(proposed.change_id, reviewer, "отклонено модератором")

    assert result.status == "rejected"
    assert ProductAttributeValue.objects.count() == pav_count_before
    assert (Product.objects.get(pk=p.pk).attrs_cache or {}) == cache_before


@pytest.mark.django_db
def test_reject_repeated_is_safe_noop(feature_enabled, attr, drill_option, reviewer):
    p = _product(slug="rej-noop")
    run = _run()
    item = _item(run, p, status=CatalogProcessingItemStatus.PROCESSING)
    proposed = _propose(_cmd(item, drill_option.slug))
    first = _reject(proposed.change_id, reviewer, "первое решение")
    assert first.status == "rejected"
    change = CatalogChange.objects.get(pk=proposed.change_id)
    reviewed_at = change.reviewed_at

    second = _reject(proposed.change_id, reviewer, "повторный reject")

    assert second.status == "rejected"
    change.refresh_from_db()
    assert change.reviewed_at == reviewed_at
    assert change.comment == "первое решение"
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.NEEDS_REVIEW
    assert item.error_code == "rejected"


@pytest.mark.django_db
def test_approve_after_reject_does_not_change_decision(
    feature_enabled, attr, drill_option, reviewer
):
    p = _product(slug="rej-then-approve")
    run = _run()
    item = _item(run, p, status=CatalogProcessingItemStatus.PROCESSING)
    proposed = _propose(_cmd(item, drill_option.slug))
    rejected = _reject(proposed.change_id, reviewer, "финальный reject")
    assert rejected.status == "rejected"
    change = CatalogChange.objects.get(pk=proposed.change_id)
    reviewed_at = change.reviewed_at

    second = _approve(proposed.change_id, reviewer)

    assert second.status == "rejected"
    change.refresh_from_db()
    assert change.status == CatalogChangeStatus.REJECTED
    assert change.reviewed_at == reviewed_at
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.NEEDS_REVIEW


@pytest.mark.django_db
def test_approve_path_leaves_item_processing(feature_enabled, attr, drill_option, reviewer):
    p = _product(slug="approve-path")
    run = _run()
    item = _item(run, p, status=CatalogProcessingItemStatus.PROCESSING)
    proposed = _propose(_cmd(item, drill_option.slug))

    reviewed = _approve(proposed.change_id, reviewer)

    assert reviewed.status == "approved"
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.PROCESSING
    assert item.error_code == ""


@pytest.mark.django_db
def test_reject_one_of_multiple_changes_leaves_item_processing(
    feature_enabled, attr, drill_option, perforator_option, reviewer
):
    p = _product(slug="rej-multi")
    run = _run()
    item = _item(run, p, status=CatalogProcessingItemStatus.PROCESSING)
    first = _propose(_cmd(item, drill_option.slug))
    second = _propose(_cmd(item, perforator_option.slug))
    assert first.status == second.status == "proposed"

    rejected = _reject(first.change_id, reviewer, "первый отклонён")

    assert rejected.status == "rejected"
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.PROCESSING
    assert item.error_code == ""


@pytest.mark.django_db
def test_reject_last_open_change_closes_item(
    feature_enabled, attr, drill_option, perforator_option, reviewer
):
    p = _product(slug="rej-last")
    run = _run()
    item = _item(run, p, status=CatalogProcessingItemStatus.PROCESSING)
    first = _propose(_cmd(item, drill_option.slug))
    second = _propose(_cmd(item, perforator_option.slug))
    assert _reject(first.change_id, reviewer, "первый отклонён").status == "rejected"
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.PROCESSING

    rejected = _reject(second.change_id, reviewer, "второй отклонён")

    assert rejected.status == "rejected"
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.NEEDS_REVIEW
    assert item.error_code == "rejected"
    assert item.error_detail == "второй отклонён"


@pytest.mark.django_db
def test_reject_does_not_downgrade_completed_item(feature_enabled, attr, drill_option, reviewer):
    p = _product(slug="rej-completed")
    run = _run()
    item = _item(run, p, status=CatalogProcessingItemStatus.PROCESSING)
    proposed = _propose(_cmd(item, drill_option.slug))
    _finish_item(item, CatalogProcessingItemStatus.COMPLETED)

    rejected = _reject(proposed.change_id, reviewer, "поздний reject")

    assert rejected.status == "rejected"
    change = CatalogChange.objects.get(pk=proposed.change_id)
    assert change.status == CatalogChangeStatus.REJECTED
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.COMPLETED


@pytest.mark.django_db
def test_reject_replay_heals_stranded_processing_item(
    feature_enabled, attr, drill_option, reviewer
):
    """Legacy-состояние: change уже rejected, item застрял в processing."""
    p = _product(slug="rej-heal")
    run = _run()
    item = _item(run, p, status=CatalogProcessingItemStatus.PROCESSING)
    proposed = _propose(_cmd(item, drill_option.slug))
    CatalogChange.objects.filter(pk=proposed.change_id).update(
        status=CatalogChangeStatus.REJECTED,
        reviewed_by_id=reviewer.pk,
        reviewed_at=timezone.now(),
        comment="legacy reject",
    )
    change = CatalogChange.objects.get(pk=proposed.change_id)
    reviewed_at = change.reviewed_at

    replay = _reject(proposed.change_id, reviewer, "replay")

    assert replay.status == "rejected"
    change.refresh_from_db()
    assert change.reviewed_at == reviewed_at
    assert change.comment == "legacy reject"
    item.refresh_from_db()
    assert item.status == CatalogProcessingItemStatus.NEEDS_REVIEW
    assert item.error_code == "rejected"
    assert item.error_detail == "legacy reject"


@pytest.mark.django_db
def test_finalize_after_reject_mixed_run(feature_enabled, attr, drill_option, reviewer):
    p1 = _product(slug="rej-fin-1")
    p2 = _product(slug="rej-fin-2")
    run = _run()
    item1 = _item(run, p1, status=CatalogProcessingItemStatus.PROCESSING)
    item2 = _item(run, p2, status=CatalogProcessingItemStatus.PROCESSING)
    _finish_item(item1, CatalogProcessingItemStatus.COMPLETED)
    proposed = _propose(_cmd(item2, drill_option.slug))
    assert _reject(proposed.change_id, reviewer, "отклонено").status == "rejected"

    result = processing.finalize_catalog_processing_run(run.id)

    assert result.status == "completed"
    assert result.outcome == "completed_with_review"
    run.refresh_from_db()
    assert run.status == CatalogProcessingRunStatus.COMPLETED
    assert run.stats["items_completed"] == 1
    assert run.stats["items_needs_review"] == 1
    assert run.stats["changes_total"] == 1
    assert run.stats["changes_applied"] == 0
