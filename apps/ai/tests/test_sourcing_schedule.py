import datetime as dt

import pytest

from apps.ai import services, tasks
from apps.ai.models import ContentFinding, SourcingBudget
from apps.catalog.models import Category, Product, ProductStatus


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(services, "_today", lambda: dt.date(2026, 6, 29))


def _flags(settings):
    settings.FEATURES = {
        **getattr(settings, "FEATURES", {}),
        "ai": True,
        "ai_sourcing": True,
        "external_integrations": True,
    }


def _imported_product(slug="hr2470"):
    cat = Category.objects.filter(slug="perf").first() or Category.add_root(
        name="Перф", slug="perf"
    )
    return Product.objects.create(
        category=cat,
        name="",
        slug=slug,
        description="",
        original_name="Перфоратор Makita " + slug,
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
        available_quantity=5,
    )


def test_beat_schedule_has_nightly_sourcing():
    from config.celery import app

    entry = app.conf.beat_schedule.get("source-catalog-nightly")
    assert entry is not None
    assert entry["task"] == "apps.ai.tasks.batch_source_task"


@pytest.mark.django_db
def test_nightly_batch_sources_pending_1c_product(settings):
    _flags(settings)
    SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=100)
    _imported_product()
    n = tasks.batch_source_task()  # EAGER → source_product_task выполняется инлайн
    assert n >= 1
    assert ContentFinding.objects.exists()


@pytest.mark.django_db
def test_nightly_batch_safe_without_budget(settings):
    _flags(settings)  # дневной лимит НЕ задан → daily_cap=0
    _imported_product(slug="x")
    tasks.batch_source_task()
    assert not ContentFinding.objects.exists()  # резерв > 0 при cap=0 → degraded, трат нет
