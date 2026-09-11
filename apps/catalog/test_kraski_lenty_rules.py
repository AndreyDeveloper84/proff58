"""Два первых блока правил: ЛКМ и клейкие ленты.

Оба типа взяты из списка «блока правил нет вовсе» — там лежит основной резерв
каталога (100 типов, 3391 значение), в отличие от верхушки рейтинга
`discover_missing_rules`, где предложения строятся поверх существующих блоков по
форме записи и оказываются ложными.

Замер по данным стенда решил, что писать:

* **ЛКМ** — 412 товаров, фасовка есть у 297: **225 в килограммах**, 49 в литрах,
  22 в миллилитрах. Заводится только вес: оси объёма в БД нет вовсе;
* **ленты** — 218 товаров, форма «48ммх50м» ловится у 96 (44 %).
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


# --- ЛКМ: вес фасовки ---------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "kg"),
    [
        ("Грунт Бетон-контакт 12кг", "12"),
        ("Грунт ГФ-021 серый, 25 кг", "25"),
        ("Грунт глубокого проникновения БОЛАРС 10кг", "10"),
    ],
)
def test_paint_package_weight_is_read(rules, name, kg):
    """Вес фасовки — самая частая форма: 225 товаров из 412."""
    assert _v(rules, "str-kraski", "weight_kg", name) == Decimal(kg)


@pytest.mark.parametrize(
    "name",
    [
        "Грунтовка Ceresit 10л",
        "Грунт глубокого проникновения Оптимист G103 10 л",
        "Грунт-эмаль аэрозоль 3в1 черная 425мл ПРЕСТИЖ",
    ],
)
def test_volume_does_not_leak_into_weight(rules, name):
    """Литры и миллилитры в ось массы не попадают.

    Вес и объём у ЛКМ **не сводятся друг к другу**: плотность красок, грунтов и
    растворителей разная, и 10 кг грунта — это не 10 л. Ось объёма в БД
    отсутствует, поэтому 71 такой товар остаётся без фасовки, а не получает
    выдуманную массу.
    """
    assert _v(rules, "str-kraski", "weight_kg", name) is None


@pytest.mark.parametrize(
    "name",
    [
        "яяВанночка для краски 330х350мм,Hobbi",
        'Колер универсальный 001 черный 100 мл. "ПРЕСТИЖ"',
    ],
)
def test_tray_and_tint_are_not_paint_packaging(rules, name):
    """Ванночка — тара, колер — добавка; «кг» у них значило бы другое."""
    assert _v(rules, "str-kraski", "weight_kg", name) is None


# --- Ленты: ширина в мм и длина в метрах --------------------------------------


@pytest.mark.parametrize(
    ("name", "width", "length"),
    [
        ("яяЛента 48ммх50м малярная  FIT", "48", "50"),
        ('Лента 50ммх10м ЗУБР "ЭКСПЕРТ" "УНИВЕРСАЛ" армированная', "50", "10"),
        ("Лента алюминиевая самоклеящаяся 100ммх50м AVIORA DSAF", "100", "50"),
        ("Лента сигнальная 75 ммх250 м красно-белая PROCONNECT", "75", "250"),
    ],
)
def test_tape_width_and_length(rules, name, width, length):
    """«48ммх50м» — ширина в миллиметрах, длина в МЕТРАХ.

    Оси `tape_width` и `tape_length` уже существуют (заведены под рулетки), и
    единицы совпадают буква в букву — поэтому новые заводить не пришлось.
    """
    assert _v(rules, "hoz-lenty", "tape_width", name) == Decimal(width)
    assert _v(rules, "hoz-lenty", "tape_length", name) == Decimal(length)


@pytest.mark.parametrize(
    "name",
    [
        "Лента алюминиевая Изоспан FL Termo 50ммх50мкмх40п.",
        "Лента ТПЛ 50ммх30мкм упаковочная",
    ],
)
def test_microns_are_not_metres(rules, name):
    """«50мм**х50мкм**» — это ТОЛЩИНА в микронах, а не длина в метрах.

    На этом шаблон сначала ошибся: правая граница отсекала латинскую «k», а в
    «мкм» стоит кириллическая «к», и 50 мкм читались как 50 м. Здесь ось молчит
    целиком — у таких лент длина записана отдельно («40п.»), и выдумывать её
    нельзя.
    """
    assert _v(rules, "hoz-lenty", "tape_width", name) is None
    assert _v(rules, "hoz-lenty", "tape_length", name) is None


def test_tape_axes_claim_no_facet():
    """Ленты размазаны по шести категориям — фасет не заявляем.

    92 из 218 лежат в НЕАКТИВНОЙ категории 35 «Хозтовары», 79 в «Клеях», 16 в
    «Малярном», 15 в «Сантехнике». Ни в одной нет большинства, и фасет был бы
    заполнен на четверть. Значения живут в карточке товара; привязка — отдельное
    решение после разбора дерева.
    """
    import json

    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == "hoz-lenty")
    for axis in block["attributes"]:
        assert axis.get("bind") is False, axis["slug"]
