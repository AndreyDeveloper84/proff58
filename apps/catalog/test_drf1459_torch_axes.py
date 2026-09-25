"""ДРФ-1459 (трек фасетов): «Тип фонаря» и «Питание» у листа 382 «Фонари».

Лист (164 опубликованных) не имел ни одного своего фасета — панель наследовала
от 381 «Электрика и освещение» только «Тип инструмента».

Числовые оси мерены на стенде 2026-09-07 и отвергнуты: световой поток 30 %,
число светодиодов 32 %, мощность 26 %, число режимов 30 % — все ниже порога
DRF-1428. Порог берут две select-оси: ``torch_type`` 52 % и ``power_source``
62 %.

``power_source`` — ось **существующая** (1339 значений, объявлена в 10 блоках
электроинструмента с вариантами «Аккумулятор» и «Сеть»). Новый атрибут не
заводится: добавляется третий вариант «Батарейки».

Проверяемые границы:

1. **Порядок вариантов ``power_source`` повторяет блоки электроинструмента.**
   ``sort_order`` выводится из позиции в массиве; переставь их — и фасет
   «Питание» поехал бы во всём электроинструменте (защита PR #658 ловит это
   как ``sort_diff``, но правильный порядок дешевле).
2. **«Сеть» намеренно без ключевых слов.** Фонарь с «ЗУ 220В» питается от
   аккумулятора, 220 В относятся к зарядке. Вариант нужен только чтобы удержать
   порядок, срабатывать он не должен никогда.
3. **«фара» — это прожектор, а не автолампа.** «Фонарь Трофи TSP10 фара 15хLED,
   аккум, з/у 220В» — аккумуляторная фара-прожектор.
4. **Значения «Ручной» в оси НЕТ.** Явно названы ручными 8 позиций при ~70
   безымянных ручных фонарях в листе: «Ручной» отдавал бы 8 из 70.
5. **Лампочка — не фонарь.** «Лампочка для фонарика Hitachi» лежит в листе, но
   осей получать не должна ни одной.
"""

from __future__ import annotations

import json

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

FON, PROZH = "fonari", "prozhektory"
TYPE, PWR = "torch_type", "power_source"

# название → (тип фонаря, питание); None — ось обязана молчать.
CASES: list[tuple[str, str | None, str | None]] = [
    ("Фонарь KRAFTOOL KH-7 налобный аккум 1000лм, 4 режима, 2200мАч", "nalobnyy", "battery"),
    ("Фонарь KRAFTOOL KH-3 налобный 500лм, 5 режимов, 3ААА", "nalobnyy", "batteries"),
    ("Фонарь FIT на голову 10LED", "nalobnyy", None),
    ("Фонарь ЭРА  K48 кемпинг НЛО, 48хLED, 3хR6", "kempingovyy", "batteries"),
    ("Фонарь ЭРА  PA-602 прожектор АЛЬФА 19хLED, литий 3", "prozhektor", "battery"),
    ("Фонарь Трофи TSP10 фара 15хLED, аккум, з/у 220В", "prozhektor", "battery"),
    ("Фонарь ЭРА  WL48 авто12V, 48хLED, 3 метра", "avtomobilnyy", None),
    ("Фонарь ЭРА  A5M АВТОСПАСАТЕЛЬ 4в1", "avtomobilnyy", None),
    ("Фонарь ЭРА  BC19 вело, 19LED", "velosipednyy", None),
    ("Фонарь Трофи TK49, наст лампа 49LED", "nastolnyy", None),
    ("Фонарь сигнальный ФС-12", "signalnyy", None),
    ("Фонарь ЭРА  B26 брелок", "brelok", None),
    ("Фонарь ЭРА SDA30M 5хLED, 220V, NiMH", None, "battery"),
    ("Фонарь Camelion LED 5313-19F4ML (3xR03)19LED 4 реж", None, "batteries"),
]


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _slug(rules: AttributeRules, tool_type: str, axis: str, name: str) -> str | None:
    for v in rules.extract(tool_type, name):
        if v.slug == axis:
            return v.option_slug
    return None


@pytest.mark.parametrize("name,kind,power", CASES)
def test_both_axes_read_the_name(rules, name, kind, power):
    """Обе оси читаются из названия одинаково у фонарей и прожекторов."""
    assert _slug(rules, FON, TYPE, name) == kind
    assert _slug(rules, FON, PWR, name) == power
    assert _slug(rules, PROZH, TYPE, name) == kind
    assert _slug(rules, PROZH, PWR, name) == power


