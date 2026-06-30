import datetime as dt

import pytest
from django.core.management import call_command

from apps.ai import services
from apps.ai.models import ContentFinding, SourcingBudget
from apps.catalog.models import Category, Product, ProductStatus


@pytest.fixture
def budget(db):
    return SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=100)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(services, "_today", lambda: dt.date(2026, 6, 29))


def _p(slug, **kw):
    cat = Category.objects.filter(slug="perf").first() or Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(category=cat, name="", slug=slug, description="",
        original_name="Перфоратор " + slug, status=ProductStatus.IMPORTED,
        is_active=False, price="1000", **kw)


@pytest.mark.django_db
def test_source_product_by_id(budget):
    p = _p("a")
    call_command("source_product", "--id", str(p.pk))
    assert ContentFinding.objects.filter(product_ref=p.pk).exists()


@pytest.mark.django_db
def test_source_product_dry_run_no_findings(budget):
    p = _p("b")
    call_command("source_product", "--id", str(p.pk), "--dry-run")
    assert not ContentFinding.objects.filter(product_ref=p.pk).exists()


@pytest.mark.django_db
def test_source_report_runs(budget, capsys):
    _p("c")
    call_command("source_report")
    assert "Находки" in capsys.readouterr().out
