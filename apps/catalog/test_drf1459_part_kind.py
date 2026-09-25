"""ДРФ-1459 (трек фасетов): «Вид детали» и «Питание» у листа 399.

Лист 399 «Статоры, якоря и редукторы» (221 опубликованный) — самый крупный
лист без собственного фасета; панель наследовала от 392 «Запчасти,
аккумуляторы и комплектующие» только «Тип инструмента».

Названия здесь предельно регулярны:
``{Якорь|Статор|Редуктор|Крышка редуктора} электродвигателя {напряжение}
({МОДЕЛЬ}) {артикул}``. Ось ``part_kind`` берёт **221 из 221 — 100 %**.

Она не дублирует панель типа: ``tool_type`` здесь всего два значения,
«Статоры, якоря, роторы» (200) и «Редукторы» (21), и внутри первого якорь от
статора он не отличает вовсе — а запчасть ищут именно как «якорь для DH40MR».

Проверяемые границы:

1. **«220В» содержит подстроку «20в».** Ключ 20-вольтового аккумуляторного
   инструмента переводил 32 сетевые детали в аккумуляторные. Закрыто
   ``word_boundary`` у оси ``power_source`` — без него ось врёт.
2. **Порядок опций значим дважды.** «Крышка редуктора» выше «Редуктора»,
   «Корпус статора» выше «Статора»: иначе частное значение поглощается общим.
3. **«Вт» в этом листе местами значит вольты.** «Якорь электродвигателя
   14,4Вт» — это 14,4 В: деталей мощностью 14 Вт не бывает. Обратный случай
   «Статор в сборе 220-230Вт» сознательно НЕ покрыт — в диапазоне 220–240 «Вт»
   может быть настоящей мощностью.
4. **Ось ``voltage`` отвергнута, хотя извлекается.** Значения дали бы 220 (105)
   и 230 (31) — артефакт того, как 1С записала диапазон, а не свойство детали.
5. **Вариант «Батарейки» держит порядок.** Он пришёл из блоков фонарей и здесь
   срабатывать не должен.
"""

from __future__ import annotations

import json

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir

SY, RED = "zap-statory-yakorya", "zap-reduktory"
KIND, PWR = "part_kind", "power_source"

# название → (вид детали, питание); None — ось обязана молчать.
CASES: list[tuple[str, str | None, str | None]] = [
    ("Статор электродвигателя 220В (H60MR) 340608E", "stator", "mains"),
    ("Статор электродвигателя 220-230В (DH28PC) 340739E", "stator", "mains"),
    ("Статор 230-240 VOLT 340791J", "stator", "mains"),
    ("Статор 220V-240V 340885E", "stator", "mains"),
    ("Статор 220-240Вольт, для СС14ST 336024", "stator", "mains"),
    ("Якорь 230 в, METABO", "yakor", "mains"),
    ("Якорь электродвигателя 220-240 в (DH22PH/DH22PG) 3", "yakor", "mains"),
    ("Статор электродвигателя 18В (WR18DBDL) 332203", "stator", "battery"),
    ("Якорь электродвигателя 12В (DS12DM) 360627", "yakor", "battery"),
    ("Якорь электродвигателя 14,4 В (DS14DSL/DV14DSL) 36", "yakor", "battery"),
    ("Якорь электро двигателя 10,8В с шестерней (WH10DL)", "yakor", "battery"),
    ("Корпус статора 335241", "korpus-statora", None),
    ("Крышка редуктора 320227", "kryshka-reduktora", None),
    ("Передняя крышка редуктора 323014", "kryshka-reduktora", None),
    ("Редуктор в сборе 331324", "reduktor", None),
    ("Шпиндель и редуктор в сборе 322917", "reduktor", None),
    ("Якорь Makita 516563-1", "yakor", None),
    ("Якорь МШУ Диолд", "yakor", None),
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
def test_name_yields_both_axes(rules, name, kind, power):
    """Обе оси читаются из названия детали."""
    assert _slug(rules, SY, KIND, name) == kind
    assert _slug(rules, SY, PWR, name) == power


def test_mains_voltage_is_not_a_twenty_volt_battery(rules):
    """Главная ловушка захода: «2​20В» содержит подстроку «20в».

    Без ``word_boundary`` ключ 20-вольтового инструмента переводил 32 сетевые
    детали в аккумуляторные — поймано замером до записи.
    """
    for name in (
        "Статор электродвигателя 220В 340176E",
        "Якорь электродвигателя 220В (C10RC) 329015А",
        "Якорь электродвигателя 220 В (C7MFA) 360694E",
        "Якорь электродвигателя 220в (DH40MR) 360591Е",
    ):
        assert _slug(rules, SY, PWR, name) == "mains", name


def test_word_boundary_is_declared_on_the_power_axis():
    """Гейт обязан стоять в словаре: без флага ось врёт молча."""
    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == SY)
    axis = next(a for a in block["attributes"] if a["slug"] == PWR)
    assert axis["word_boundary"] is True


