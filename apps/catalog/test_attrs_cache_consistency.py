"""Инвариант Фазы 4: обычный PAV-путь и enrich-путь дают ИДЕНТИЧНЫЙ attrs_cache.

Оба пути сериализации значения делегируют в единое ядро ``typed_value_to_json``
(``read_models``). Здесь проверяем ТОЧНОЕ равенство значений и их типов
(``==`` и ``type(...)``) для характеристик разных типов: decimal, boolean (включая
False), select. Числовой enrich-экстракт (NUMBER) проходит через реальный
``Attribute.attribute_type`` (DECIMAL по ``load_attributes``), поэтому совпадает
с PAV-путём (float, не int).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttrValue
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
)
from apps.catalog.read_models import (
    attr_value_to_json,
    extracted_value_to_json,
    rebuild_attrs_cache,
)


@pytest.fixture
def product(db):
    cat = Category.add_root(name="Дрели", slug="dreli")
    return Product.objects.create(category=cat, name="Дрель X", slug="drel-x")


def _attr(slug, atype, **kw):
    return Attribute.objects.create(slug=slug, name=slug, attribute_type=atype, **kw)


@pytest.mark.django_db
def test_enrich_and_pav_paths_produce_identical_cache(product):
    """attrs_cache из rebuild и из extracted_value_to_json совпадает значение-в-значение."""
    # DECIMAL: load_attributes мапит number→DECIMAL, enrich пишет в value_decimal.
    a_dec = _attr("voltage", AttributeType.DECIMAL, unit="В")
    # BOOLEAN, включая значение False (валидное, не выбрасывается).
    a_bool_true = _attr("reverse", AttributeType.BOOLEAN)
    a_bool_false = _attr("battery_included", AttributeType.BOOLEAN)
    # SELECT: значение кэша — option.value (рус. ярлык).
    a_sel = _attr("power_source", AttributeType.SELECT)
    opt = AttributeOption.objects.create(attribute=a_sel, value="Аккумулятор", slug="battery")

    # --- Путь 1: реальные PAV + rebuild_attrs_cache ---
    ProductAttributeValue.objects.create(
        product=product, attribute=a_dec, value_decimal=Decimal("18")
    )
    ProductAttributeValue.objects.create(product=product, attribute=a_bool_true, value_boolean=True)
    ProductAttributeValue.objects.create(
        product=product, attribute=a_bool_false, value_boolean=False
    )
    ProductAttributeValue.objects.create(product=product, attribute=a_sel, value_option=opt)
    pav_cache = rebuild_attrs_cache(product)

    # --- Путь 2: enrich-сериализация тех же значений (extracted_value_to_json) ---
    # av — то, что отдаёт AttributeRules.extract (Decimal в number, bool в boolean).
    enrich_cache = {
        "voltage": extracted_value_to_json(
            a_dec,
            AttrValue(
                slug="voltage", kind="number", source="regex", priority=0, number=Decimal("18")
            ),
        ),
        "reverse": extracted_value_to_json(
            a_bool_true,
            AttrValue(slug="reverse", kind="boolean", source="regex", priority=0, boolean=True),
        ),
        "battery_included": extracted_value_to_json(
            a_bool_false,
            AttrValue(
                slug="battery_included", kind="boolean", source="regex", priority=0, boolean=False
            ),
        ),
        "power_source": extracted_value_to_json(
            a_sel,
            AttrValue(
                slug="power_source",
                kind="select",
                source="keyword",
                priority=0,
                option_slug="battery",
            ),
            opt,
        ),
    }

    # Точное равенство значений И типов по каждому ключу.
    assert pav_cache.keys() == enrich_cache.keys()
    for slug in pav_cache:
        assert pav_cache[slug] == enrich_cache[slug], slug
        assert type(pav_cache[slug]) is type(enrich_cache[slug]), slug  # noqa: E721

    # Контроль конкретных типов эталона.
    assert enrich_cache["voltage"] == 18.0
    assert type(enrich_cache["voltage"]) is float  # noqa: E721 — decimal→float, не int
    assert enrich_cache["reverse"] is True
    assert enrich_cache["battery_included"] is False  # False сохраняется
    assert enrich_cache["power_source"] == "Аккумулятор"
    assert type(enrich_cache["power_source"]) is str  # noqa: E721


@pytest.mark.django_db
def test_core_covers_pav_only_types_via_attr_value_to_json(product):
    """TEXT/INTEGER enrich не заполняет, но ядро даёт эталон для них (через PAV-адаптер)."""
    a_text = _attr("note", AttributeType.TEXT)
    a_int = _attr("power", AttributeType.INTEGER, unit="Вт")

    pav_text = ProductAttributeValue.objects.create(
        product=product, attribute=a_text, value_text="хорошая"
    )
    pav_int = ProductAttributeValue.objects.create(
        product=product, attribute=a_int, value_integer=650
    )

    assert attr_value_to_json(pav_text) == "хорошая"
    assert type(attr_value_to_json(pav_text)) is str  # noqa: E721
    assert attr_value_to_json(pav_int) == 650
    assert type(attr_value_to_json(pav_int)) is int  # noqa: E721 — INTEGER→int, не float
