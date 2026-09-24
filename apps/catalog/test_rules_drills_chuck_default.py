"""SEO-BATCH-02: патрон аккумуляторного шуруповёрта по умолчанию — быстрозажимной.

Решение владельца 24.09: если производитель тип патрона не указал, аккумуляторному
шуруповёрту/винтоверту ставим быстрозажимной. Значение выводится (source=inferred,
приоритет 10) и перебивается любой картой производителя или ручным вводом.

Границы, которые держит тест: правило не трогает дрели и сетевые машины (нет voltage),
а явный тип патрона в названии не подменяется выводом.
"""

from __future__ import annotations

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

TT = "dreli-shurupoverty"


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _chuck(rules, name):
    for v in rules.extract(TT, name):
        if v.slug == "chuck":
            return v.option_slug, v.source
    return None, None


CASES = [
    # аккумуляторные шуруповёрты без типа патрона — выводим быстрозажимной
    ("Шуруповёрт аккумуляторный Hanskonner HCD1865BL 18В 65Нм 2акк", "bystrozazhimnoy"),
    ("Шуруповёрт аккумуляторный РЕСАНТА ДА-18-2ЛК-У (Li-ion) ударный", "bystrozazhimnoy"),
    ("Винтоверт аккумуляторный ЗУБР GVB-250 20В бесщеточная", "bystrozazhimnoy"),
    # дрель — не шуруповёрт: правило выключено
    ("Дрель ударная аккум. Einhell PXC TC-ID 18 Li 18В без АКБ", None),
    ("Дрель ударная РЕСАНТА ДУ-15/680", None),
    # сетевой шуруповёрт: напряжения нет, вывод не делается
    ("Шуруповёрт сетев. СШ-550-1 РЕСАНТА", None),
]


@pytest.mark.parametrize(("name", "expected"), CASES)
def test_chuck_default_for_cordless_screwdrivers(rules, name, expected):
    got, source = _chuck(rules, name)
    assert got == expected, f"{name!r}: {got!r} != {expected!r}"
    if expected is not None:
        assert source == "inferred", f"{name!r}: источник {source!r}, ожидался inferred"


def test_inferred_chuck_is_weakest_source(rules):
    """Вывод не должен перебивать карты производителя: приоритет inferred — минимальный."""
    assert rules.source_priority["inferred"] < rules.source_priority["scraper"]
    assert rules.source_priority["inferred"] < rules.source_priority["manual"]
