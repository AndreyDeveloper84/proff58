"""ДРФ-1459 (трек фасетов): три оси пневмоинструмента после разделения листа.

Лист 162 «Пневмоинструмент» держал 285 опубликованных товаров **шестнадцати**
типов и не имел ни одного фасета. Общей оси у них нет и быть не может: у
краскораспылителя это сопло, у гайковёрта момент, у шлифмашины диаметр круга,
у фитинга резьба. Самая крупная группа — 51 из 285, то есть ни одна ось не
взяла бы 50 % листа.

Поэтому лист сначала разделён по типу, и уже каждый новый лист получает свою
ось. Замер на стенде 2026-09-07:

* ``bp-kraskoraspyliteli`` → ``nozzle_diameter``  32/51 = 62 %, 10 значений;
* ``bp-pnevmogaikoverty``  → ``torque``           22/28 = 78 %, 21 значение;
* ``bp-pnevmoshlif``       → ``disc_diameter``    17/27 = 62 %,  8 значений.

``torque`` и ``disc_diameter`` — существующие оси каталога (183 и 1604
значения), новый только ``nozzle_diameter``.

Проверяемые границы (каждая найдена на реальных названиях):

1. **Единица момента пишется двумя алфавитами.** «1200Hm» и «420Hm» — латиница,
   «1100Нм» — кириллица. Обе формы обязаны читаться.
2. **Левая граница обязательна.** В «DGM DTP-1252, 125мм» без неё из модельного
   номера прочиталось бы «252».
3. **Цанга — не круг.** «ST-7733M 6 мм» это хвостовик 6 мм, и двузначный
   минимум его не пускает в ось диаметра.
4. **Объём бачка — не сопло.** «с верхним бачком V=1,0» это литры; голое
   дробное число без «мм» и без якоря «сопло» не берётся намеренно.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

NOZZLE = ("bp-kraskoraspyliteli", "nozzle_diameter")
TORQUE = ("bp-pnevmogaikoverty", "torque")
DISC = ("bp-pnevmoshlif", "disc_diameter")

CASES: list[tuple[tuple[str, str], str, str | None]] = [
    # --- сопло: якорная форма и форма с «мм» ---
    (NOZZLE, "Краскопульт пневматический KRAFTOOL AirKraft, 1,7мм с верхним бачком", "1.7"),
    (NOZZLE, "Краскопульт пневматический KRAFTOOL AirKraft HVLP, 1,4мм нижний бачок", "1.4"),
    (NOZZLE, "Краскопульт пневматический KRAFTOOL AIRKRAFT MINI сопло 1,0мм, бачок", "1.0"),
    (NOZZLE, "Краскопульт пневматический KRAFTOOL Jeta 3000 MINI сопло 0,8мм", "0.8"),
    (NOZZLE, "Набор покрасочный сопло 2,5мм MD-STARS верх пласт бачок", "2.5"),
    (NOZZLE, "Краскораспылитель PEGAS с верхним бачком 600мл сопло 2мм", "2"),
    # объём бачка в ось не попадает
    (NOZZLE, "Краскораспылитель пневмат. с верхним бачком V=1,0", None),
    (NOZZLE, "Краскораспылитель с верхним бачком Fubag 0,6 л.", None),
    # --- момент: кириллица и латиница ---
    (TORQUE, 'Пневмогайковерт ЗУБР ПГ-2500 ударный 1" 2500Нм', "2500"),
    (TORQUE, 'Пневмогайковерт KRAFTOOL PW-900 ударный 1/2" 880Нм', "880"),
    (TORQUE, 'Пневмогайковерт Einhell TC-PR 68, угловой 68Нм, 1/2"', "68"),
    (TORQUE, 'Пневмогайковерт OMP11212  (1/2" 1200Hm 7000 об/мин)', "1200"),
    (TORQUE, "Пневмогайковерт PEGAS TP-002K, 420Hm, 7000 об/мин", "420"),
    (TORQUE, 'Пневмогайковерт ST 55881-8 (1" 2439 Нм вал 8" 566', "2439"),
    # модельный номер без единицы оси не даёт
    (TORQUE, "Пневмогайковерт ИП-3126", None),
    (TORQUE, 'Пневмогайковерт Black Horn AT-3921 ударный 1/2"', None),
    # --- диаметр круга ---
    (DISC, "Пневмошлифмашина орбитальная DGM DTP-1252, 125мм, 180 л/мин, 6 бар", "125"),
    (DISC, "Пневмошлифмашина ИП-21230 ф230мм 8000об/мин, 6,3бар", "230"),
    (DISC, "Пневмошлифмашина прямая ИП-2015 ф100мм", "100"),
    (DISC, "Пневмошлифмашина угловая SUMAKE ST-7737 ф 125мм", "125"),
    (DISC, "Пневмошлифмашина ИП-2009Б круг 63мм", "63"),
    (DISC, "Пневмошлифмашина орбитальная ST-7716 200 мм Sumake", "200"),
    # цанга 6 мм — не круг; модельный номер — не диаметр
    (DISC, "Пневмошлифмашина прямая ST-7733M 6 мм Sumake", None),
    (DISC, "Пневмошлифмашина угловая Fubag GA125 (184 л/мин_6.", None),
]


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _num(rules: AttributeRules, tool_type: str, axis: str, name: str):
    for v in rules.extract(tool_type, name):
        if v.slug == axis:
            return v.number
    return None


@pytest.mark.parametrize("pair,name,expected", CASES, ids=[f"{p[1]}:{n[:34]}" for p, n, _ in CASES])
def test_pneumatic_axes_from_real_names(rules, pair, name, expected):
    tool_type, axis = pair
    got = _num(rules, tool_type, axis, name)
    if expected is None:
        assert got is None, f"ложное срабатывание: {got}"
    else:
        assert got == Decimal(expected)


def test_torque_unit_in_both_alphabets(rules):
    """«Hm» латиницей и «Нм» кириллицей — одна и та же единица."""
    tt, ax = TORQUE
    assert _num(rules, tt, ax, "Пневмогайковерт X 1200Hm") == Decimal(1200)
    assert _num(rules, tt, ax, "Пневмогайковерт X 1200Нм") == Decimal(1200)


def test_left_boundary_blocks_model_number(rules):
    """«DTP-1252» не должен дать 252 в диаметр — левая граница держит."""
    tt, ax = DISC
    assert _num(rules, tt, ax, "Пневмошлифмашина DGM DTP-1252, 125мм") == Decimal(125)


def test_collet_is_not_a_disc(rules):
    """6 мм у прямой машины — цанговый хвостовик, а не круг."""
    tt, ax = DISC
    assert _num(rules, tt, ax, "Пневмошлифмашина прямая ST-7733M 6 мм Sumake") is None


def test_tank_volume_is_not_a_nozzle(rules):
    """«V=1,0» и «0,6 л» — объём бачка; ось сопла обязана молчать."""
    tt, ax = NOZZLE
    assert _num(rules, tt, ax, "Краскораспылитель с верхним бачком V=1,0") is None
    assert _num(rules, tt, ax, "Краскораспылитель Fubag 0,6 л. верхний бачок") is None


def test_each_axis_yields_at_least_two_values(rules):
    """Правило DRF-1428: ось с одним значением фасетом быть не может."""
    for pair in (NOZZLE, TORQUE, DISC):
        tt, ax = pair
        vals = {_num(rules, tt, ax, n) for p, n, e in CASES if p == pair and e is not None}
        assert len(vals - {None}) >= 2, ax
