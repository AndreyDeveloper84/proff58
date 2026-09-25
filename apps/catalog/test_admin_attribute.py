"""Тесты списка характеристик в админке: счётчики без декартова фан-аута JOIN-ов.

Регрессия: две Count(distinct=True) по разным связям (PAV и options) в одном
annotate раздували JOIN в произведение — страница висела секунды. Счётчики
считаются подзапросами; здесь проверяем, что значения остаются точными.
"""

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from apps.catalog.admin import AttributeAdmin
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
)


@pytest.mark.django_db
def test_attribute_admin_counts_are_exact_without_fanout():
    cat = Category.add_root(name="Инструменты", slug="instr")

    # Атрибут с вариантами И значениями одновременно — именно эта комбинация
    # раньше давала умножение счётчиков из-за двойного JOIN.
    power = Attribute.objects.create(
        slug="power", name="Мощность", attribute_type=AttributeType.INTEGER
    )
    AttributeOption.objects.create(attribute=power, value="600", slug="600")
    AttributeOption.objects.create(attribute=power, value="800", slug="800")
    for i in range(3):
        product = Product.objects.create(category=cat, name=f"Дрель {i}", slug=f"drill-{i}")
        ProductAttributeValue.objects.create(
            product=product, attribute=power, value_integer=600 + i
        )

    # Второй атрибут: только значение, без вариантов — проверяем Coalesce → 0 (не None).
    weight = Attribute.objects.create(
        slug="weight", name="Вес", attribute_type=AttributeType.INTEGER
    )
    saw = Product.objects.create(category=cat, name="Пила", slug="saw")
    ProductAttributeValue.objects.create(product=saw, attribute=weight, value_integer=10)

    admin_obj = AttributeAdmin(Attribute, AdminSite())
    request = RequestFactory().get("/admin/catalog/attribute/")
    qs = admin_obj.get_queryset(request)

    power_row = qs.get(pk=power.pk)
    assert power_row._values_count == 3  # три PAV, не 3×2
    assert power_row._options_count == 2  # два варианта, не 2×3
    assert admin_obj.values_count(power_row) == 3
    assert admin_obj.options_count(power_row) == 2

    weight_row = qs.get(pk=weight.pk)
    assert weight_row._values_count == 1
    assert weight_row._options_count == 0  # Coalesce: ноль, а не None
