import datetime as dt

import pytest

from apps.ai import services
from apps.ai.models import (
    ContentFinding,
    ExternalCall,
    FindingEvidence,
    SourcingBudget,
    SourcingRun,
)
from apps.catalog.models import Category, Product, ProductStatus


def _product(**kw):
    cat = Category.objects.filter(slug="perf").first() or Category.add_root(
        name="Перф", slug="perf"
    )
    return Product.objects.create(
        category=cat,
        name="",
        slug="x",
        description="",
        short_description="",
        original_name="Перфоратор Makita HR2470",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
        **kw,
    )


@pytest.fixture
def budget(db):
    return SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=100)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(services, "_today", lambda: dt.date(2026, 6, 29))


@pytest.mark.django_db
def test_source_content_collects_findings_without_touching_product(budget):
    p = _product()
    run = services.source_content(product_id=p.pk, idempotency_key="run-1")
    p.refresh_from_db()
    assert run.status in (SourcingRun.Status.OK, SourcingRun.Status.DEGRADED)
    assert ContentFinding.objects.filter(product_ref=p.pk).exists()
    assert FindingEvidence.objects.exists()
    assert p.description == "" and p.enrich_status == "pending"  # товар не изменён


@pytest.mark.django_db
def test_source_content_idempotent_no_double_call(budget):
    p = _product()
    services.source_content(product_id=p.pk, idempotency_key="run-2")
    services.source_content(product_id=p.pk, idempotency_key="run-2")  # повтор
    run = SourcingRun.objects.get(idempotency_key="run-2")
    assert ExternalCall.objects.filter(run=run, adapter="dummy", status="ok").count() == 1


@pytest.mark.django_db
def test_content_locked_blocks_sourcing(budget):
    p = _product(content_locked=True)
    run = services.source_content(product_id=p.pk, idempotency_key="run-3")
    assert run.status == SourcingRun.Status.DEGRADED
    assert not ContentFinding.objects.filter(product_ref=p.pk).exists()


@pytest.mark.django_db
def test_approve_applies_selected_evidence(budget):
    p = _product()
    services.source_content(product_id=p.pk, idempotency_key="run-4")
    f = ContentFinding.objects.get(product_ref=p.pk, target_kind="description")
    ev = f.evidences.first()
    result = services.approve_and_apply_finding(f.pk, ev.pk, reviewer_id=None)
    p.refresh_from_db()
    f.refresh_from_db()
    assert result.status == "applied"
    assert p.description.startswith("Перфоратор") and f.status == "applied"


@pytest.mark.django_db
def test_reapprove_is_noop(budget):
    p = _product()
    services.source_content(product_id=p.pk, idempotency_key="run-5")
    f = ContentFinding.objects.get(product_ref=p.pk, target_kind="description")
    ev = f.evidences.first()
    services.approve_and_apply_finding(f.pk, ev.pk, reviewer_id=None)
    again = services.approve_and_apply_finding(f.pk, ev.pk, reviewer_id=None)
    assert again.status == "skipped"
