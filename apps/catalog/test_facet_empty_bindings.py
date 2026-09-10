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


# --- Решение владельца 2026-09-10: «кВт, охват важнее» ------------------------
#
# Фасет мощности бензоинструмента ведём осью `power`, а не `power_hp`: «л.с.» есть
# у 65 товаров, «кВт» — у 130. `power_hp` получила bind: false — значения остаются
# в карточке, но второго фасета мощности на витрине нет.
#
# Единица оси `power` — ВАТТЫ, и это не формальность: в ней уже 923 значения,
# включая лампы на 8–25 Вт. Поэтому киловатты пересчитываются множителем
# scale=1000, и шкала остаётся единой с электроинструментом вместо двух разных.


def _pw(rules: AttributeRules, tt: str, name: str):
    for v in rules.extract(tt, name):
        if v.slug == "power":
            return v.number
    return None


@pytest.mark.parametrize(
    ("tt", "name", "watts"),
    [
        ("bp-benzopily", 'Бензопила CS30EH; 12", 34см3, 1,32кВт/1,8л.с. бак', "1320"),
        ("bp-benzopily", 'Бензопила CHAMPION 237-16"-3/8-1,3-56 (1,5кВт 37,2см3', "1500"),
        ("bp-trimmery", "Бензокоса CG27EAS;  двиг 27см3, 0,88кВт, прям. вал", "880"),
        ("bp-trimmery", "Триммер бензиновый Hanskonner HBT43F 43см3, 1,35кВт/1,8л.с.", "1350"),
        ("bp-generatory", "Электрогенератор DEZEL PS-25. 2,5кВт, 220В, 15л", "2500"),
    ],
)
def test_kilowatts_are_converted_to_watts(rules, tt, name, watts):
    """Ось хранит ватты, поэтому «1,32кВт» → 1320, а не 1,32."""
    assert _pw(rules, tt, name) == Decimal(watts)


def test_generator_pair_takes_the_nominal_value(rules):
    """«5,0/5,5кВт» — номинальная и максимальная; берём НОМИНАЛ.

    Паспортная мощность генератора — номинальная; максимальная кратковременна, и
    фильтровать по ней значит обещать покупателю больше, чем машина держит.
    """
    name = "Электрогенератор CARVER PPG- 6500Е (LT-188F, 5,0/5,5кВт, 220В, бак 25л,"
    assert _pw(rules, "bp-generatory", name) == Decimal("5000")


def test_plain_watts_are_taken_as_is(rules):
    """Где производитель написал ватты — множитель не применяется."""
    name = "Триммер бензиновый STURM BT89314 1400Вт/1,9лс, 31см3, 4-х такт"
    assert _pw(rules, "bp-trimmery", name) == Decimal("1400")


def test_typo_in_the_name_yields_nothing_rather_than_nonsense(rules):
    """«135кВт» у бытового триммера — опечатка (там 1,35 кВт).

    Одного ограничения разрядности не хватило: regex брал последние две цифры и
    давал 35 000 Вт. Левая граница делает так, что опечатка не даёт значения
    вовсе — это лучше, чем правдоподобное неверное.
    """
    name = "Триммер бензиновый Hanskonner HBT143D 43см3, 135кВт/1,8л.с. нож/"
    assert _pw(rules, "bp-trimmery", name) is None


@pytest.mark.parametrize("tt", BLOCKS)
def test_exactly_one_power_axis_claims_a_facet(rules, tt):
    """Фасет мощности заявляет ровно одна ось — иначе покупатель выбирает между
    «Мощность» и «Мощность двигателя», не понимая разницы.

    В четырёх блоках фасет ведёт `power` (киловатты, охват вдвое больше), а у
    `bp-motobloki` — наоборот `power_hp`: киловатт в названиях культиваторов нет
    вовсе. Тест не фиксирует, КАКАЯ именно ось ведёт фасет, — только то, что она
    одна: это и есть инвариант, а распределение выведено из данных.
    """
    import json

    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == tt)
    axes = {a["slug"]: a for a in block["attributes"]}
    claims = [s for s in ("power", "power_hp") if axes[s].get("bind") is not False]
    assert claims == [claims[0]] and len(claims) == 1, f"{tt}: фасет заявляют {claims}"
    assert _pw(rules, tt, 'Бензопила CS30EH; 12", 1,32кВт/1,8л.с.') is not None


def test_motoblok_facet_stays_on_horsepower():
    """У культиваторов и мотобуров киловатт в названиях нет вовсе.

    Замер на стенде: 0 значений `power` против 5 в `power_hp`. Если оставить
    `power` с фасетом, следующий `load_attributes` вернёт привязку и создаст в
    узле 186 пустой фильтр — ровно тот дефект, ради которого трек затевался.
    Поэтому здесь фасет ведёт `power_hp`, а `power` объявлена с `bind: false`:
    ось остаётся на случай, если 1С начнёт писать киловатты.
    """
    import json

    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == "bp-motobloki")
    axes = {a["slug"]: a for a in block["attributes"]}
    assert axes["power"].get("bind") is False
    assert axes["power_hp"].get("bind") is not False


# --- Снятие пустых фасетов ----------------------------------------------------
#
# Замер показал 10 привязок без единого значения в поддереве. Проверка каждой
# свела «десять пустых фасетов» к куда более скромной картине, и это стоит
# помнить: пустая ЗАПИСЬ не равна пустой ПАНЕЛИ на витрине.
#
#   diameter -> 406   единственная настоящая пустая панель фильтра
#   spindle_thread -> 3   is_filter=False — панели и так нет
#   mount, purpose -> 80  дубликаты унаследованных от 79 «Коронки» (176 и 211
#                         значений); фасеты наследуются вниз, панель осталась бы
#   saw_for -> 89         дубликат унаследованного от 86 «Пильная оснастка»
#   tool_type ×5          на мёртвых узлах с нулём товаров — не трогаем


@pytest.mark.parametrize(
    ("tt", "slug"),
    [("bolgarki-ushm", "spindle_thread"), ("str-kisti", "diameter")],
)
def test_axes_whose_value_is_never_written_claim_no_facet(tt, slug):
    """Две оси не заявляют фасет, потому что величины нет в данных вовсе.

    `spindle_thread`: «М14/М10» встречается 0 раз в названиях 76 болгарок.
    `diameter` у кистей: «120х12мм» — это ширина и толщина плоской кисти,
    диаметра у неё нет; движок даёт значение у 0 из 143 товаров, и это верно.

    Обе оси в блоках ОСТАВЛЕНЫ: если 1С начнёт писать величину, значения попадут
    в карточку, и решение о фасете можно пересмотреть по замеру. Без `bind: false`
    удаление привязки не пережило бы следующий `load_attributes`.
    """
    import json

    data = json.loads((data_dir() / "attribute_rules.json").read_text(encoding="utf-8"))
    block = next(b for b in data["tool_types"] if b["tool_type"] == tt)
    axis = next(a for a in block["attributes"] if a["slug"] == slug)
    assert axis.get("bind") is False
    assert axis.get("regex") or axis.get("options"), "ось осталась без способа извлечения"
