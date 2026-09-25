from unittest.mock import patch

import pytest

from apps.catalog import provenance as prov
from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    ContentSource,
    Product,
    ProductAttributeValue,
    ProductStatus,
    Source,
)


def _product(**kw):
    cat = Category.objects.filter(slug="perf").first() or Category.add_root(
        name="Перф", slug="perf"
    )
    defaults = dict(
        name="",
        slug="x",
        description="",
        short_description="",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
    )
    defaults.update(kw)
    return Product.objects.create(category=cat, **defaults)


def _cmd(product, **kw):
    base = dict(
        product_id=product.pk,
        target_kind="description",
        attribute_slug="",
        value={"type": "text", "value": "Описание из веба"},
        source="web",
        confidence=0.9,
        observed_value_hash=prov.value_hash(""),
        observed_source="",
        allow_equal_override=False,
    )
    base.update(kw)
    return prov.SourcedValueCommand(**base)


def test_can_overwrite_strict_greater():
    assert prov.can_overwrite("web", "llm") is True  # 25 > 20
    assert prov.can_overwrite("web", "regex") is False  # 25 < 40
    assert prov.can_overwrite("web", "marketplace") is False  # равны → без allow_equal
    assert prov.can_overwrite("web", "marketplace", allow_equal=True) is True


@pytest.mark.django_db
def test_apply_text_into_empty_sets_field_provenance():
    p = _product()
    r = prov.apply_sourced_value(_cmd(p))
    p.refresh_from_db()
    assert r.status == "applied"
    assert p.description == "Описание из веба"
    assert p.content_field_sources["description"] == "web"
    assert p.content_source == ContentSource.WEB  # last-applied (текстовое поле)


@pytest.mark.django_db
def test_apply_blocked_by_content_locked():
    p = _product(content_locked=True)
    assert prov.apply_sourced_value(_cmd(p)).status == "skipped_locked"
    p.refresh_from_db()
    assert p.description == ""


@pytest.mark.django_db
def test_apply_conflict_when_baseline_changed():
    p = _product(description="старое")  # поле уже не пустое
    cmd = _cmd(p, observed_value_hash=prov.value_hash(""))  # baseline думает «было пусто»
    assert prov.apply_sourced_value(cmd).status == "conflict"


@pytest.mark.django_db
def test_apply_priority_blocked_lower_than_existing():
    p = _product(
        description="ручное",
        content_source=ContentSource.MANUAL,
        content_field_sources={"description": "manual"},
    )
    cmd = _cmd(p, observed_value_hash=prov.value_hash("ручное"), observed_source="manual")
    assert prov.apply_sourced_value(cmd).status == "priority_blocked"


@pytest.mark.django_db
def test_apply_attribute_does_not_touch_content_source():
    p = _product()
    attr = Attribute.objects.create(
        name="Мощность", slug="power", attribute_type=AttributeType.INTEGER
    )
    cmd = _cmd(
        p,
        target_kind="attribute",
        attribute_slug="power",
        value={"type": "integer", "value": 780},
        observed_value_hash=prov.value_hash(None),
        observed_source="",
    )
    r = prov.apply_sourced_value(cmd)
    p.refresh_from_db()
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    assert r.status == "applied" and pav.value_integer == 780 and pav.source == Source.WEB
    assert p.content_source == ""  # атрибут НЕ трогает карточный source


@pytest.mark.django_db
def test_apply_invalid_type():
    p = _product()
    Attribute.objects.create(name="Мощность", slug="power", attribute_type=AttributeType.INTEGER)
    cmd = _cmd(
        p,
        target_kind="attribute",
        attribute_slug="power",
        value={"type": "integer", "value": "не число"},
        observed_value_hash=prov.value_hash(None),
        observed_source="",
    )
    assert prov.apply_sourced_value(cmd).status == "invalid"


@pytest.mark.django_db
def test_apply_missing_product():
    cmd = prov.SourcedValueCommand(
        product_id=999999,
        target_kind="description",
        attribute_slug="",
        value={"type": "text", "value": "x"},
        source="web",
        confidence=0.5,
        observed_value_hash=prov.value_hash(""),
        observed_source="",
    )
    assert prov.apply_sourced_value(cmd).status == "missing_product"


@pytest.mark.django_db
def test_apply_select_writes_value_option():
    from apps.catalog.models import AttributeOption

    p = _product()
    attr = Attribute.objects.create(
        name="Патрон", slug="chuck", attribute_type=AttributeType.SELECT
    )
    opt = AttributeOption.objects.create(attribute=attr, value="SDS-plus", slug="sds-plus")
    cmd = _cmd(
        p,
        target_kind="attribute",
        attribute_slug="chuck",
        value={"type": "option", "value": "sds-plus"},
        observed_value_hash=prov.value_hash(None),
        observed_source="",
    )
    r = prov.apply_sourced_value(cmd)
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    assert r.status == "applied"
    assert pav.value_option_id == opt.id and pav.value_text == ""


@pytest.mark.django_db
def test_apply_unknown_option_invalid():
    p = _product()
    Attribute.objects.create(name="Патрон", slug="chuck", attribute_type=AttributeType.SELECT)
    cmd = _cmd(
        p,
        target_kind="attribute",
        attribute_slug="chuck",
        value={"type": "option", "value": "нет-такого"},
        observed_value_hash=prov.value_hash(None),
        observed_source="",
    )
    assert prov.apply_sourced_value(cmd).status == "invalid"


@pytest.mark.django_db
def test_apply_option_slug_conflict_invalid():
    """Дубль option slug в provenance — ApplyResult(invalid, 'option slug conflict')."""
    from apps.catalog.models import AttributeOption

    p = _product()
    Attribute.objects.create(name="Патрон", slug="chuck", attribute_type=AttributeType.SELECT)
    cmd = _cmd(
        p,
        target_kind="attribute",
        attribute_slug="chuck",
        value={"type": "option", "value": "sds-plus"},
        observed_value_hash=prov.value_hash(None),
        observed_source="",
    )
    with patch.object(
        AttributeOption.objects, "get", side_effect=AttributeOption.MultipleObjectsReturned
    ):
        r = prov.apply_sourced_value(cmd)
    assert r.status == "invalid"
    assert r.reason == "option slug conflict"
