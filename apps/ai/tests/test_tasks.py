# apps/ai/tests/test_tasks.py
import pytest
from django.test import override_settings

from apps.ai.tasks import batch_enrich_task, enrich_product_task
from apps.catalog.models import Category, Product, ProductStatus


def _p(slug, *, stock, **kw):
    cat = Category.objects.first() or Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(category=cat, name="", slug=slug, description="",
                                  original_name="Перфоратор " + slug,
                                  status=ProductStatus.IMPORTED, is_active=False,
                                  price="1000", available_quantity=stock, **kw)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
@pytest.mark.django_db
def test_enrich_product_task_runs():
    p = _p("a", stock=5)
    enrich_product_task(p.pk)
    p.refresh_from_db()
    assert p.name


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
@pytest.mark.django_db
def test_batch_prioritizes_in_stock_and_limits():
    _p("instock", stock=10)
    _p("nostock", stock=0)
    n = batch_enrich_task(limit=1, only_empty=True)
    assert n == 1
    assert Product.objects.get(slug="instock").name != ""
    assert Product.objects.get(slug="nostock").name == ""
