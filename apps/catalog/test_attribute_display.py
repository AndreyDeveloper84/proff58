"""Порядок и состав характеристик в API каталога (DATA-01).

Карточка списка брала фильтруемые характеристики ПО АЛФАВИТУ и обрезала по лимиту: у
перфоратора первой шла не энергия удара, а «АКБ в комплекте». Здесь проверяется, что
порядок задаётся типом товара, одинаков у list и detail и не теряет ``0`` и ``False``.
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.attribute_display import load_order
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    ProductStatus,
)

LIST_URL = "/api/catalog/products/"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def attrs(db):
    def attr(slug, name, kind=AttributeType.DECIMAL, unit="", filterable=True):
        return Attribute.objects.create(
            slug=slug, name=name, attribute_type=kind, unit=unit, is_filterable=filterable
        )

    return {
        "tool_type": attr("tool_type", "Тип инструмента", AttributeType.SELECT),
        "battery_included": attr("battery_included", "АКБ в комплекте", AttributeType.BOOLEAN),
        "power": attr("power", "Мощность", unit="Вт"),
        "energy_impact": attr("energy_impact", "Энергия удара", unit="Дж"),
        "chuck": attr("chuck", "Тип патрона", AttributeType.TEXT),
        "voltage": attr("voltage", "Напряжение", unit="В"),
        "torque": attr("torque", "Крутящий момент", unit="Н·м"),
        "weight_kg": attr("weight_kg", "Масса", unit="кг"),
        "country": attr("country", "Страна", AttributeType.TEXT, filterable=False),
        "exotic": attr("exotic", "Аааа-редкая ось", AttributeType.TEXT),
    }


def make_product(slug, tool_type, attrs, values):
    root = Category.objects.filter(slug="ei").first() or Category.add_root(
        name="Электроинструмент", slug="ei"
    )
    product = Product.objects.create(
        category=root,
        name=f"Товар {slug}",
        slug=slug,
        price=Decimal("1000"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
    )
    if tool_type:
        option, _ = AttributeOption.objects.get_or_create(
            attribute=attrs["tool_type"], value=tool_type, defaults={"slug": tool_type}
        )
        ProductAttributeValue.objects.create(
            product=product, attribute=attrs["tool_type"], value_option=option
        )
    for slug_, value in values.items():
        attribute = attrs[slug_]
        field = {
            AttributeType.DECIMAL: "value_decimal",
            AttributeType.BOOLEAN: "value_boolean",
            AttributeType.TEXT: "value_text",
        }[attribute.attribute_type]
        ProductAttributeValue.objects.create(product=product, attribute=attribute, **{field: value})
    return product


def list_slugs(client, product_slug):
    rows = client.get(LIST_URL, {"limit": 100}).json()["results"]
    return [a["slug"] for a in next(p for p in rows if p["slug"] == product_slug)["attributes"]]


def test_перфоратор_начинается_с_энергии_удара_а_не_с_алфавита(client, attrs):
    make_product(
        "perf",
        "perforatory",
        attrs,
        {
            "battery_included": False,
            "weight_kg": Decimal("2.9"),
            "power": Decimal("800"),
            "chuck": "SDS-plus",
            "energy_impact": Decimal("2.7"),
        },
    )

    assert list_slugs(client, "perf") == [
        "energy_impact",
        "power",
        "chuck",
        "battery_included",
        "weight_kg",
        "tool_type",
    ]


def test_порядок_зависит_от_типа_товара(client, attrs):
    values = {"voltage": Decimal("18"), "torque": Decimal("60"), "power": Decimal("700")}
    make_product("drel", "dreli-shurupoverty", attrs, values)
    make_product("bolg", "bolgarki-ushm", attrs, values)

    assert list_slugs(client, "drel")[:2] == ["voltage", "torque"]
    assert list_slugs(client, "bolg")[:2] == ["power", "voltage"]


def test_тип_без_переопределения_и_товар_без_типа_идут_по_общему_рейтингу(client, attrs):
    make_product("noname", None, attrs, {"weight_kg": Decimal("1"), "power": Decimal("500")})

    assert list_slugs(client, "noname") == ["power", "weight_kg"]


def test_ось_вне_списков_идёт_после_известных_по_названию(client, attrs):
    make_product("x", None, attrs, {"exotic": "да", "weight_kg": Decimal("1")})

    assert list_slugs(client, "x") == ["weight_kg", "exotic"]


def test_ноль_и_нет_не_исчезают_а_пустое_значение_не_отдаётся(client, attrs):
    make_product(
        "zero", None, attrs, {"power": Decimal("0"), "battery_included": False, "chuck": "  "}
    )

    rows = client.get(LIST_URL, {"limit": 100}).json()["results"]
    got = {
        a["slug"]: a["value"] for a in next(p for p in rows if p["slug"] == "zero")["attributes"]
    }

    assert got == {"power": 0.0, "battery_included": False}


def test_карточка_и_страница_товара_показывают_один_порядок(client, attrs):
    make_product(
        "both",
        "perforatory",
        attrs,
        {
            "country": "Германия",
            "weight_kg": Decimal("2.9"),
            "power": Decimal("800"),
            "energy_impact": Decimal("2.7"),
        },
    )

    detail = client.get(f"{LIST_URL}both/").json()["attributes"]
    card = list_slugs(client, "both")

    # Ключевые на странице товара = характеристики карточки, в том же порядке;
    # нефильтруемые (страна) — после них и только на странице товара.
    assert [a["slug"] for a in detail if a["is_key"]] == card
    assert [a["slug"] for a in detail] == [*card, "country"]
    assert "country" not in card


def test_файл_порядка_согласован():
    order = load_order()

    assert order["last"] == ["tool_type"]
    assert "energy_impact" in order["default"]
    for slugs in order["by_tool_type"].values():
        assert slugs, "пустое переопределение бессмысленно"


def test_переопределения_заданы_только_для_типов_из_манифеста():
    """Опечатка в slug типа молча отключила бы переопределение — ловим её здесь."""
    import json
    from pathlib import Path

    from django.conf import settings

    manifest = json.loads(
        (
            Path(settings.BASE_DIR)
            / "data"
            / "catalog_processing_rules"
            / "tool_type_taxonomy.v1.json"
        ).read_text(encoding="utf-8")
    )
    known: set[str] = set()

    def collect(node):
        if isinstance(node, dict):
            if isinstance(node.get("slug"), str):
                known.add(node["slug"])
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(manifest)
    assert not [slug for slug in load_order()["by_tool_type"] if slug not in known]
