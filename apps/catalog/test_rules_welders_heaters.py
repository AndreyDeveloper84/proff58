"""SEO-BATCH-04: характеристики сварочных аппаратов и тепловых пушек.

Блока `svar-apparaty` в правилах не было вовсе — 143 аппарата стенда жили без единой
характеристики. Кейсы взяты с названий стенда в форме 1С (её подаёт `enrich_attributes`).

Границы, которые держит тест:
* явный ток в тексте сильнее цифры в обозначении модели («BRIMA TIG 200P … 10-180 А» → 180);
* «САИПА» — полуавтомат, хотя слово «инвертор» в названии тоже встречается;
* аппарат для сварки пластиковых труб не получает ни тока, ни типа дуговой сварки;
* у пушек мощность читается только из явных киловатт: обозначение серии ей не равно
  («ТГП-15000 18кВт»), это закреплено фикстурой пакета A.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _v(rules, tt, axis, name):
    for v in rules.extract(tt, name):
        if v.slug == axis:
            return v.option_slug or v.number
    return None


WELDERS = [
    # ток из обозначения серии
    ("welding_current", "Свар. инвертор п/а САИПА-190 3в1 РЕСАНТА", 190),
    ("welding_current", "Свар. инвертор САИ-160 LUX Ресанта", 160),
    # явный ток сильнее обозначения
    ("welding_current", "Свар. аппарат BRIMA TIG 200P 220В 10-180 А", 180),
    # тип сварки
    ("welding_type", "Свар. инвертор п/а САИПА-160 РЕСАНТА", "mig"),
    ("welding_type", "Свар. инвертор САИ-160 LUX Ресанта", "mma"),
    ("welding_type", "Свар. аппарат BRIMA TIG 200P 220В 10-180 А", "tig"),
    # не дуговая сварка — характеристик не выдумываем
    ("welding_type", "Аппарат для сварки полипр.труб CANDAN СМ-02 SET 850Вт", None),
    ("welding_current", "Аппарат для сварки пласт. труб 800Вт;50-300;Д.т.20/2", None),
]

HEATERS = [
    # мощность берётся только из явных киловатт
    ("power", "Тепловая завеса КЭВ-9П3011Е 9кВт, 380В", 9000),
    # обозначение серии мощностью НЕ является: у «ТГП-15000» реальная мощность 18 кВт
    ("power", "Тепловая пушка газовая ТГП-50000 Ресанта", None),
    ("power", "Тепловая пушка РЕСАНТА ТЭП-2000 220В ТЭН", None),
    # тип нагрева
    ("heater_type", "Тепловая пушка газовая ТГП-50000 Ресанта", "gas"),
    ("heater_type", "Тепловая пушка дизельная непрямого нагрева ТДПН-6000 Ресанта", "diesel"),
    ("heater_type", "Тепловая пушка РЕСАНТА ТЭП-3000 220В ТЭН", "electric"),
    ("heater_type", "Тепловая пушка Ballu BHP-M-15", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), WELDERS)
def test_welders(rules, axis, name, expected):
    got = _v(rules, "svar-apparaty", axis, name)
    if expected is None:
        assert got is None, f"{name!r}: лишнее значение {got!r}"
    elif isinstance(expected, str):
        assert got == expected, f"{name!r}: {got!r} != {expected!r}"
    else:
        assert got == Decimal(str(expected)), f"{name!r}: {got!r} != {expected!r}"


@pytest.mark.parametrize(("axis", "name", "expected"), HEATERS)
def test_heaters(rules, axis, name, expected):
    got = _v(rules, "obor-pushki", axis, name)
    if expected is None:
        assert got is None, f"{name!r}: лишнее значение {got!r}"
    elif isinstance(expected, str):
        assert got == expected, f"{name!r}: {got!r} != {expected!r}"
    else:
        assert got == Decimal(str(expected)), f"{name!r}: {got!r} != {expected!r}"


def test_welding_current_stays_in_plausible_range(rules):
    """Ток дуговой сварки бытового класса: 75–400 А. Выход за него — знак ложного матча."""
    for name in (
        "Свар. инвертор САИ-220 Ресанта",
        "Свар. инвертор п/а САИПА-180/5 MIG 5в1 РЕСАНТА",
    ):
        value = _v(rules, "svar-apparaty", "welding_current", name)
        assert value is not None and Decimal(75) <= value <= Decimal(400), (name, value)
