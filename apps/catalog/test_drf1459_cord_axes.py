"""ДРФ-1459 (трек фасетов): оси листа 383 «Удлинители и сетевые фильтры».

Лист разобран по решению владельца 2026-09-08. Он был свалкой по слову
«удлинитель»: из 172 опубликованных позиций электрическими были 84, а остальные
— оснастка под квадрат головок (удлинители 1/2, 3/4, 1/4), удлинители алмазных
и буровых коронок, оснастка буров и шнеков, держатели бит, штанги для валиков и
дренажные шланги. Все они несли **один и тот же неверный** ``tool_type``
``udliniteli-filtry``. 122 позиции перетипизированы и разведены по семи листьям;
новых типов не заводилось — все цели уже были в манифесте.

| ось | смешанный лист (172) | очищенный (89) |
|---|---|---|
| длина кабеля | 43 % | **77 %** |
| сечение | — | **65 %** |
| число гнёзд | 30 % | **58 %** |
| мощность | 23 % | 44 % — ниже порога, ось не заводится |

Проверяемые границы:

1. **Длина кабеля — отдельная ось, а не существующая ``length``.** Та в
   МИЛЛИМЕТРАХ (2685 значений), и «50» метров в ней испортило бы фасет во всех
   листьях, где она уже живёт. Образец — ``tape_length`` «Длина ленты» в метрах.
2. **Правая граница обязательна.** Без неё «75 мм» у оставшихся в листе
   неэлектрических позиций прочиталось бы как 75 метров.
3. **Сечение — select, а не пара чисел.** 1С пишет один и тот же кабель
   четырьмя способами: «3х2,5», «3*2,5», «3x2,5», «3 х 2,5».
4. **Порядок опций сечения значим:** «2×1,5» выше «2×1», иначе общее ведро
   съело бы частное.
5. **Число гнёзд читается и из «мест».** «Удлинитель 2-мест 7м» — двухместный.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

TT = "udliniteli-filtry"
LEN, SEC, SOCK = "cable_length", "cable_section", "socket_count"

# название → (длина, сечение, гнёзд); None — ось обязана молчать.
CASES: list[tuple[str, str | None, str | None, str | None]] = [
    (
        "Удлинитель на катушке 30 м, КГ 3х2,5, 4000 Вт, 4 гнезда, IP44, ЗУБР Профессионал",
        "30",
        "3x2-5",
        "4",
    ),
    ("Удлинитель на рамке ТМСоюз ПВС 2*0,75 1гн 10 м. 1300Вт", "10", "2x0-75", "1"),
    ("Удлинитель 2-мест 7м с/з (ПВС3*0,75) У10-553", "7", "3x0-75", "2"),
    ("Удлинитель сетевой 10 м ПВС 2*2,5 1 роз", "10", "2x2-5", "1"),
    (
        "Удлинитель силовой 4 роз. с/з, 50м (мет.кат.), 16А, 220В, ПВС 3х2,5 (синий) 14227",
        "50",
        "3x2-5",
        "4",
    ),
    ("Удлинитель на катушке 50 м, КГ 4х1,5, 1 розетка 3-х фазный", "50", "4x1-5", "1"),
    ("Удлинитель силовой 10 м, КГ 3х1,5, 3700 Вт, IP44, STAYER 1 гнездо", "10", "3x1-5", "1"),
    ("Удлинитель Е-304 (10м)", "10", None, None),
    ("Удлинитель Е-302 (3м)", "3", None, None),
    ("Удлинитель 2-х мест.10м ШВВП 2*0,75) У6-011", "10", "2x0-75", "2"),
    ("Удлинитель на кат.ВЕМ-250 термо 4-х мест.ПВС-3*0,7", None, "3x0-75", "4"),
]


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _val(rules: AttributeRules, axis: str, name: str):
    for v in rules.extract(TT, name):
        if v.slug == axis:
            return v.option_slug or v.number
    return None


@pytest.mark.parametrize("name,length,section,sockets", CASES)
def test_name_yields_all_three_axes(rules, name, length, section, sockets):
    """Три оси читаются из названия электрического удлинителя."""
    assert _val(rules, LEN, name) == (None if length is None else Decimal(length))
    assert _val(rules, SEC, name) == section
    assert _val(rules, SOCK, name) == (None if sockets is None else Decimal(sockets))


def test_millimetres_are_not_metres(rules):
    """Главная ловушка: «100мм» и «75 мм» — не сто и не семьдесят пять метров.

    В листе остались неэлектрические позиции, разобрать которые по типу не
    удалось. Без правой границы они получили бы длину кабеля в метрах.
    """
    for name in (
        'Удлинитель 1" 100мм ударный JTC',
        'Удлинитель 3/8"х75 мм ДТ',
        "Удлинитель с шарниром 250мм FORCE",
        "Удлинитель профиля 60х27",
    ):
        assert _val(rules, LEN, name) is None, name


def test_cable_length_is_its_own_axis_not_the_millimetre_one():
    """``length` в миллиметрах — писать в неё метры нельзя.

    У оси 2685 значений в других листьях; «50» метров испортило бы их фасет.
    Образец правильного решения — ``tape_length`` «Длина ленты» в метрах.
    """
    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == TT)
    slugs = {a["slug"] for a in block["attributes"]}
    assert "length" not in slugs, "метры в миллиметровую ось писать нельзя"
    axis = next(a for a in block["attributes"] if a["slug"] == LEN)
    assert axis["unit"] == "м"


def test_section_normalises_four_spellings(rules):
    """1С пишет один кабель четырьмя способами — фасет обязан свести их в одно."""
    for name in (
        "Удлинитель на катушке 30 м, КГ 3х2,5, 4000 Вт",
        "Удлинитель на катушке с 4гн. ТМ СОЮЗ КГ 3*2,5 4000Вт 30м",
        "Сетевой фильтр Volsten 3x2,5",
        "Удлинитель ПВС 3 х 2,5 30м",
    ):
        assert _val(rules, SEC, name) == "3x2-5", name


def test_section_option_order_specific_before_general(rules):
    """«2×1,5» стоит выше «2×1»: иначе общее ведро съело бы частное."""
    assert _val(rules, SEC, "Удлинитель ПВС 2*1,5 3500Вт 20м") == "2x1-5"
    assert _val(rules, SEC, "Удлинитель ПВС 2*1 1гн 10 м. 2200Вт") == "2x1"

    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == TT)
    axis = next(a for a in block["attributes"] if a["slug"] == SEC)
    order = [o["slug"] for o in axis["options"]]
    assert order.index("2x1-5") < order.index("2x1")
    assert order.index("3x1-5") < order.index("3x1")


def test_sockets_read_from_mest_too(rules):
    """«2-мест» и «4-х мест» — это тоже число гнёзд."""
    assert _val(rules, SOCK, "Удлинитель 2-мест 7м с/з (ПВС3*0,75)") == Decimal("2")
    assert _val(rules, SOCK, "Удлинитель 3-х мест 3м ШВВП 2*0,75") == Decimal("3")


def test_power_axis_is_not_declared(rules):
    """Мощность 44 % — ниже порога DRF-1428, ось не заводится."""
    assert {r.slug for r in rules.rules_for(TT)} == {LEN, SEC, SOCK}


def test_each_axis_yields_at_least_two_values():
    """Правило DRF-1428: ось с одним значением фасетом быть не может."""
    assert len({x for _, x, _, _ in CASES if x}) >= 2
    assert len({x for _, _, x, _ in CASES if x}) >= 2
    assert len({x for _, _, _, x in CASES if x}) >= 2


def test_dot_is_a_word_separator_not_a_decimal_point(rules):
    r"""«мест.10м» — точка разделяет слова, а не дробь.

    Простой запрет любого знака перед числом («(?<![\d.,])») терял длину у
    «Удлинитель 2-х мест.10м ШВВП». Запрещаются цифра и связка
    «цифра+разделитель», то есть хвост дроби «3,10м», но не «мест.10м».
    """
    assert _val(rules, LEN, "Удлинитель 2-х мест.10м ШВВП 2*0,75) У6-011") == Decimal("10")
    assert _val(rules, LEN, "Удлинитель 2-х мест. 2м (ПВС 2*0,75) У6-011М") == Decimal("2")
    assert _val(rules, LEN, "Удлинитель кабель 3,10м") is None
