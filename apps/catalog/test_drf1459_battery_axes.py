"""ДРФ-1459 (трек фасетов): напряжение и ёмкость у листа «Аккумуляторы».

Лист 393 не имел фасета при 88 опубликованных товарах. Обе оси
**существующие** — ``voltage`` (457 значений) и ``battery_capacity`` (330);
новых атрибутов не заводим.

Замер на стенде 2026-09-07 по типу ``akkumulyatory`` (67 опубликованных):
напряжение 55 = 82 %, ёмкость 54 = 80 %. По листу это 61 % и 60 % — обе выше
порога DRF-1428.

Проверяемые границы:

1. **Единица напряжения пишется тремя способами.** «18В» кириллицей, «18 V»
   латиницей и «36B» латинской B, которая выглядит как русская В.
2. **Правая граница обязательна.** Без неё «Unibattery-1BatterySystem» дал бы
   напряжение 1: там есть «1b» внутри слова.
3. **Амперы — не ампер-часы.** «EB1414 1.4 А» это ток, ёмкость обязана молчать.
4. **Тип ячейки осью не становится.** Li-ion / Ni-Cd / Ni-MH берут только 45 %
   листа — ниже порога, ось не заводится.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

TOOL_TYPE = "akkumulyatory"
V, C = "voltage", "battery_capacity"

CASES: list[tuple[str, str, str | None, str | None]] = [
    # название, ось, напряжение, ёмкость
    ("Аккумулятор ЗУБР ST7-20-4 20В Li-ion 4 А/ч Профессионал", "", "20", "4"),
    ("Аккумулятор Hanskonner 18В 6,0А/ч серия PLATINUM SAMSUNG", "", "18", "6.0"),
    ("Аккумулятор HITACHI BSL1430; 14,4 V, 3,0 Ah, Li-ion", "", "14.4", "3.0"),
    ("Аккумулятор HITACHI BSL3626 36B 2.6 Ah Li-Ion", "", "36", "2.6"),
    ("Аккумулятор HITACHI EBM 315 3.6V 1.5Ah Li-Ion", "", "3.6", "1.5"),
    ("Аккумулятор STURM SBP1802. 18В, 2,0а/ч", "", "18", "2.0"),
    ("Аккумулятор для пилы ПОБЕДА ПА 150, 14,4в 1,5Ач", "", "14.4", "1.5"),
    # ток, а не ёмкость
    ("Аккумулятор СЕБ аналог HITACHI EB1414  1.4 А", "", None, None),
    # напряжение зашито в модель — ось молчит
    ("Аккумуляторная батарея Delta DT 1207", "", None, None),
    ("Аккумулятор ЗУБР ЗАКБ-14,4-ЛИ", "", None, None),
    # mAh не наша единица
    ("Аккумулятор Panasonic EVOLTA P06 2050 mAh 2BL", "", None, None),
]


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _val(rules: AttributeRules, axis: str, name: str):
    for v in rules.extract(TOOL_TYPE, name):
        if v.slug == axis:
            return v.number
    return None


@pytest.mark.parametrize("name,_axis,volt,cap", CASES, ids=[n[:42] for n, _, _, _ in CASES])
def test_battery_axes_from_real_names(rules, name, _axis, volt, cap):
    got_v = _val(rules, V, name)
    got_c = _val(rules, C, name)
    assert got_v == (Decimal(volt) if volt else None), f"напряжение: {got_v}"
    assert got_c == (Decimal(cap) if cap else None), f"ёмкость: {got_c}"


def test_voltage_unit_in_three_spellings(rules):
    """«18В» кириллицей, «18 V» латиницей, «36B» латинской B."""
    assert _val(rules, V, "Аккумулятор X 18В Li-ion") == Decimal(18)
    assert _val(rules, V, "Аккумулятор X 18 V Li-ion") == Decimal(18)
    assert _val(rules, V, "Аккумулятор X 36B Li-Ion") == Decimal(36)


def test_right_boundary_blocks_word_interior(rules):
    """«Unibattery-1BatterySystem» не должен дать напряжение 1."""
    name = "Адаптер-переходник для аккумуляторов Hanskonner Unibattery-1BatterySystem"
    assert _val(rules, V, name) is None


def test_amperes_are_not_amp_hours(rules):
    """«1.4 А» — ток; ёмкость обязана молчать."""
    assert _val(rules, C, "Аккумулятор СЕБ аналог HITACHI EB1414  1.4 А") is None


def test_cell_chemistry_is_not_an_axis(rules):
    """Li-ion / Ni-Cd брали бы 45 % листа — ниже порога, оси нет."""
    slugs = {r.slug for r in rules.rules_for(TOOL_TYPE)}
    assert slugs == {V, C}, slugs


def test_each_axis_yields_at_least_two_values(rules):
    """Правило DRF-1428: ось с одним значением фасетом быть не может."""
    for axis, idx in ((V, 2), (C, 3)):
        vals = {_val(rules, axis, n) for n, _, v, c in CASES if (v if idx == 2 else c)}
        assert len(vals - {None}) >= 2, axis
