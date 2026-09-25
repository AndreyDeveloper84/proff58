# apps/ai/tests/test_commands.py
import pytest
from django.core.management import call_command

from apps.catalog.models import Category, Product, ProductStatus


def _p(slug, **kw):
    cat = Category.objects.first() or Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(
        category=cat,
        name="",
        slug=slug,
        description="",
        original_name="Перфоратор " + slug,
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
        **kw,
    )


@pytest.mark.django_db
def test_enrich_product_by_id():
    p = _p("a")
    call_command("enrich_product", "--id", str(p.pk))
    p.refresh_from_db()
    assert p.name


@pytest.mark.django_db
def test_enrich_catalog_dry_run_writes_nothing():
    _p("a", available_quantity=5)
    call_command("enrich_catalog", "--all", "--limit", "5", "--dry-run")
    assert Product.objects.get(slug="a").name == ""


@pytest.mark.django_db
def test_enrich_report_runs(capsys):
    _p("a")
    call_command("enrich_report")
    out = capsys.readouterr().out
    assert "Ожидает" in out