def test_watt_means_volt_in_this_leaf(rules):
    """1С местами пишет «Вт» там, где вольты: деталей на 14 Вт не бывает."""
    assert _slug(rules, SY, PWR, "Якорь электродвигателя 14,4Вт (WH14DBL) 328651") == "battery"
    assert _slug(rules, SY, PWR, "Якорь электродвигателя 14,4 Вт 360865") == "battery"


def test_word_boundary_costs_one_name_without_a_space(rules):
    """Цена гейта: «14,4ВтWH14DSL» — в 1С пропущен пробел, и граница не встаёт.

    Значение теряется честно. Ослаблять границу ради одной позиции нельзя:
    именно она удерживает 32 сетевые детали от превращения в аккумуляторные.
    Вид детали при этом читается как обычно — молчит только ось питания.
    """
    name = "Якорь электродвигателя 14,4ВтWH14DSL/WR14DSL) 3607"
    assert _slug(rules, SY, PWR, name) is None
    assert _slug(rules, SY, KIND, name) == "yakor"


def test_mains_watt_form_is_deliberately_uncovered(rules):
    """«Статор в сборе 220-230Вт» — осознанный промах в безопасную сторону.

    В диапазоне 220–240 «Вт» может оказаться настоящей мощностью, и ради одной
    позиции такой ключ не заводится.
    """
    assert _slug(rules, SY, PWR, "Статор в сборе 220-230Вт 340753Е") is None
    assert _slug(rules, SY, KIND, "Статор в сборе 220-230Вт 340753Е") == "stator"


def test_specific_part_wins_over_the_general_one(rules):
    """«Крышка редуктора» и «Корпус статора» стоят выше общих значений."""
    assert _slug(rules, SY, KIND, "Крышка редуктора в сборе 336374") == "kryshka-reduktora"
    assert _slug(rules, SY, KIND, "Корпус статора 335660") == "korpus-statora"
    assert _slug(rules, RED, KIND, "Крышка редуктора(OLD 317823) 333839") == "kryshka-reduktora"


def test_gearbox_part_is_not_a_gearbox(rules):
    """Ключ сужен до «редуктор в сборе»: втулка редуктора — не редуктор.

    Широкий ключ «редуктор» внутри листа безупречен, но на полном пуле садился
    на ДЕТАЛИ редуктора и называл их редуктором — 144 позиции в legacy-узлах,
    которые по ДРФ-1459 ждут миграции: значения всплыли бы ровно тогда, когда
    узлы оживят. Лист при сужении не потерял ни одной позиции.
    """
    for name in (
        "Втулка редуктора 324109",
        "Втулка редуктора металлическая 321299",
        "Зубчатая пара редуктора 330040",
        "Задний корпус редуктора 330570",
        "Вторичный вал редуктора 323180",
        "Зажим редуктора 333512",
    ):
        assert _slug(rules, RED, KIND, name) is None, name


def test_assembled_gearbox_still_reads(rules):
    """Всё, что в листе названо редуктором, названо «в сборе» — сужение цело."""
    assert _slug(rules, RED, KIND, "Редуктор в сборе 331324") == "reduktor"
    assert _slug(rules, RED, KIND, "Редуктор в сборе 790221") == "reduktor"
    assert _slug(rules, SY, KIND, "Шпиндель и редуктор в сборе 322917") == "reduktor"
    assert _slug(rules, RED, KIND, "Крышка редуктора в сборе 336374") == "kryshka-reduktora"


def test_voltage_axis_is_not_declared(rules):
    """``voltage`` отвергнута: 220 против 230 — артефакт записи диапазона в 1С.

    Покупатель, отфильтровав «220», потерял бы подходящие ему детали,
    подписанные «230-240В».
    """
    assert {r.slug for r in rules.rules_for(SY)} == {KIND, PWR}
    assert {r.slug for r in rules.rules_for(RED)} == {KIND}


def test_batteries_option_only_holds_sort_order(rules):
    """Вариант из блоков фонарей присутствует, но здесь не срабатывает."""
    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == SY)
    axis = next(a for a in block["attributes"] if a["slug"] == PWR)
    assert [o["slug"] for o in axis["options"]] == ["battery", "mains", "batteries"]
    assert axis["options"][2]["keywords"] == []

    for name, _kind, _power in CASES:
        assert _slug(rules, SY, PWR, name) != "batteries"


def test_gearbox_block_binds_to_the_same_leaf():
    """У блока редукторов своей категории нет — адрес задан у оси.

    Из 172 его товаров в листе 399 лежат лишь 28, остальные — в мёртвых
    legacy-узлах запчастей.
    """
    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    sy = next(b for b in data["tool_types"] if b["tool_type"] == SY)
    red = next(b for b in data["tool_types"] if b["tool_type"] == RED)
    assert sy["category"] == "Статоры, якоря и редукторы"
    assert "category" not in red
    assert red["attributes"][0]["category"] == "Статоры, якоря и редукторы"


def test_each_axis_yields_at_least_two_values():
    """Правило DRF-1428: ось с одним значением фасетом быть не может."""
    assert len({k for _, k, _ in CASES if k}) >= 2
    assert len({p for _, _, p in CASES if p}) >= 2
