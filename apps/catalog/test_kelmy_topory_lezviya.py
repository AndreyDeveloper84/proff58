"""Ещё три блока правил для типов, у которых блока не было: гладилки, топоры, лезвия.

Из пяти кандидатов взяты три. Лопаты и лестницы отложены: в лопатах половина пула —
движки для снега (скреперы) с шириной ковша вместо размера черенка, в лестницах —
вышки-туры, где запись разнородная («до 3м», «высота 300см», «150кг»).
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
            return v.number
    return None


# --- Гладилки и кельмы: размер рабочей поверхности ----------------------------


@pytest.mark.parametrize(
    ("name", "width", "length"),
    [
        ('Гладилка 130х280мм STAYER "PROFI" нержавеющая', "130", "280"),
        ("Гладилка 130х480мм нерж сталь, деревянная рукоятка/Remocolor", "130", "480"),
        ("Гладилка 140х280мм пластиковая", "140", "280"),
    ],
)
def test_trowel_face_size(rules, name, width, length):
    """«130х280мм» — ширина и длина рабочей поверхности.

    Фасет заводить не понадобилось: в листе «Шпатели, кельмы и тёрки» оси `width`
    и `length` уже привязаны — не хватало только значений.
    """
    assert _v(rules, "str-kelmy", "width", name) == Decimal(width)
    assert _v(rules, "str-kelmy", "length", name) == Decimal(length)


def test_notch_size_does_not_win_over_face_size(rules):
    """«зубчатая 6х6мм» — размер зуба, а не полотна.

    Парный шаблон требует двузначного числа слева, у зуба размеры однозначные, и
    первым в названии всегда стоит размер полотна.
    """
    name = 'Гладилка 130х280мм ЗУБР "ЭКСПЕРТ" зубчатая 6х6мм'
    assert _v(rules, "str-kelmy", "width", name) == Decimal("130")
    assert _v(rules, "str-kelmy", "length", name) == Decimal("280")


# --- Топоры и колуны: вес ------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "kg"),
    [
        ('Колун 3,6кг/900мм ЗУБР "МАСТЕР" кованый', "3.6"),
        ("яяКолун Вача (1,9кг) (8)", "1.9"),
        ("Ледоруб-топор 150мм, 1,4 кг, металлический черенок 1370", "1.4"),
    ],
)
def test_axe_weight(rules, name, kg):
    """Вес — главный параметр выбора топора, и он записан в названии."""
    assert _v(rules, "topory", "weight_kg", name) == Decimal(kg)


@pytest.mark.parametrize(
    "name",
    [
        "Клинья для топора 2шт 5-6мм STAYER",
        'Жало для паяльника серии 900М, d4,3мм тип "топорик" 5,0мм REXANT',
    ],
)
def test_foreign_goods_inside_the_type_stay_silent(rules, name):
    """Клин и паяльное жало «типа топорик» лежат в типе, но топорами не являются."""
    assert _v(rules, "topory", "weight_kg", name) is None


# --- Сменные лезвия: типоразмер и фасовка -------------------------------------


@pytest.mark.parametrize(
    ("name", "width"),
    [
        ("Лезвие 18х100х0,5мм, OLFA BLACK MAX сегментированное, 10шт", "18"),
        ("Лезвие OLFA EXCEL BLACK 18мм 10шт черные", "18"),
        ("Лезвия 18 мм (10 шт.)", "18"),
        ("Лезвие 9х80х0,4мм сегментированное 10шт", "9"),
        ("Лезвие 25х125х0,7мм 10шт", "25"),
    ],
)
def test_blade_width_is_a_standard_size(rules, name, width):
    """Ширина сменного лезвия — стандартный типоразмер 9, 18 или 25 мм."""
    assert _v(rules, "hoz-lezviya", "width", name) == Decimal(width)


def test_hook_blade_gets_no_width(rules):
    """«Лезвие-крюк 90х20х39,5х0,8мм» — 90 это длина крюка, а не ширина.

    Сначала списком типоразмеров был ограничен только один из двух шаблонов, и
    крюковидное лезвие получило ширину 90. Теперь список стоит в обоих: ширину
    сменного лезвия нельзя угадывать — по ней его подбирают к ножу, и лучше
    молчание, чем правдоподобное чужое число.
    """
    name = "Лезвие-крюк OLFA для ножа OLFA-HOK-1, 90х20х39,5х0,8мм"
    assert _v(rules, "hoz-lezviya", "width", name) is None


def test_blade_pack_quantity_is_not_claimed_without_a_decision(rules):
    """Фасовка лезвий («10шт») в блок НЕ заведена — и это не забывчивость.

    По решению ХАР-20 ось `package_quantity` подключена ровно к одному
    подтверждённому типу (str-skoby), и `test_har20_package_quantity` держит это
    инвариантом, чтобы «N шт» не стало глобальной фасовкой. Сменные лезвия
    продают пачками, ось им подходит по смыслу, замер даёт 55 товаров из 105 —
    но подключение второго типа это решение владельца, а не побочный эффект
    нового блока.
    """
    name = "Лезвие 18х100х0,5мм, OLFA сегментированное, 10шт"
    assert _v(rules, "hoz-lezviya", "package_quantity", name) is None
    assert _v(rules, "hoz-lezviya", "width", name) == Decimal("18")
