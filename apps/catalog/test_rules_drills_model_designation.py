"""SEO-BATCH-02: мощность и напряжение дрелей-шуруповёртов из обозначения модели.

У части сетевых дрелей и шуруповёртов мощность в названии указана только обозначением
(«ДУ-15/680», «СШ-550-1»), у аккумуляторных — напряжение («ДА-18», «ДА-14,4»). Кейсы взяты
с реальных названий стенда (565 дрелей) и держат обе границы: явное значение в тексте
приоритетнее, а «ДА-10/12В» — диаметр патрона плюс вольты, не «10 В».
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

TT = "dreli-shurupoverty"


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _v(rules, axis, name):
    for v in rules.extract(TT, name):
        if v.slug == axis:
            return v.option_slug or v.number
    return None


CASES = [
    # мощность: явные ватты
    ("power", 'Дрель ударная ДУ-13/750 ЭР (ударная, 750 Вт) "Интерскол"', 750),
    ("power", "Дрель D13VF; 710 Вт б/з 13мм, 47 Нм, сталь/дер. 13", 710),
    # мощность: только обозначение модели
    ("power", "Дрель ударная РЕСАНТА ДУ-15/680", 680),
    ("power", "Дрель ударная РЕСАНТА ДУ-16/1100МК", 1100),
    ("power", 'Дрель ударная ДУ-16/1050ЭР "Интерскол"', 1050),
    ("power", "Шуруповёрт сетев. СШ-550-1 РЕСАНТА", 550),
    ("power", "Шуруповёрт сетев. СШ-550/2 ВИХРЬ", 550),
    # мощность: обозначения без ватт не выдумываются
    ("power", "Шуруповёрт аккумуляторный РЕСАНТА ДА-20-2ЛК-Б (Li-ion) бесщеточный", None),
    ("power", "Дрель-миксер ЗУБР ЗДМ-1200РММ2", None),
    # напряжение: явные вольты
    ("voltage", 'Дрель акк. ДА-12 ЭР-02 (12В) "Интерскол"', 12),
    ("voltage", "Винтоверт аккумуляторный ЗУБР GVB-250 20В бесщеточная", 20),
    # напряжение: только обозначение модели
    ("voltage", "Шуруповёрт аккумуляторный ДА-18-2к ВИХРЬ", 18),
    ("voltage", "Шуруповёрт аккумуляторный РЕСАНТА ДА-18-2ЛК-У (Li-ion) ударный", 18),
    ("voltage", "Шуруповёрт аккумуляторный ДА-14,4Л-2К (Li-ion) ВИХРЬ", Decimal("14.4")),
    # граница: «ДА-10/12В» — 10 это диаметр патрона, напряжение 12
    ("voltage", "Шуруповёрт аккумуляторный ДА-10/12В ИНТЕРСКОЛ", 12),
    ("voltage", "Шуруповёрт аккумуляторный ДА-10/18В, Li-ion АПИ (кейс, 2 аккумулятора)", 18),
    # граница: мощность сетевой машины не попадает в вольты
    ("voltage", "Шуруповёрт сетев. СШ-550-1 РЕСАНТА", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES)
def test_model_designation_rules(rules, axis, name, expected):
    got = _v(rules, axis, name)
    if expected is None:
        assert got is None, f"{axis}: лишнее значение {got!r} из {name!r}"
    else:
        assert got == Decimal(str(expected)), f"{axis}: {got!r} != {expected!r} из {name!r}"
