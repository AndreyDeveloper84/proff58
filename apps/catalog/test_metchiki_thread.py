"""Метчики и плашки: резьба с дробным номинальным диаметром.

`discover_missing_rules` поставил этот тип первым среди заблокированных — 1381
«потенциальное значение» на 802 товарах — и предложил завести новые оси `thread`
и `size_pair`. Проверка показала другое: блок уже развитый (`tool_kind` заполнен у
всех 802, диаметр и шаг у 495), а из 307 товаров без диаметра новые оси нужны
лишь части.

Разбор 307:

* 141 прочее;
* 65 держатели и оснастка — у метчикодержателя своей резьбы нет;
* 64 дюймовые и трубные (BSW, UNC, UNF, G1–G3) — им нужна отдельная ось;
* **37 метрических, которые правило просто не брало** — этот файл про них.

Причина была в шаблоне: он требовал ЦЕЛЫЙ номинальный диаметр, поэтому
«М 6х1,0» читалось, а «М 2,5х0,45» — нет. М2,5 и М4,5 — стандартные размеры
резьбы, а не опечатки.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

TT = "metchiki-plashki"


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _pair(rules: AttributeRules, name: str):
    got = {v.slug: v.number for v in rules.extract(TT, name)}
    return got.get("diameter"), got.get("thread_pitch")


@pytest.mark.parametrize(
    ("name", "diameter", "pitch"),
    [
        ("Метчик м/р М 2,0х0,4 Р6М5", "2.0", "0.4"),
        ("Метчик М 2,0х0,4 м/р Р6М5", "2.0", "0.4"),
        ("Метчик м/р гаечный прямой М  2,5х0,45", "2.5", "0.45"),
        ("Метчик м/р М 1,6х0,35 к-т 3шт сталь Р6М5К5", "1.6", "0.35"),
        ("Метчик м/р М 4,5х0,75 к-т", "4.5", "0.75"),
        ("Метчик м/р М 9,0х1,25 м/р Р6М5", "9.0", "1.25"),
    ],
)
def test_fractional_nominal_diameter_is_read(rules, name, diameter, pitch):
    """«М 2,5х0,45» — диаметр 2,5 и шаг 0,45, а не молчание.

    Шаблон требовал целое число перед «х», и все резьбы с дробным номиналом
    выпадали. Диаметр и шаг читаются из ОДНОЙ пары, поэтому правятся синхронно:
    иначе у товара появился бы шаг без диаметра.
    """
    assert _pair(rules, name) == (Decimal(diameter), Decimal(pitch))


@pytest.mark.parametrize(
    ("name", "diameter", "pitch"),
    [
        ("Метчик винтовой М  6х1,0 HSS STV", "6", "1.0"),
        ("Метчик машинный М10х1,5 HSS", "10", "1.5"),
        ("Метчик винтовой М  4х0,7 HSSE DIN 371 RUKO", "4", "0.7"),
    ],
)
def test_whole_nominal_diameter_unchanged(rules, name, diameter, pitch):
    """Регресс: целый номинал читается как прежде — правка аддитивная."""
    assert _pair(rules, name) == (Decimal(diameter), Decimal(pitch))


@pytest.mark.parametrize(
    "name",
    [
        "Набор металло-режущ инструмент Matrix метчики и плашки М2-М20, 65 шт",
        'Набор металло-режущ инструмент ЗУБР "МАСТЕР" метчики и плашки М1-М2,5',
        "Метчикодержатель №2 (М3-М14)",
        "Метчикодержатель №1, с регулируемыми вкладышами",
    ],
)
def test_sets_and_holders_stay_silent(rules, name):
    """У набора «М3-М12» одной резьбы нет, у держателя — своей резьбы нет вовсе.

    Диапазон в названии набора («М2-М20») выглядит как размер, но описывает
    ОХВАТ комплекта. Стоп-слова блока («набор», «держател», «ворот») закрывают
    оба класса, и дробная часть в шаблоне их не ослабила.
    """
    assert _pair(rules, name) == (None, None)
