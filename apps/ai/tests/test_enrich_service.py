# apps/ai/tests/test_enrich_service.py
import pytest

from apps.ai.models import AiCallLog
from apps.ai.services import enrich
from apps.catalog.models import Category, Product, ProductStatus


def _product(**kw):
    cat = Category.objects.first() or Category.add_root(name="Перфораторы", slug="perf")
    data = dict(category=cat, name="", slug="p1", description="",
                original_name="Перфоратор HR2470 Makita 780Вт",
                status=ProductStatus.IMPORTED, is_active=False, price="1000")
    data.update(kw)
    return Product.objects.create(**data)


@pytest.mark.django_db
def test_enrich_fills_card_and_logs():
    p = _product()
    res = enrich(product_id=p.pk)
    assert res.source == "llm"
    p.refresh_from_db()
    assert p.name and p.description
    log = AiCallLog.objects.get(entity_ref=p.pk, capability=AiCallLog.Capability.ENRICH)
    assert log.status == AiCallLog.Status.OK


@pytest.mark.django_db
def test_enrich_respects_content_locked():
    p = _product(slug="p2", content_locked=True)
    res = enrich(product_id=p.pk)
    p.refresh_from_db()
    assert p.name == "" and res.source == "fallback"
    log = AiCallLog.objects.get(entity_ref=p.pk)
    assert log.status == AiCallLog.Status.FALLBACK and log.reason == "content_locked"


@pytest.mark.django_db
def test_enrich_missing_product_returns_fallback():
    res = enrich(product_id=999999)
    assert res.source == "fallback"
