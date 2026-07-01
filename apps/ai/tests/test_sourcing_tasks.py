import datetime as dt

import pytest

from apps.ai import services, tasks
from apps.ai.models import ContentFinding, ExternalCall, SourcingBudget, SourcingRun
from apps.catalog.models import Category, Product, ProductStatus


def _product(**kw):
    cat = Category.objects.filter(slug="perf").first() or Category.add_root(
        name="Перф", slug="perf"
    )
    return Product.objects.create(
        category=cat,
        name="",
        slug=kw.pop("slug", "x"),
        description="",
        original_name="Перфоратор Makita",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
        available_quantity=kw.pop("q", 5),
        **kw,
    )


@pytest.fixture
def budget(db):
    return SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=100)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(services, "_today", lambda: dt.date(2026, 6, 29))


@pytest.mark.django_db
def test_source_product_task_runs(budget, settings):
    settings.FEATURES = {
        **getattr(settings, "FEATURES", {}),
        "ai": True,
        "ai_sourcing": True,
        "external_integrations": True,
    }
    p = _product()
    tasks.source_product_task(p.pk, "task-run-1")
    assert ContentFinding.objects.filter(product_ref=p.pk).exists()


@pytest.mark.django_db
def test_task_skipped_when_flag_off(budget, settings):
    settings.FEATURES = {**getattr(settings, "FEATURES", {}), "ai_sourcing": False}
    p = _product()
    tasks.source_product_task(p.pk, "task-run-2")
    assert not SourcingRun.objects.filter(idempotency_key="task-run-2").exists()


class _RetryCalled(Exception):
    """Маркер: source_product_task вызвал self.retry (подмена в тесте)."""


@pytest.mark.django_db
def test_source_product_task_retries_on_transient(settings, monkeypatch):
    """#370: временный сбой source_content → self.retry, а не тихая потеря задачи."""
    settings.FEATURES = {
        **getattr(settings, "FEATURES", {}),
        "ai": True,
        "ai_sourcing": True,
        "external_integrations": True,
    }

    def _boom(*, product_id, idempotency_key):
        raise RuntimeError("временный сбой инфраструктуры")

    monkeypatch.setattr(services, "source_content", _boom)

    retried = {"n": 0}

    def _fake_retry(*args, **kwargs):
        retried["n"] += 1
        raise _RetryCalled

    monkeypatch.setattr(tasks.source_product_task, "retry", _fake_retry)

    try:
        tasks.source_product_task.apply(args=[1, "retry-key"])
    except Exception:  # noqa: BLE001 — ловим и маркер retry, и «сырое» исключение (RED)
        pass

    assert retried["n"] == 1  # без фикса self.retry не вызывается → RED (retried=0)


@pytest.mark.django_db
def test_mark_stale_sourcing_runs(budget):
    run = SourcingRun.objects.create(
        idempotency_key="stale", product_ref=1, status=SourcingRun.Status.RUNNING
    )
    call = ExternalCall.objects.create(run=run, adapter="web", status=ExternalCall.Status.RUNNING)
    SourcingRun.objects.filter(pk=run.pk).update(created_at=dt.datetime(2020, 1, 1, tzinfo=dt.UTC))
    tasks.mark_stale_sourcing_runs(older_than_minutes=60)
    call.refresh_from_db()
    assert call.status == ExternalCall.Status.UNKNOWN
