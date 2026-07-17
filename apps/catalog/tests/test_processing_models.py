import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.catalog.models import (
    CatalogChange,
    CatalogChangeStatus,
    CatalogProcessingItem,
    CatalogProcessingItemStatus,
    CatalogProcessingRun,
    CatalogProcessingRunStatus,
    Category,
    Product,
    ProductStatus,
)


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


def _run(**kw):
    defaults = dict(
        kind="manual",
        mode="tool_type",
        status=CatalogProcessingRunStatus.RUNNING,
        idempotency_key="run-1",
    )
    defaults.update(kw)
    return CatalogProcessingRun.objects.create(**defaults)


def _item(run, product, **kw):
    defaults = dict(
        run=run,
        product=product,
        product_ref=product.pk,
        status=CatalogProcessingItemStatus.PENDING,
        input_hash="h1",
        baseline_hashes={"tool_type": "b1"},
        needed_targets=["tool_type"],
    )
    defaults.update(kw)
    return CatalogProcessingItem.objects.create(**defaults)


@pytest.mark.django_db
def test_run_idempotency_key_unique():
    _run(idempotency_key="k1")
    with pytest.raises(IntegrityError), transaction.atomic():
        _run(idempotency_key="k1")


@pytest.mark.django_db
def test_item_unique_within_run():
    run = _run()
    p = _product(slug="p1")
    _item(run, p)
    with pytest.raises(IntegrityError), transaction.atomic():
        _item(run, p, input_hash="h2")


@pytest.mark.django_db
def test_change_idempotency_key_unique():
    run = _run()
    p = _product(slug="p2")
    item = _item(run, p)
    CatalogChange.objects.create(
        item=item,
        product_ref=p.pk,
        target_kind="tool_type",
        status=CatalogChangeStatus.PROPOSED,
        idempotency_key="c1",
        source="manual",
        confidence=100,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CatalogChange.objects.create(
            item=item,
            product_ref=p.pk,
            target_kind="tool_type",
            status=CatalogChangeStatus.PROPOSED,
            idempotency_key="c1",
            source="manual",
            confidence=100,
        )


@pytest.mark.django_db
def test_change_confidence_out_of_range_blocked_by_db():
    run = _run()
    p = _product(slug="p3")
    item = _item(run, p)
    with pytest.raises(IntegrityError), transaction.atomic():
        CatalogChange.objects.create(
            item=item,
            product_ref=p.pk,
            target_kind="tool_type",
            status=CatalogChangeStatus.PROPOSED,
            idempotency_key="c2",
            source="manual",
            confidence=150,
        )


@pytest.mark.django_db
def test_change_confidence_negative_blocked_by_validator():
    change = CatalogChange(
        item_id=1,
        product_ref=1,
        target_kind="tool_type",
        status=CatalogChangeStatus.PROPOSED,
        idempotency_key="c3",
        source="manual",
        confidence=-1,
    )
    with pytest.raises(ValidationError):
        change.full_clean()


@pytest.mark.django_db
def test_approved_requires_reviewed_by_and_at():
    run = _run()
    p = _product(slug="p4")
    item = _item(run, p)
    with pytest.raises(IntegrityError), transaction.atomic():
        CatalogChange.objects.create(
            item=item,
            product_ref=p.pk,
            target_kind="tool_type",
            status=CatalogChangeStatus.APPROVED,
            idempotency_key="c4",
            source="manual",
            confidence=100,
        )


@pytest.mark.django_db
def test_rejected_requires_reviewed_by_and_at():
    run = _run()
    p = _product(slug="p5")
    item = _item(run, p)
    with pytest.raises(IntegrityError), transaction.atomic():
        CatalogChange.objects.create(
            item=item,
            product_ref=p.pk,
            target_kind="tool_type",
            status=CatalogChangeStatus.REJECTED,
            idempotency_key="c5",
            source="manual",
            confidence=100,
        )


@pytest.mark.django_db
def test_applied_requires_after_value_and_applied_at():
    run = _run()
    p = _product(slug="p6")
    item = _item(run, p)
    with pytest.raises(IntegrityError), transaction.atomic():
        CatalogChange.objects.create(
            item=item,
            product_ref=p.pk,
            target_kind="tool_type",
            status=CatalogChangeStatus.APPLIED,
            idempotency_key="c6",
            source="manual",
            confidence=100,
            reviewed_by_id=1,
            reviewed_at="2026-01-01T00:00:00Z",
        )


@pytest.mark.django_db
def test_run_protect_deletion_when_items_exist():
    run = _run()
    p = _product(slug="p7")
    _item(run, p)
    with pytest.raises(IntegrityError), transaction.atomic():
        run.delete()


@pytest.mark.django_db
def test_item_protect_deletion_when_changes_exist():
    run = _run()
    p = _product(slug="p8")
    item = _item(run, p)
    CatalogChange.objects.create(
        item=item,
        product_ref=p.pk,
        target_kind="tool_type",
        status=CatalogChangeStatus.PROPOSED,
        idempotency_key="c7",
        source="manual",
        confidence=100,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        item.delete()
