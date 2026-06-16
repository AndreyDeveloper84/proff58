"""Тесты денормализации характеристик в Product.attrs_cache (#20)."""

import pytest
from django.core.management import call_command

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
)
from apps.catalog.services import rebuild_attrs_cache


@pytest.fixture
def product(db):
    cat = Category.add_root(name="Дрели", slug="dreli")
    return Product.objects.create(category=cat, name="Дрель X", slug="drel-x")


def _attr(slug, atype, **kw):
    return Attribute.objects.create(slug=slug, name=slug, attribute_type=atype, **kw)


@pytest.mark.django_db
def test_rebuild_typed_values(product):
    a_text = _attr("note", AttributeType.TEXT)
    a_int = _attr("power", AttributeType.INTEGER, unit="Вт")
    a_dec = _attr("weight", AttributeType.DECIMAL, unit="кг")
    a_bool = _attr("reverse", AttributeType.BOOLEAN)
    a_sel = _attr("chuck", AttributeType.SELECT)
    opt = AttributeOption.objects.create(attribute=a_sel, value="Быстрозажимной")

    ProductAttributeValue.objects.create(product=product, attribute=a_text, value_text="хорошая")
    ProductAttributeValue.objects.create(product=product, attribute=a_int, value_integer=650)
    ProductAttributeValue.objects.create(product=product, attribute=a_dec, value_decimal="1.5")
    ProductAttributeValue.objects.create(product=product, attribute=a_bool, value_boolean=False)
    ProductAttributeValue.objects.create(product=product, attribute=a_sel, value_option=opt)

    cache = rebuild_attrs_cache(product)
    assert cache == {
        "note": "хорошая",
        "power": 650,
        "weight": 1.5,
        "reverse": False,
        "chuck": "Быстрозажимной",
    }


@pytest.mark.django_db
def test_empty_skipped_but_false_kept(product):
    a_text = _attr("note", AttributeType.TEXT)
    a_bool = _attr("reverse", AttributeType.BOOLEAN)
    ProductAttributeValue.objects.create(product=product, attribute=a_text, value_text="")
    ProductAttributeValue.objects.create(product=product, attribute=a_bool, value_boolean=False)

    cache = rebuild_attrs_cache(product)
    assert "note" not in cache  # пустой текст не кэшируется
    assert cache["reverse"] is False  # boolean False — валидное значение


@pytest.mark.django_db
def test_idempotent(product):
    a = _attr("power", AttributeType.INTEGER)
    ProductAttributeValue.objects.create(product=product, attribute=a, value_integer=600)
    assert rebuild_attrs_cache(product) == rebuild_attrs_cache(product)


@pytest.mark.django_db
def test_signal_rebuilds_on_commit(product, django_capture_on_commit_callbacks):
    a = _attr("power", AttributeType.INTEGER)
    with django_capture_on_commit_callbacks(execute=True):
        ProductAttributeValue.objects.create(product=product, attribute=a, value_integer=600)
    product.refresh_from_db()
    assert product.attrs_cache == {"power": 600}

    pav = product.attribute_values.first()
    with django_capture_on_commit_callbacks(execute=True):
        pav.delete()
    product.refresh_from_db()
    assert product.attrs_cache == {}


@pytest.mark.django_db
def test_rebuild_command_backfills(product):
    a = _attr("power", AttributeType.INTEGER)
    # создаём значение без срабатывания on_commit (в тест-транзакции коллбэк не идёт)
    ProductAttributeValue.objects.create(product=product, attribute=a, value_integer=600)
    product.refresh_from_db()
    assert product.attrs_cache == {}  # кэш ещё пуст

    call_command("rebuild_attrs_cache")
    product.refresh_from_db()
    assert product.attrs_cache == {"power": 600}
