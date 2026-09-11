"""Три блока правил для типов без правил: линейки, миксеры-насадки, электроточила.

Из шести кандидатов взяты три. Отложены: угольники (тип-свалка — всё, где есть
слово «треугольник»: кабельные бирки, кельмы, баки), веники (характеристик в
названиях нет), зарядные устройства (напряжение записано разнобоем).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _v(rules: AttributeRules, tt: str, axis: str, name: str):
    for v in rules.extract(tt, name):
        if v.slug == axis:
            return v.option_slug or v.number
    return None


# --- Линейки: длина в двух единицах -------------------------------------------


@pytest.mark.parametrize(
    ("name", "mm"),
    [
        ("Линейка 0,15 м SPARTA", "150"),
        ("Линейка 0,2м ЗУБР Про-20, усиленная нержавеющая", "200"),
        ("Линейка 0,5 м Калибр", "500"),
        ("Линейка измерительная метал. 1000 мм (с поверкой)", "1000"),
        ("Линейка 150 мм хром ГОСТ 427-75", "150"),
    ],
)
def test_ruler_length_in_metres_and_millimetres(rules, name, mm):
    """«0,15 м» и «150 мм» — одна и та же длина, ось хранит миллиметры.

    Метры пересчитываются множителем scale=1000 — тем же механизмом, что
    киловатты у бензоинструмента. Шаблон метров ограничен одной целой цифрой:
    линеек длиннее 9 м не бывает, а ограничение отсекает номера ГОСТ.
    """
    assert _v(rules, "izm-lineyki", "length", name) == Decimal(mm)


# --- Миксеры-насадки: диаметр, длина, хвостовик -------------------------------


@pytest.mark.parametrize(
    ("name", "d", "length", "shank"),
    [
        ("Миксер 100х600мм оцинкованный для красок SDS+", "100", "600", "sds-plus"),
        ("Миксер 100х450мм оцинкованный для красок 6гр хвост СИБИН", "100", "450", "hex"),
        ('Миксер 100х600 мм, SDS+, тип "С", для штукат.смесей', "100", "600", "sds-plus"),
        ("Миксер 120х590мм для гипс смесей ЗУБР", "120", "590", None),
    ],
)
def test_mixer_axes(rules, name, d, length, shank):
    """«100х600мм» — диаметр венчика и длина; хвостовик — ключ совместимости.

    Миксер под SDS+ не встанет в дрель с кулачковым патроном. Опции и slug
    хвостовика совпадают с `shank_type` у коронок и буров — фасет единый.
    """
    assert _v(rules, "str-miksery", "diameter", name) == Decimal(d)
    assert _v(rules, "str-miksery", "length", name) == Decimal(length)
    assert _v(rules, "str-miksery", "shank_type", name) == shank


def test_whisk_is_not_a_mixer(rules):
    """«Венчик-мешалка для миксера» — сменная часть, у неё размеры другие."""
    name = "яяВенчик-мешалка для миксера MGV 120 (нержавеющая ст"
    assert _v(rules, "str-miksery", "diameter", name) is None
    assert _v(rules, "str-miksery", "length", name) is None


def test_mixer_axes_claim_no_facet():
    """39 из 47 миксеров лежат в узле 406 на 550 разнородных товаров — 7 %."""
    import json

    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == "str-miksery")
    for axis in block["attributes"]:
        assert axis.get("bind") is False, axis["slug"]


# --- Электроточила: мощность и диаметр круга ----------------------------------


@pytest.mark.parametrize(
    ("name", "power", "disc"),
    [
        ("Электроточило  Elitech CT600C; 600 Вт, 200х32х40 м", "600", "200"),
        ("Электроточило  Elitech CT900C; 900 Вт, 250х25х20 м", "900", "250"),
        ("Электроточило  Elitech CT300РC; 300 Вт, круг 150х32", "300", "150"),
    ],
)
def test_grinder_power_and_wheel(rules, name, power, disc):
    """Мощность и диаметр круга из тройки «200х32х40»; обе оси в узле уже привязаны."""
    assert _v(rules, "tochila-nazhdaki", "power", name) == Decimal(power)
    assert _v(rules, "tochila-nazhdaki", "disc_diameter", name) == Decimal(disc)


def test_model_index_is_not_a_wheel_size(rules):
    """«BG 250/150» — индекс модели: у одного производителя два круга, у другого — модель.

    Без единицы и в формате индекса шаблон это не трогает намеренно.
    """
    name = "Электроточило BG 250/150  Кратон"
    assert _v(rules, "tochila-nazhdaki", "disc_diameter", name) is None
    assert _v(rules, "tochila-nazhdaki", "power", name) is None
