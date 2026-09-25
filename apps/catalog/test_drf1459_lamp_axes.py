"""ДРФ-1459 (трек фасетов): четыре оси листа 384 «Лампы».

Лист (132 опубликованных) не имел ни одного своего фасета — панель наследовала
от 381 «Электрика и освещение» только «Тип инструмента». Лист чистый: два типа
(``lampy`` 126 и ``perenoski`` 6), ноль без типа, за пределами листа только
мёртвый узел 47.

Замер на стенде 2026-09-08 по типу ``lampy``: цоколь **96 %**, цветовая
температура **92 %**, мощность **88 %**, форма колбы **80 %**.

Ось «тип лампы» брала бы 98 %, но не заводится: 114 значений из 130 —
«Светодиодная». Фасет с такой доминантой фильтром не работает.

Проверяемые границы:

1. **Порядок опций цоколя решает конкретную ловушку.** «Лампа Camelion Basic
   power **G45** LED 8Вт,3000К, **Е14**» несёт форму колбы G45, внутри которой
   лежит подстрока «g4». E27 и E14 стоят выше G4, иначе лампа с цоколем Е14
   ушла бы в G4.
2. **Кириллическая «Е» и латинская «E» — обе.** 1С пишет и так и так, а
   нормализация регистра их не сводит.
3. **Цветовая температура записана ЧЕТЫРЬМЯ способами:** прямое «3000К»,
   сокращение Ресанты «-3K-», кодировка 8xx (827 = 2700 K), голое «2700».
4. **Порядок шаблонов температуры значим:** 8xx выше голого числа, иначе
   «A60-10W-827-E27» дало бы 827 кельвинов.
5. **«1000W» — это ватты, а не кельвины.** У голого числа стоит запрет
   «не ватты и не вольты».
6. **Запятая в «12Вт,3000К» разделяет поля, а не дробь.** Простой запрет
   любого знака перед числом терял бы температуру у всей серии Camelion.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

TT = "lampy"
SOCK, PWR, TEMP, SHAPE = "socket", "power", "color_temperature", "bulb_shape"

# название → (цоколь, мощность, температура, форма); None — ось обязана молчать.
CASES: list[tuple[str, str | None, str | None, str | None, str | None]] = [
    ("Лампа Camelion Basic power A60 LED 12Вт,3000К, Е27", "e27", "12", "3000", "grusha"),
    ("Лампа Camelion Basic power A65 LED 17Вт,6500К, Е27", "e27", "17", "6500", "grusha"),
    ("Лампа Camelion Basic power C35 LED 8Вт,4500К, Е14", "e14", "8", "4500", "svecha"),
    ("Лампа Camelion Basic power G45 LED 8Вт,3000К, Е14", "e14", "8", "3000", "shar"),
    ("Лампа Gauss LED Elementary G4 1W 4100К", "g4", "1", "4100", None),
    ("Лампа Gauss LED Elementary MR16 3W GU10 2700K", "gu10", "3", "2700", "reflektor"),
    ("Лампа Gauss LED R50 2,5W Е14 4100K", "e14", "2.5", "4100", "reflektor"),
    ("Лампа ЭРА LED sdm A60-10W-827-E27", "e27", "10", "2700", "grusha"),
    ("Лампа ЭРА LED sdm A65-13W-840-E27", "e27", "13", "4000", "grusha"),
    ("Лампа ЭРА LED sdm MR16-8W-842-GU5.3", "gu5-3", "8", "4200", "reflektor"),
    (
        "Лампа светодиодная Ресанта LL-R-A60-11W-230-3K-E27 (груша, 11Вт, тепл Е27)",
        "e27",
        "11",
        "3000",
        "grusha",
    ),
    (
        "Лампа светодиодная Ресанта LL-R-C37- 6W-230-4K-E14 (свеча, 6Вт, нейтр Е14)",
        "e14",
        "6",
        "4000",
        "svecha",
    ),
    ("Лампа Camelion Braght power G45 LED 4,5/845/Е14", "e14", None, "4500", "shar"),
    ("Лампа ES ESL-CL11-2700 E14 энергосберегающая", "e14", None, "2700", None),
    ("Лампа ECOLA Light T8 G13 LED 6500К", "g13", None, "6500", "trubka"),
    ("Лампа ДРВ 250Вт Е40 TDM ртутная прямого включения", "e40", "250", None, None),
]


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _val(rules: AttributeRules, axis: str, name: str):
    for v in rules.extract(TT, name):
        if v.slug == axis:
            return v.option_slug or v.number
    return None


@pytest.mark.parametrize("name,socket,power,temp,shape", CASES)
def test_name_yields_four_axes(rules, name, socket, power, temp, shape):
    """Четыре оси читаются из названия лампы."""
    assert _val(rules, SOCK, name) == socket
    assert _val(rules, PWR, name) == (None if power is None else Decimal(power))
    assert _val(rules, TEMP, name) == (None if temp is None else Decimal(temp))
    assert _val(rules, SHAPE, name) == shape


def test_shape_code_g45_is_not_socket_g4(rules):
    """Главная ловушка цоколя: «G45» — форма колбы, внутри неё подстрока «g4».

    E27 и E14 стоят выше G4 в списке опций. При обратном порядке лампа с
    цоколем Е14 ушла бы в цоколь G4.
    """
    for name in (
        "Лампа Camelion Basic power G45 LED 10Вт,3000К, Е27",
        "Лампа Camelion Basic power G45 LED 8Вт,4500К, Е14",
        "Лампа Gauss LED Elementary Globe 6W E14 2700K",
    ):
        assert _val(rules, SOCK, name) in ("e14", "e27"), name

    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == TT)
    axis = next(a for a in block["attributes"] if a["slug"] == SOCK)
    order = [o["slug"] for o in axis["options"]]
    assert order.index("e27") < order.index("g4")
    assert order.index("e14") < order.index("g4")


def test_cyrillic_and_latin_e_are_both_listed(rules):
    """1С пишет цоколь и кириллической «Е», и латинской «E»."""
    assert _val(rules, SOCK, "Лампа Camelion LED 12Вт Е27") == "e27"  # кириллица
    assert _val(rules, SOCK, "Лампа Ecola Reflector R39 LED 5.2W E14 4200K") == "e14"  # латиница


def test_temperature_is_written_four_ways(rules):
    """Один и тот же признак записан четырьмя способами."""
    assert _val(rules, TEMP, "Лампа Gauss LED Candle 3W E14 2700K") == Decimal("2700")
    assert _val(rules, TEMP, "Лампа Ресанта LL-R-A80-20W-230-4K-E27") == Decimal("4000")
    assert _val(rules, TEMP, "Лампа ЭРА LED sdm B35-7W-842-E14") == Decimal("4200")
    assert _val(rules, TEMP, "Лампа ES ESL-T2HS15-4000 E14 энергосберегающая") == Decimal("4000")


def test_code_pattern_wins_over_the_bare_number(rules):
    """8xx обязана идти выше голого числа: иначе 827 стало бы 827 кельвинами."""
    assert _val(rules, TEMP, "Лампа ЭРА LED sdm A65-13W-827-E27") == Decimal("2700")
    assert _val(rules, TEMP, "Лампа ЭРА LED sdm P45-7W-842-E14") == Decimal("4200")

    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == TT)
    axis = next(a for a in block["attributes"] if a["slug"] == TEMP)
    kinds = [p if isinstance(p, str) else p["pattern"] for p in axis["regex"]]
    assert kinds.index(r"(?<!\d)8(\d\d)(?!\d)") < kinds.index(
        r"(?<!\d)(\d{4})(?!\d)(?!\s*(?:вт|w|в))"
    )


def test_watts_are_not_kelvin(rules):
    """«1000W» — мощность галогенки, а не цветовая температура."""
    name = "Лампа Camelion J 1000W 220В, 189мм галогеновая"
    assert _val(rules, PWR, name) == Decimal("1000")
    assert _val(rules, TEMP, name) is None


def test_comma_is_a_field_separator_not_a_decimal_point(rules):
    r"""«12Вт,3000К» — запятая разделяет поля.

    Простой запрет любого знака перед числом («(?<![\d.,])») терял бы
    температуру у всей серии Camelion Basic power.
    """
    assert _val(rules, TEMP, "Лампа Camelion Basic power A65 LED 15Вт,4500К, Е27") == Decimal(
        "4500"
    )
    assert _val(rules, TEMP, "Лампа Camelion Basic power C35 LED4 4Вт,3000К, Е14") == Decimal(
        "3000"
    )


def test_lamp_type_axis_is_not_declared(rules):
    """«Тип лампы» брала бы 98 %, но 114 из 130 — «Светодиодная».

    Фасет, у которого одно значение покрывает 88 % листа, фильтром не работает.
    """
    assert {r.slug for r in rules.rules_for(TT)} == {SOCK, PWR, TEMP, SHAPE}


def test_each_axis_yields_at_least_two_values():
    """Правило DRF-1428: ось с одним значением фасетом быть не может."""
    for idx in (1, 2, 3, 4):
        vals = {c[idx] for c in CASES if c[idx]}
        assert len(vals) >= 2, idx
