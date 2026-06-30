import datetime as dt

import pytest

from apps.ai import services
from apps.ai.admin import ContentFindingAdmin
from apps.ai.models import ContentFinding, SourcingBudget
from apps.catalog.models import Category, Product, ProductStatus


@pytest.fixture
def budget(db):
    return SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=100)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(services, "_today", lambda: dt.date(2026, 6, 29))


def _seed():
    cat = Category.objects.filter(slug="perf").first() or Category.add_root(
        name="Перф", slug="perf"
    )
    p = Product.objects.create(
        category=cat,
        name="",
        slug="x",
        description="",
        original_name="Перфоратор Makita",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
    )
    services.source_content(product_id=p.pk, idempotency_key="admin-run")
    return p


@pytest.mark.django_db
def test_queue_shows_only_pending(budget):
    _seed()
    admin = ContentFindingAdmin(ContentFinding, None)
    qs = admin.get_queryset(type("R", (), {"GET": {}})())
    assert qs.count() >= 1 and all(f.status == "pending" for f in qs)


@pytest.mark.django_db
def test_bulk_approve_applies_selected_evidence(budget):
    p = _seed()
    f = ContentFinding.objects.get(product_ref=p.pk, target_kind="description")
    f.selected_evidence = f.evidences.first()
    f.save()
    admin = ContentFindingAdmin(ContentFinding, None)
    admin.approve_selected(None, ContentFinding.objects.filter(pk=f.pk))
    p.refresh_from_db()
    f.refresh_from_db()
    assert f.status == "applied" and p.description.startswith("Перфоратор")
