"""Карточка товара в админке: защита полей 1С и сужение характеристик.

Спринт 2. Два свойства, которые легко потерять при правках:
поля, которые ведёт 1С, руками не редактируются; список характеристик
показывает только те, что назначены категории товара.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite

from apps.catalog.admin import ProductAdmin, ProductAttributeValueInline
from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
)

ПОЛЯ_1С = [
    "price",
    "old_price",
    "currency",
    "unit",
    "is_active_1c",
    "stock_quantity",
    "reserved_quantity",
    "available_quantity",
    "stock_status",
    "code_1c",
    "original_name",
]


@pytest.mark.parametrize("field", ПОЛЯ_1С)
def test_поля_из_1с_только_для_чтения(field):
    """Правка молча терялась при следующей синхронизации — теперь её нельзя сделать."""
    admin_obj = ProductAdmin(Product, AdminSite())

    assert field in admin_obj.readonly_fields


@pytest.mark.parametrize("field", ["name", "card_name", "category", "brand", "description"])
def test_контентные_поля_остаются_редактируемыми(field):
    admin_obj = ProductAdmin(Product, AdminSite())

    assert field not in admin_obj.readonly_fields


@pytest.fixture
def данные(db):
    перфораторы = Category.add_root(name="Перфораторы", slug="perf")
    пилы = Category.add_root(name="Пилы", slug="pily")

    мощность = Attribute.objects.create(
        name="Мощность", slug="moshch", attribute_type=AttributeType.INTEGER
    )
    диаметр = Attribute.objects.create(
        name="Диаметр диска", slug="diametr", attribute_type=AttributeType.INTEGER
    )
    CategoryAttribute.objects.create(category=перфораторы, attribute=мощность)
    CategoryAttribute.objects.create(category=пилы, attribute=диаметр)

    товар = Product.objects.create(
        name="Перфоратор",
        slug="perf-1",
        code_1c="c-1",
        category=перфораторы,
        price=Decimal("100.00"),
    )
    return {"товар": товар, "мощность": мощность, "диаметр": диаметр}


@pytest.fixture
def запрос(rf, db):
    """Запрос с суперпользователем: get_formset проверяет права на удаление."""
    from django.contrib.auth import get_user_model

    request = rf.get("/admin/catalog/product/1/change/")
    request.user = get_user_model().objects.create_superuser(
        phone="+79995550000", password="pwd12345"
    )
    return request


def _attribute_choices(inline, request, obj):
    inline.get_formset(request, obj)
    field = inline.formfield_for_foreignkey(
        ProductAttributeValue._meta.get_field("attribute"), request
    )
    return set(field.queryset.values_list("slug", flat=True))


def test_характеристики_сужены_до_категории_товара(данные, запрос):
    """Иначе человек выбирает из всего справочника и ставит перфоратору диаметр диска."""
    inline = ProductAttributeValueInline(Product, AdminSite())

    choices = _attribute_choices(inline, запрос, данные["товар"])

    assert choices == {"moshch"}


def test_без_категории_показываем_весь_справочник(данные, запрос):
    """У неразобранного товара выбор иначе был бы пустым — заполнить нечем."""
    данные["товар"].category = None
    inline = ProductAttributeValueInline(Product, AdminSite())

    choices = _attribute_choices(inline, запрос, данные["товар"])

    assert {"moshch", "diametr"} <= choices


def test_на_добавлении_товара_справочник_полный(данные, запрос):
    inline = ProductAttributeValueInline(Product, AdminSite())

    choices = _attribute_choices(inline, запрос, None)

    assert {"moshch", "diametr"} <= choices


def test_характеристика_не_в_autocomplete(данные):
    """autocomplete тянет варианты через AJAX и сужение по категории игнорирует."""
    inline = ProductAttributeValueInline(Product, AdminSite())

    assert "attribute" not in (inline.autocomplete_fields or ())


def test_миниатюра_в_списке_и_готовность_в_карточке():
    admin_obj = ProductAdmin(Product, AdminSite())

    assert "thumbnail" in admin_obj.list_display
    assert "readiness" in admin_obj.readonly_fields
