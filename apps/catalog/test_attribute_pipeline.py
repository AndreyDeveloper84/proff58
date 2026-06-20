"""Пайплайн характеристик (Фаза B, #96): load_attributes → enrich_attributes.

Проверяем поверх реального словаря ``data/attribute_rules.json`` (через call_command):
извлечение значений с провенансом, защиту приоритетом (manual/import_1c не затираются),
конфликт boolean «без АКБ», валидатор confidence и backend range-фильтра (+ HTTP 400).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client

from apps.catalog import services
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    Source,
)


@pytest.fixture
def catalog(db):
    """Топ-категория «Электроинструмент» + атрибут tool_type с вариантом «Дрели…»."""
    top = Category.add_root(name="Электроинструмент", slug="elektroinstrument", on_site=True)
    tool_type = Attribute.objects.create(
        slug="tool_type",
        name="Тип инструмента",
        attribute_type=AttributeType.SELECT,
        is_filterable=True,
    )
    option = AttributeOption.objects.create(
        attribute=tool_type, value="Дрели и шуруповёрты", slug="dreli-shurupoverty"
    )
    return {"top": top, "tool_type": tool_type, "option": option}


def _make_product(catalog, name, code):
    """Товар с tool_type=Дрели и шуруповёрты (как после enrich_tool_type)."""
    product = Product.objects.create(category=catalog["top"], name=name, slug=code, code_1c=code)
    ProductAttributeValue.objects.create(
        product=product,
        attribute=catalog["tool_type"],
        value_option=catalog["option"],
        source=Source.MANUAL,
    )
    return product


@pytest.mark.django_db
def test_enrich_extracts_with_provenance(catalog):
    product = _make_product(catalog, "Дрель-шуруповёрт аккумуляторный 18В бесщёточный 55 Нм", "p1")
    call_command("load_attributes")
    call_command("enrich_attributes")

    vals = {
        pav.attribute.slug: pav
        for pav in product.attribute_values.select_related("attribute", "value_option")
    }
    assert vals["voltage"].value_decimal == Decimal("18")
    assert vals["torque"].value_decimal == Decimal("55")
    assert vals["power_source"].value_option.slug == "battery"
    assert vals["motor_type"].value_option.slug == "brushless"

    # Провенанс: source + confidence (regex=100, keyword=90).
    assert vals["voltage"].source == Source.REGEX
    assert vals["voltage"].confidence == 100
    assert vals["power_source"].source == Source.KEYWORD
    assert vals["power_source"].confidence == 90

    # attrs_cache (read-model) пересобран из EAV.
    product.refresh_from_db()
    assert product.attrs_cache["voltage"] == 18.0
    assert product.attrs_cache["power_source"] == "Аккумулятор"


@pytest.mark.django_db
def test_manual_not_overwritten_even_with_higher_confidence(catalog):
    """Перезапись решает приоритет источника, НЕ confidence."""
    product = _make_product(catalog, "Дрель-шуруповёрт 18В", "pm")
    call_command("load_attributes")
    voltage = Attribute.objects.get(slug="voltage")
    # Ручное значение с НИЗКИМ confidence; regex дал бы 18 с confidence=100.
    ProductAttributeValue.objects.create(
        product=product,
        attribute=voltage,
        value_decimal=Decimal("99"),
        source=Source.MANUAL,
        confidence=50,
    )
    call_command("enrich_attributes")

    pav = ProductAttributeValue.objects.get(product=product, attribute=voltage)
    assert pav.value_decimal == Decimal("99")  # regex НЕ затёр ручное
    assert pav.source == Source.MANUAL


@pytest.mark.django_db
def test_import_1c_not_overwritten_by_regex(catalog):
    product = _make_product(catalog, "Дрель-шуруповёрт 55 Нм", "pi")
    call_command("load_attributes")
    torque = Attribute.objects.get(slug="torque")
    ProductAttributeValue.objects.create(
        product=product, attribute=torque, value_decimal=Decimal("10"), source=Source.IMPORT_1C
    )
    call_command("enrich_attributes")

    pav = ProductAttributeValue.objects.get(product=product, attribute=torque)
    assert pav.value_decimal == Decimal("10")  # import_1c (60) > regex (40)
    assert pav.source == Source.IMPORT_1C


@pytest.mark.django_db
def test_battery_included_negative_wins(catalog):
    """«без АКБ и ЗУ» → False, даже что в названии есть «АКБ»."""
    product = _make_product(catalog, "Дрель-шуруповёрт 18В без АКБ и ЗУ", "pb")
    call_command("load_attributes")
    call_command("enrich_attributes")

    pav = ProductAttributeValue.objects.get(product=product, attribute__slug="battery_included")
    assert pav.value_boolean is False


@pytest.mark.django_db
def test_confidence_validator_rejects_out_of_range(catalog):
    product = Product.objects.create(category=catalog["top"], name="Дрель", slug="pc")
    pav = ProductAttributeValue(
        product=product,
        attribute=catalog["tool_type"],
        value_option=catalog["option"],
        confidence=999,
    )
    with pytest.raises(ValidationError):
        pav.full_clean()


@pytest.mark.django_db
def test_range_filter_matches_value(catalog):
    p18 = _make_product(catalog, "Дрель-шуруповёрт 18В", "r18")
    p12 = _make_product(catalog, "Дрель-шуруповёрт 12В", "r12")
    call_command("load_attributes")
    call_command("enrich_attributes")

    ids = set(
        services.products_in(catalog["top"], attr_ranges={"voltage": (18, 18)}).values_list(
            "id", flat=True
        )
    )
    assert p18.id in ids
    assert p12.id not in ids


@pytest.mark.django_db
def test_range_filter_invalid_query_returns_400(catalog):
    _make_product(catalog, "Дрель-шуруповёрт 18В", "rb")
    call_command("load_attributes")
    call_command("enrich_attributes")

    resp = Client().get("/catalog/elektroinstrument/?voltage_min=abc")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_load_attributes_idempotent(catalog):
    call_command("load_attributes")
    attrs = Attribute.objects.count()
    opts = AttributeOption.objects.count()
    call_command("load_attributes")  # повтор не плодит дубли
    assert Attribute.objects.count() == attrs
    assert AttributeOption.objects.count() == opts
