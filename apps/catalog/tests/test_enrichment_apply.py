# apps/catalog/tests/test_enrichment_apply.py
import pytest

from apps.catalog.enrichment import (AiAttr, apply_ai_enrichment,
                                     get_enrichable_product, pending_for_enrichment)
from apps.catalog.models import (Attribute, AttributeType, Category, EnrichStatus,
                                  Product, ProductAttributeValue, ProductStatus, Source)


def _product(**kw):
    cat = Category.objects.first() or Category.add_root(name="Перфораторы", slug="perf")
    data = dict(category=cat, name="", slug="p1", original_name="Перфоратор HR2470 Makita",
                status=ProductStatus.IMPORTED, is_active=False, price="1000")
    data.update(kw)
    return Product.objects.create(**data)


@pytest.mark.django_db
def test_get_enrichable_returns_unpublished():
    p = _product()
    assert get_enrichable_product(p.pk).pk == p.pk
    assert get_enrichable_product(999999) is None


@pytest.mark.django_db
def test_fills_only_empty_card_fields():
    p = _product(slug="p2", description="уже есть")
    res = apply_ai_enrichment(p, name="Перфоратор Makita HR2470",
                              description="новое", confidence=0.9)
    p.refresh_from_db()
    assert p.name == "Перфоратор Makita HR2470"
    assert p.description == "уже есть"
    assert p.content_source == "llm" and p.enrich_status == EnrichStatus.DONE
    assert "name" in res["fields_updated"] and "description" not in res["fields_updated"]


@pytest.mark.django_db
def test_low_confidence_goes_to_moderation():
    p = _product(slug="p3")
    apply_ai_enrichment(p, name="X", confidence=0.5)
    p.refresh_from_db()
    assert p.enrich_status == EnrichStatus.MODERATION


@pytest.mark.django_db
def test_content_locked_blocks_everything():
    p = _product(slug="p4", content_locked=True)
    res = apply_ai_enrichment(p, name="X", confidence=0.9)
    p.refresh_from_db()
    assert p.name == "" and res["locked"] is True


@pytest.mark.django_db
def test_llm_does_not_overwrite_manual_pav():
    p = _product(slug="p5")
    attr = Attribute.objects.create(slug="power", name="Мощность",
                                    attribute_type=AttributeType.INTEGER, unit="Вт")
    ProductAttributeValue.objects.create(product=p, attribute=attr, value_integer=900,
                                         source=Source.MANUAL, confidence=100)
    apply_ai_enrichment(p, attributes=[AiAttr(slug="power", value=780)], confidence=0.9)
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    assert pav.value_integer == 900 and pav.source == Source.MANUAL


@pytest.mark.django_db
def test_llm_writes_into_gap_pav():
    p = _product(slug="p6")
    Attribute.objects.create(slug="power", name="Мощность",
                             attribute_type=AttributeType.INTEGER, unit="Вт")
    apply_ai_enrichment(p, attributes=[AiAttr(slug="power", value=780)], confidence=0.9)
    pav = ProductAttributeValue.objects.get(product=p, attribute__slug="power")
    assert pav.value_integer == 780 and pav.source == Source.LLM
    p.refresh_from_db()
    assert p.attrs_cache.get("power") == 780


@pytest.mark.django_db
def test_pending_prioritizes_in_stock():
    _product(slug="instock", available_quantity=10)
    _product(slug="nostock", available_quantity=0)
    ids = pending_for_enrichment(limit=1)
    assert Product.objects.get(slug="instock").id == ids[0]


@pytest.mark.django_db
def test_force_overwrites_existing_card_field():
    p = _product(slug="p7", name="Старое имя", description="Старое описание")
    res = apply_ai_enrichment(p, name="Новое имя Makita", description="Новое описание PRO",
                              confidence=0.9, force=True)
    p.refresh_from_db()
    assert p.name == "Новое имя Makita"
    assert p.description == "Новое описание PRO"
    assert "name" in res["fields_updated"]
    assert "description" in res["fields_updated"]
    assert p.content_source == "llm"


@pytest.mark.django_db
def test_force_bypasses_content_locked():
    p = _product(slug="p8", content_locked=True)
    res = apply_ai_enrichment(p, name="Новый Перфоратор", confidence=0.9, force=True)
    p.refresh_from_db()
    assert res["locked"] is False
    assert p.name == "Новый Перфоратор"
    assert p.content_source == "llm"
    assert p.enrich_status == EnrichStatus.DONE
