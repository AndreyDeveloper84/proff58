import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

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
def test_apply_uses_locked_item_product_not_product_ref(
    feature_enabled, reviewer, attr, drill_option
):
    """Если item.product_ref и item.product расходятся, apply отклоняет изменение."""
    p = _product(slug="p17")
    other = _product(slug="p17-other")
    run = _run()
    item = _item(run, p)
    item.product_ref = other.pk
    item.save(update_fields=["product_ref"])

    proposed = _propose(_cmd(item, drill_option.slug))
    _approve(proposed.change_id, reviewer)
    result = processing.apply_catalog_change(proposed.change_id)

    assert result.status == "invalid"
    assert result.reason == "product_identity_mismatch"
    assert not ProductAttributeValue.objects.filter(product=p).exists()
    assert not ProductAttributeValue.objects.filter(product=other).exists()
