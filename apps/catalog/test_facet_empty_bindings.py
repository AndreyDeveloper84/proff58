"""Трек привязок фасетов: ось объявлена, привязана — и не извлекает ничего.

Замер на стенде показал **15 привязок, висящих вхолостую**: `CategoryAttribute`
есть, а значений в поддереве ноль. Для покупателя это панель фильтра, которая
ничего не фильтрует.

Причины оказались разными, и лечение у них противоположное:

* `power_hp` (5 привязок) — ось объявлена в правилах **без единого шаблона
  извлечения**. `load_attributes` честно создал привязку, а извлекать было нечем.
  Лечится шаблоном — этим файлом.
* `spindle_thread`, `mount`, `purpose`, `saw_for` — величины **не пишутся в 1С
  вовсе** (проверено: «М14/М10» в названиях болгарок — 0 совпадений из 76).
  Шаблон тут не поможет: лечение — снять привязку, а это удаление с витрины.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

BLOCKS = ["bp-benzopily", "bp-trimmery", "bp-generatory", "bp-motobloki", "bp-motopompy"]


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _hp(rules: AttributeRules, tt: str, name: str):
    for v in rules.extract(tt, name):
        if v.slug == "power_hp":
            return v.number
    return None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ('Бензопила CS30EH; 12", 34см3, 1,32кВт/1,8л.с. бак', "1.8"),
        ("Бензопила Husqvarna 120 Mark II (1.5кВт/2.0 л.с., X-TORQ, 14'', SN", "2.0"),
        ('Бензопила Hanskonner HGC2020 2,0кВт/2,7л.с. 52см3, 18"', "2.7"),
        ('Бензопила Husqvarna 135-16" 40,9см3, 1,4кВт/1,9л.с', "1.9"),
    ],
)
def test_horsepower_is_read_from_the_pair(rules, name, expected):
    """Мощность почти всегда записана парой «1,32кВт/1,8л.с.» — берём л.с.

    Ось называется «Мощность двигателя» с единицей **л.с.**, поэтому киловатты в
    неё писать нельзя, хотя их в названиях вдвое больше (130 товаров против 65).
    """
    assert _hp(rules, "bp-benzopily", name) == Decimal(expected)


@pytest.mark.parametrize(
    "name",
    [
        'Бензопила CHAMPION 237-16"-3/8-1,3-56 (1,5кВт 37,2см3, дегкий старт 4,7к',
        "Бензокоса CG27EAS;  двиг 27см3, 0,88кВт, прям. вал",
        "Электрогенератор CARVER PPG- 6500Е (LT-188F, 5,0/5,5кВт, 220В, бак 25л,",
    ],
)
def test_kilowatts_alone_do_not_fill_the_horsepower_axis(rules, name):
    """Где производитель написал только кВт — ось молчит, а не конвертирует.

    Пересчёт кВт в л.с. дал бы производную величину, которой в названии нет;
    покупатель сравнивал бы вычисленное с паспортным и видел расхождение.
    """
    tt = "bp-benzopily" if "Бензопила" in name else "bp-trimmery"
    assert _hp(rules, tt, name) is None


@pytest.mark.parametrize("tt", BLOCKS)
def test_every_bp_block_declaring_the_axis_can_extract_it(rules, tt):
    """Главный инвариант: ось, объявленная в блоке, обязана уметь извлекать.

    Именно нарушение этого правила и создало пять пустых фасетов —
    `power_hp` был объявлен во всех пяти бензо-блоках, а `regex` не имел ни один.
    Тест держит все пять, чтобы дефект не вернулся в один из них незаметно.
    """
    assert _hp(rules, tt, 'Бензопила CS30EH; 12", 34см3, 1,32кВт/1,8л.с.') == Decimal("1.8")


# Известный долг: числовые оси, объявленные без шаблонов извлечения. Список
# закрыт намеренно — он фиксирует долг, а не разрешает его пополнять.
#
# `weight_kg` не чинится здесь и не «забыт»: вес в названиях действительно есть
# («…25,4см3, 3,2кг»), но у ДОМКРАТОВ в том же виде записана ГРУЗОПОДЪЁМНОСТЬ
# («домкрат 2т», «5кг» у корпуса) — две разные величины одной формой записи.
# Один шаблон на четыре блока написал бы в «Вес» грузоподъёмность, поэтому нужен
# отдельный замер по каждому типу, а не догадка.
KNOWN_AXES_WITHOUT_PATTERNS = {
    ("dreli-shurupoverty", "weight_kg"),
    ("perforatory", "weight_kg"),
    ("shlifmashiny", "weight_kg"),
    ("domkraty", "weight_kg"),
}


def test_no_new_number_axis_is_left_without_patterns():
    """Числовая ось без шаблонов извлечения = будущий пустой фасет.

    Это класс дефекта, а не единичный случай: `load_attributes` создаёт привязку
    по объявлению оси и не проверяет, есть ли чем её заполнить — именно так
    появились пять пустых фасетов `power_hp`. Тест ловит любую НОВУЮ такую ось до
    того, как она доедет до витрины, и одновременно не даёт молча вырасти списку
    известного долга.
    """
    import json

    rules = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    empty = {
        (block["tool_type"], axis["slug"])
        for block in rules["tool_types"]
        for axis in block["attributes"]
        if axis.get("kind") == "number" and not axis.get("regex")
    }
    assert (
        empty - KNOWN_AXES_WITHOUT_PATTERNS == set()
    ), f"новые числовые оси без шаблонов: {sorted(empty - KNOWN_AXES_WITHOUT_PATTERNS)}"
    assert KNOWN_AXES_WITHOUT_PATTERNS - empty == set(), (
        "долг закрыт — уберите оси из KNOWN_AXES_WITHOUT_PATTERNS: "
        f"{sorted(KNOWN_AXES_WITHOUT_PATTERNS - empty)}"
    )
