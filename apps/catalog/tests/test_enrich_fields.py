import pytest
from apps.catalog.models import Category, Product, ProductStatus, EnrichStatus


def _product(**kw):
    cat = Category.add_root(name="Перфораторы", slug="perf")
    data = dict(category=cat, name="t", slug="t", status=ProductStatus.IMPORTED,
                is_active=False, price="1000")
    data.update(kw)
    return Product.objects.create(**data)


@pytest.mark.django_db
def test_enrich_fields_defaults():
    p = _product()
    assert p.enrich_status == EnrichStatus.PENDING
    assert p.content_source is None
    assert p.content_confidence is None
