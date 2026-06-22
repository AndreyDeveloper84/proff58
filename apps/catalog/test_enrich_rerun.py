"""Повторный прогон enrich_tool_type должен быть идемпотентным и bulk (не per-row).

Регресс-тест на баг: при повторном enrich существующие PAV обновлялись через
update_or_create по одной строке (вешало Postgres). Теперь — bulk_update.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    Source,
)


def _make_catalog():
    root = Category.add_root(name="Электроинструмент", slug="elektro", on_site=True)
    for i in range(12):
        Product.objects.create(
            code_1c=f"p{i}", name=f"Перфоратор Bosch {i}", category=root, slug=f"p{i}"
        )
    Product.objects.create(code_1c="u", name="Удлинитель силовой", category=root, slug="u")
    return root


@pytest.mark.django_db
def test_enrich_rerun_idempotent_and_bulk():
    _make_catalog()
    call_command("load_tool_types")
    call_command("enrich_tool_type")

    attr = Attribute.objects.get(slug="tool_type")
    first = ProductAttributeValue.objects.filter(attribute=attr).count()
    assert first == 12  # перфораторы получили tool_type, удлинитель — нет

    # Повторный прогон: без дублей и БЕЗ per-row UPDATE по PAV.
    with CaptureQueriesContext(connection) as ctx:
        call_command("enrich_tool_type")

    assert ProductAttributeValue.objects.filter(attribute=attr).count() == 12  # идемпотентно

    pav_updates = [
        q["sql"]
        for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith("UPDATE")
        and "productattributevalue" in q["sql"].lower()
    ]
    # значения не изменились → ни одного UPDATE по PAV (и точно не по строке на товар)
    assert pav_updates == []


@pytest.mark.django_db
def test_enrich_rerun_fixes_changed_value_via_bulk():
    """Если значение PAV разъехалось — повторный enrich чинит его bulk_update'ом."""
    _make_catalog()
    call_command("load_tool_types")
    call_command("enrich_tool_type")

    attr = Attribute.objects.get(slug="tool_type")
    wrong = attr.options.exclude(value="Перфораторы").first()
    pav = ProductAttributeValue.objects.filter(attribute=attr).first()
    pav.value_option = wrong
    pav.save(update_fields=["value_option"])

    with CaptureQueriesContext(connection) as ctx:
        call_command("enrich_tool_type")

    pav.refresh_from_db()
    assert pav.value_option.value == "Перфораторы"  # вернулось к правильному
    bulk_updates = [
        q["sql"]
        for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith("UPDATE")
        and "productattributevalue" in q["sql"].lower()
    ]
    assert len(bulk_updates) >= 1  # обновление было — и оно bulk (одно на батч)


def _make_ushm(name, code="u1"):
    """Товар-УШМ с tool_type=bolgarki-ushm (как после enrich_tool_type)."""
    top = Category.add_root(name="Электроинструмент", slug="elektro", on_site=True)
    tt = Attribute.objects.create(
        slug="tool_type",
        name="Тип инструмента",
        attribute_type=AttributeType.SELECT,
        is_filterable=True,
    )
    opt = AttributeOption.objects.create(attribute=tt, value="УШМ (болгарки)", slug="bolgarki-ushm")
    product = Product.objects.create(category=top, name=name, slug=code, code_1c=code)
    ProductAttributeValue.objects.create(
        product=product, attribute=tt, value_option=opt, source=Source.MANUAL
    )
    return product


@pytest.mark.django_db
def test_enrich_prunes_stale_engine_value():
    """Устаревшее regex-значение, которое движок больше не извлекает, удаляется + чистится кэш."""
    product = _make_ushm("Шлифмаш угл DENZEL AG125-1500")  # disc/power/power_source, без voltage
    call_command("load_attributes")
    call_command("enrich_attributes")

    voltage = Attribute.objects.get(slug="voltage")
    stale = ProductAttributeValue.objects.create(
        product=product, attribute=voltage, value_decimal=Decimal("2000"), source=Source.REGEX
    )
    product.refresh_from_db()
    cache = dict(product.attrs_cache or {})
    cache["voltage"] = {"value": "2000"}
    product.attrs_cache = cache
    product.save(update_fields=["attrs_cache"])

    call_command("enrich_attributes")

    assert not ProductAttributeValue.objects.filter(pk=stale.pk).exists()  # удалено
    product.refresh_from_db()
    assert "voltage" not in (product.attrs_cache or {})  # и из attrs_cache
    # Реально извлекаемые значения не пострадали.
    assert ProductAttributeValue.objects.filter(product=product, attribute__slug="power").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("source", [Source.MANUAL, Source.IMPORT_1C, Source.LLM])
def test_enrich_keeps_non_engine_value(source):
    """Авторитетные (manual/import_1c) и llm-значения enrich НЕ удаляет, даже если не извлёк."""
    product = _make_ushm("Шлифмаш угл DENZEL AG125-1500")
    call_command("load_attributes")
    call_command("enrich_attributes")

    voltage = Attribute.objects.get(slug="voltage")
    kept = ProductAttributeValue.objects.create(
        product=product, attribute=voltage, value_decimal=Decimal("2000"), source=source
    )

    call_command("enrich_attributes")

    assert ProductAttributeValue.objects.filter(pk=kept.pk).exists()  # сохранено