def test_mains_never_fires_for_a_torch(rules):
    """«Сеть» без ключевых слов: 220 В у фонаря — это зарядка, а не питание."""
    for name in (
        "Фонарь Трофи TG9 аккум. налобный 9xLED, ЗУ 220V",
        "Фонарь Трофи TSP12 фара 12+18хLED, аккум, з/у 220В",
        "Фонарь ЭРА SDA50M 6хLED, 220V, NiMH",
        "Фонарь ЭРА  PA-604 прожектор АЛЬФА 9х18хLED SMD, литий 3Ач, ЗУ 220В+12В",
    ):
        assert _slug(rules, FON, PWR, name) != "mains"


def test_power_source_option_order_matches_power_tool_blocks(rules):
    """Порядок вариантов обязан совпадать с блоками электроинструмента.

    ``sort_order`` выводится из позиции в массиве ``options``. Переставь
    «Аккумулятор» и «Сеть» — и порядок значений в фасете «Питание» поехал бы у
    дрелей, перфораторов и всего остального электроинструмента.
    """
    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    order_by_block: dict[str, list[str]] = {}
    for block in data["tool_types"]:
        for a in block["attributes"]:
            if a["slug"] == PWR:
                order_by_block[block["tool_type"]] = [o["slug"] for o in a["options"]]

    assert order_by_block["dreli-shurupoverty"] == ["battery", "mains"]
    for tool_type in (FON, PROZH):
        assert order_by_block[tool_type][:2] == ["battery", "mains"], tool_type
        assert order_by_block[tool_type][2] == "batteries", tool_type


def test_batteries_is_a_new_option_not_a_new_axis(rules):
    """Ось существующая: заводим вариант, а не второй атрибут «Питание»."""
    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    names = {a["name"] for b in data["tool_types"] for a in b["attributes"] if a["slug"] == PWR}
    assert names == {"Питание"}, names


def test_searchlight_is_not_a_car_lamp(rules):
    """«фара» ведёт в «Прожектор»: это аккумуляторная фара-прожектор."""
    assert _slug(rules, FON, TYPE, "Фонарь Трофи TSP19 фара 19+18xLED аккум з/у 220В") == (
        "prozhektor"
    )
    assert _slug(rules, FON, TYPE, "Фонарь ЭРА ПРАКТИК AA-701 автомобильный 7,3Вт СОВ") == (
        "avtomobilnyy"
    )


def test_no_generic_hand_torch_value(rules):
    """«Ручной» осью не становится: 8 названных против ~70 безымянных.

    Безымянный фонарь обязан дать честный ноль, а не попасть в ведро, которое
    показывает покупателю восьмую часть того, что он ищет.
    """
    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == FON)
    axis = next(a for a in block["attributes"] if a["slug"] == TYPE)
    slugs = [o["slug"] for o in axis["options"]]
    assert "ruchnoy" not in slugs, slugs

    for name in (
        "Фонарь ЭРА  SD17  17 св.диод, алюминий, 3хAAA",
        "Фонарь КОСМОС ручной аккумул 1Вт LED+5ВСОВ",
        "Фонарь GARIN TS-1W трансформер",
    ):
        assert _slug(rules, FON, TYPE, name) is None


def test_bulb_for_a_torch_is_not_a_torch(rules):
    """Расходник в листе не должен получить ни одной оси."""
    for name in (
        "Лампочка для фонарика Hitachi 14-18V 318-767",
        "Лампочка для фонарика Hitachi 9-12V 314-424",
    ):
        assert _slug(rules, FON, TYPE, name) is None
        assert _slug(rules, FON, PWR, name) is None


def test_floodlight_block_binds_to_the_torch_leaf(rules):
    """У блока прожекторов своей категории нет — адрес задан у осей.

    Товары типа ``prozhektory`` в основном живут в листе 385 «Светильники и
    прожекторы» (62 позиции); «Тип фонаря» там был бы одноголосым фасетом.
    Привязка нужна только к листу 382.
    """
    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    fon = next(b for b in data["tool_types"] if b["tool_type"] == FON)
    prozh = next(b for b in data["tool_types"] if b["tool_type"] == PROZH)

    assert fon["category"] == "Фонари"
    assert "category" not in prozh
    assert all(a["category"] == "Фонари" for a in prozh["attributes"])


def test_each_axis_yields_at_least_two_values():
    """Правило DRF-1428: ось с одним значением фасетом быть не может."""
    assert len({k for _, k, _ in CASES if k}) >= 2
    assert len({p for _, _, p in CASES if p}) >= 2
