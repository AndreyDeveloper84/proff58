"""Regression coverage for explicit cordless power-source extension."""

from pathlib import Path

import pytest
from django.conf import settings

from apps.catalog.attribute_extract import AttributeRules


@pytest.fixture(scope="module")
def rules():
    return AttributeRules.from_file(Path(settings.BASE_DIR) / "data" / "attribute_rules.json")


@pytest.mark.parametrize(
    "tool_type",
    [
        "bp-trimmery",
        "bp-vozdukhoduvki",
        "obor-moyki",
        "hoz-sekatory",
        "hoz-opryskivateli",
    ],
)
@pytest.mark.parametrize(
    "name,expected",
    [
        ("Инструмент аккумуляторный 18 В", "battery"),
        ("Мойка аккумуляторная 36 В", "battery"),
        ("Устройство аккумуляторное", "battery"),
        ("Cordless tool", "battery"),
        ("Инструмент аккум. 18 В", "battery"),
        ("Инструмент 220В", "mains"),
        ("Инструмент 380 В", "mains"),
        ("Инструмент аккум 220В", None),
        ("Инструмент 380 В аккум", None),
        ("Бензокоса аккум", None),
        ("Насадка аккум", None),
        ("Инструмент без аккум", None),
        ("Инструмент для аккум", None),
        ("Инструмент Li-ion 18 В", None),
        ("Инструмент электрический", None),
        ("Инструмент сетевой 220 В", "mains"),
        ("Модель сетевая", "mains"),
        ("Инструмент от сети", "mains"),
        ("Инструмент бесщёточный", None),
        ("Инструмент 18 В", None),
        ("Инструмент бензиновый", None),
        ("Бензиновый инструмент с электростартером", None),
        ("Инструмент аккумуляторный сетевой", None),
        ("Инструмент сетевой аккумуляторный", None),
        ("Инструмент cordless от сети", None),
        ("Инструмент от сети cordless", None),
        ("Инструмент для аккумуляторной платформы", None),
        ("Запчасть для аккумуляторной модели", None),
        ("Адаптер аккумуляторный", None),
    ],
)
def test_cordless_extension_power_source(rules, tool_type, name, expected):
    values = {value.slug: value for value in rules.extract(tool_type, name)}
    actual = values.get("power_source")
    if expected is None:
        assert actual is None
    else:
        assert actual is not None
        assert actual.option_slug == expected
        assert actual.source == "keyword"
        assert actual.priority == 30


@pytest.mark.parametrize(
    "tool_type,name",
    [
        (
            "bp-vozdukhoduvki",
            "Воздуходувка аккум DENZEL RB180-36, Li-ion 36В 4Ач, 180км/ч 820м3/ч 2 аккум 18В 4Ач",
        ),
        (
            "bp-vozdukhoduvki",
            "Воздуходувка аккум Einhell PXC GE-LB 36/210 Li E-Solo бесщеточная без АККУМ и ЗУ",
        ),
        (
            "bp-vozdukhoduvki",
            "Воздуходувка аккум Hitachi RВ18DLL; без аккум и за",
        ),
        (
            "bp-trimmery",
            "Триммер аккум DENZEL RT300-36, Li-ion 36В 4Ач 2 аккум 18В 4Ач",
        ),
        (
            "bp-trimmery",
            "Триммер аккум DENZEL бесщеточ CBC350-36, Li-ion 36В 2 акуум 18В 4Ач",
        ),
        (
            "bp-trimmery",
            "Триммер аккум. CG18DSDLT4; 18V,(без аккум и зар. у",
        ),
    ],
)
def test_cordless_original_name_regression(rules, tool_type, name):
    values = {value.slug: value for value in rules.extract(tool_type, name)}
    assert values["power_source"].option_slug == "battery"
