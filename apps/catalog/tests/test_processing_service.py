import uuid

import pytest

from apps.catalog import processing
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    CatalogChange,
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
from apps.catalog.processing import apply_catalog_decision, canonical_hash, tool_type_snapshot


def _category():
    return Category.add_root(name="Перф", slug="perf")


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


def _item(run, product):
    snapshot = tool_type_snapshot(product)
    baseline = {"tool_type": canonical_hash(processing._operational_baseline(snapshot))}
    return CatalogProcessingItem.objects.create(
        run=run,
        product=product,
        product_ref=product.pk,
        status=CatalogProcessingItemStatus.PENDING,
        input_snapshot=snapshot,
        input_hash=canonical_hash(snapshot),
        baseline_hashes=baseline,
        needed_targets=["tool_type"],
    )


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
    return processing.CatalogDecisionCommand(**defaults)


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
def test_empty_to_known_option_applied(attr, drill_option):
    p = _product(slug="p1")
    run = _run()
    item = _item(run, p)
    result = apply_catalog_decision(_cmd(item, drill_option.slug))

    p.refresh_from_db()
    assert result.status == "applied"
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    assert pav.value_option == drill_option
    assert pav.source == "manual"
    assert p.attrs_cache.get("tool_type") == drill_option.value


@pytest.mark.django_db
def test_weaker_existing_source_overwritten_by_stronger(attr, drill_option, perforator_option):
    p = _product(slug="p2")
    _set_tool_type(p, drill_option, source=Source.LLM, confidence=60)
    run = _run()
    item = _item(run, p)
    result = apply_catalog_decision(
        _cmd(item, perforator_option.slug, source="manual", confidence=100)
    )

    assert result.status == "applied"
    p.refresh_from_db()
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    assert pav.value_option == perforator_option
    assert pav.source == "manual"


@pytest.mark.django_db
def test_manual_existing_blocks_weaker_source(attr, drill_option, perforator_option):
    p = _product(slug="p3")
    _set_tool_type(p, drill_option, source=Source.MANUAL, confidence=100)
    run = _run()
    item = _item(run, p)
    result = apply_catalog_decision(_cmd(item, perforator_option.slug, source="web", confidence=90))

    assert result.status == "skipped"
    p.refresh_from_db()
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    assert pav.value_option == drill_option


@pytest.mark.django_db
def test_unknown_option_invalid(attr):
    p = _product(slug="p4")
    run = _run()
    item = _item(run, p)
    result = apply_catalog_decision(_cmd(item, "no-such-option"))

    assert result.status == "invalid"
    assert not ProductAttributeValue.objects.filter(product=p).exists()


@pytest.mark.django_db
def test_changed_baseline_returns_conflict(attr, drill_option, perforator_option):
    p = _product(slug="p5")
    run = _run()
    item = _item(run, p)
    # Baseline captured as empty, but we secretly set tool_type before apply.
    _set_tool_type(p, perforator_option, source=Source.MANUAL, confidence=100)
    result = apply_catalog_decision(_cmd(item, drill_option.slug))

    assert result.status == "conflict"
    p.refresh_from_db()
    assert (
        ProductAttributeValue.objects.get(product=p, attribute=attr).value_option
        == perforator_option
    )


@pytest.mark.django_db
def test_content_locked_blocks(attr, drill_option):
    p = _product(slug="p6", content_locked=True)
    run = _run()
    item = _item(run, p)
    result = apply_catalog_decision(_cmd(item, drill_option.slug))

    assert result.status == "skipped"
    assert not ProductAttributeValue.objects.filter(product=p).exists()


@pytest.mark.django_db
def test_missing_product_invalid(attr, drill_option):
    p = _product(slug="p7")
    run = _run()
    item = _item(run, p)
    p.delete()
    result = apply_catalog_decision(_cmd(item, drill_option.slug))

    assert result.status == "invalid"


@pytest.mark.django_db
def test_idempotency_returns_same_result(attr, drill_option):
    p = _product(slug="p8")
    run = _run()
    item = _item(run, p)
    key = str(uuid.uuid4())
    cmd = _cmd(item, drill_option.slug, idempotency_key=key)
    r1 = apply_catalog_decision(cmd)
    r2 = apply_catalog_decision(cmd)

    assert r1.status == r2.status == "applied"
    assert r1.change_id == r2.change_id
    assert CatalogChange.objects.filter(idempotency_key=key).count() == 1


@pytest.mark.django_db
def test_run_not_running_invalid(attr, drill_option):
    p = _product(slug="p9")
    run = _run(status=CatalogProcessingRunStatus.COMPLETED)
    item = _item(run, p)
    result = apply_catalog_decision(_cmd(item, drill_option.slug))

    assert result.status == "invalid"
    assert result.reason == "run_not_running"


@pytest.mark.django_db
def test_unrelated_fields_unchanged(attr, drill_option):
    p = _product(slug="p10", description="unchanged")
    run = _run()
    item = _item(run, p)
    apply_catalog_decision(_cmd(item, drill_option.slug))

    p.refresh_from_db()
    assert p.description == "unchanged"


@pytest.mark.django_db
def test_unsupported_target_kind_invalid():
    p = _product(slug="p11")
    run = _run()
    item = _item(run, p)
    cmd = processing.CatalogDecisionCommand(
        item_id=item.pk,
        target_kind="category",
        proposed_value={"slug": "x"},
        source="manual",
        confidence=100,
        idempotency_key=str(uuid.uuid4()),
    )
    result = apply_catalog_decision(cmd)

    assert result.status == "invalid"
    assert result.reason == "unsupported_target_kind"
