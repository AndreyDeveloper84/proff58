"""Повторный прогон enrich_tool_type должен быть идемпотентным и bulk (не per-row).

Регресс-тест на баг: при повторном enrich существующие PAV обновлялись через
update_or_create по одной строке (вешало Postgres). Теперь — bulk_update.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.models import Attribute, Category, Product, ProductAttributeValue


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
