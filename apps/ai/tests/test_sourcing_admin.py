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


def _seed_named(slug, key):
    cat = Category.objects.filter(slug="perf").first() or Category.add_root(
        name="Перф", slug="perf"
    )
    p = Product.objects.create(
        category=cat,
        name="",
        slug=slug,
        description="",
        original_name="Перфоратор Makita " + slug,
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
    )
    services.source_content(product_id=p.pk, idempotency_key=key)
    return p


@pytest.mark.django_db
def test_bulk_approve_partial_success_on_error(budget, monkeypatch):
    """#367: сбой применения одной находки не должен прерывать весь bulk."""
    p1 = _seed_named("a", "run-a")
    p2 = _seed_named("b", "run-b")
    f1 = ContentFinding.objects.get(product_ref=p1.pk, target_kind="description")
    f2 = ContentFinding.objects.get(product_ref=p2.pk, target_kind="description")
    for f in (f1, f2):
        f.selected_evidence = f.evidences.first()
        f.save()

    calls = []

    def _boom(finding_id, evidence_id, reviewer_id):
        calls.append(finding_id)
        raise RuntimeError("сбой применения")

    monkeypatch.setattr(services, "approve_and_apply_finding", _boom)
    admin = ContentFindingAdmin(ContentFinding, None)
    admin.approve_selected(None, ContentFinding.objects.filter(pk__in=[f1.pk, f2.pk]))
    assert set(calls) == {f1.pk, f2.pk}


@pytest.mark.django_db
def test_admin_resolve_unknown_actions(budget):
    """#432: сверка UNKNOWN из админки — резерв снимается/списывается, не-unknown пропускается."""
    from unittest import mock

    from apps.ai.admin import ExternalCallAdmin
    from apps.ai.models import ExternalCall
    from apps.ai.sourcing.ports import SourceUncertain

    class _Boom:
        name = "web"

        def find(self, query, *, idempotency_key):
            raise SourceUncertain()

    cat = Category.objects.filter(slug="perf").first() or Category.add_root(
        name="Перф", slug="perf"
    )
    p = Product.objects.create(
        category=cat,
        name="",
        slug="adm-unk",
        description="",
        original_name="Перфоратор",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
    )
    services.source_content(product_id=p.pk, idempotency_key="adm-unk", sources=[_Boom()])
    call = ExternalCall.objects.get(run__idempotency_key="adm-unk")
    assert call.status == ExternalCall.Status.UNKNOWN

    admin_obj = ExternalCallAdmin(ExternalCall, admin_site=mock.Mock())
    admin_obj.message_user = mock.Mock()
    admin_obj.resolve_unknown_as_error(mock.Mock(), ExternalCall.objects.filter(pk=call.pk))

    call.refresh_from_db()
    assert call.status == ExternalCall.Status.ERROR
    assert SourcingBudget.objects.get(day=dt.date(2026, 6, 29)).reserved == 0

    # Повторный прогон action'а по уже разрешённому вызову — пропуск, без сдвига бюджета.
    admin_obj.resolve_unknown_as_paid(mock.Mock(), ExternalCall.objects.filter(pk=call.pk))
    assert SourcingBudget.objects.get(day=dt.date(2026, 6, 29)).spent == 0
