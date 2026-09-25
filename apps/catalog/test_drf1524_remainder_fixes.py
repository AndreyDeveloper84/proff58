"""ДРФ-1524: остаток каталога — 631 значение, 16 из них были ложью.

После записи семи типов read-only прогон по ВСЕМУ каталогу (25 075 товаров)
показал, что правила извлекают ещё 631 значение, которого нет в БД. Сверка
каждого против смысла названия остановила семь типов.

Два из них раньше считались «заблокированными до решения о карантине» (товары
18772 и 18449). Проверка показала обратное: оба чинятся правилами, и это лучше
карантина — запись реестра глушит товар целиком, а здесь неверна одна ось.
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
            return v.option_slug or v.number
    return None


# --- 1. Напильники: «яяНабор» обходил стоп-слово ------------------------------


def test_file_set_has_no_single_shape(rules):
    """У набора напильников одной формы нет — в нём их несколько.

    Стоп-слово «набор» в правиле есть, но не срабатывает: skip_if требует границы
    НАЧАЛА слова, а служебный префикс «яя» вплотную её убирает. Дублируется в
    skip_regex с якорем начала.

    Замер по всем 3930 «яя»-товарам с типом: системное снятие префикса изменило
    бы РОВНО это одно значение по всему каталогу — поэтому движок не трогаем.
    """
    name = "яяНабор напильников с двухкомп.рукояткой:плоский, кр"
    assert _v(rules, "napilniki", "file_shape", name) is None
    assert _v(rules, "napilniki", "file_cut", name) is None
    assert _v(rules, "napilniki", "length", name) is None


def test_single_file_still_reads(rules):
    """Регресс: одиночный напильник читается по всем трём осям."""
    name = "Напильник плоский 200мм №2"
    assert _v(rules, "napilniki", "file_shape", name) == "ploskiy"
    assert _v(rules, "napilniki", "length", name) == Decimal("200")


# --- 2. Шарошки: тройка размеров отдавала второе число ------------------------


def test_triple_size_yields_the_first_number(rules):
    """«цилиндр 25х38x6 мм» давало диаметр 38 — это ДЛИНА.

    Парный шаблон требует «мм» сразу после второго числа, поэтому «25х38» не
    подходил, а «38x6 мм» подходил. Тройка объявлена отдельным шаблоном ПЕРЕД
    парным и берёт первое число.
    """
    name = "Шарошка абразивная по металлу, цилиндр 25х38x6 мм, F46, 3 шт Matrix"
    assert _v(rules, "sharoshki", "diameter", name) == Decimal("25")


def test_pair_size_unchanged(rules):
    """Регресс: обычная пара читается как раньше."""
    name = "Шарошка абразивная по металлу, цилиндр 20x25 мм FIT"
    assert _v(rules, "sharoshki", "diameter", name) == Decimal("20")


# --- 3. Скобы: диаметр крепёжной скобы уходил в длину -------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Скобы металлические , двухлапковые,  d=25мм, 50шт",
        "Скобы металлические D31мм, двухлапковые, для крепл",
    ],
)
def test_cable_clip_diameter_is_not_a_length(rules, name):
    """У двухлапковой скобы размер — диаметр кабеля, а не длина ножки."""
    assert _v(rules, "str-skoby", "length", name) is None


def test_stapler_staple_length_still_reads(rules):
    """Регресс: у скоб для степлера размер — именно длина."""
    name = "Скобы для степлера тип 53 GROSS 12мм/1000шт"
    assert _v(rules, "str-skoby", "length", name) == Decimal("12")


# --- 4. Зубила: три класса ошибок разом ---------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Зубило 12х9,5х130 мм Hans",
        "Зубило Бучарда SDS-max (45x45х240 мм; 16Z) ПРАКТИКА",
        "Зубило Бучарда SDS-plus (45x45х180 мм; 16Z) ПРАКТИКА",
        "Кернер автоматический 3,9х12,7х130 Bohre",
    ],
)
def test_triple_size_is_gated(rules, name):
    """Тройка размеров давала длиной ТОЛЩИНУ: «12х9,5х130» → 9,5.

    Числа тройки бывают дробными, и первая версия гейта их не поймала — тест
    держит именно дробную форму. Различить «ширина×толщина×длина» и
    «ширина×длина×протектор» нечем, поэтому ось молчит: молчание лучше лжи.
    """
    assert _v(rules, "zubila", "length", name) is None
    assert _v(rules, "zubila", "width", name) is None


@pytest.mark.parametrize(
    "name",
    [
        "Зубило 250 х 24 мм, с протектором// Sparta",
        "Зубило, 300 х 24 мм, с протектором// Sparta",
    ],
)
def test_reversed_order_is_gated(rules, name):
    """«Зубило 250 х 24 мм» — длина 250, ширина 24, а правило читало наоборот.

    Гейт опознаёт форму «три цифры × две»: ширина зубила не превышает 45 мм,
    поэтому трёхзначное число слева — всегда длина.
    """
    assert _v(rules, "zubila", "length", name) is None
    assert _v(rules, "zubila", "width", name) is None


def test_blade_width_is_not_a_length(rules):
    """«Зубило 13 мм» — это ширина лезвия, а не длина инструмента."""
    assert _v(rules, "zubila", "length", "Зубило 13 мм NEO") is None


@pytest.mark.parametrize(
    ("name", "length", "width"),
    [
        ("Зубило 115х350мм SDS-MAX HAWERA", "350", "115"),
        ("Зубило 40х400 мм SDS-Plus  TUNDRA", "400", "40"),
    ],
)
def test_normal_chisel_pair_survives(rules, name, length, width):
    """Регресс: обычная пара «ширина × длина» не задета."""
    assert _v(rules, "zubila", "length", name) == Decimal(length)
    assert _v(rules, "zubila", "width", name) == Decimal(width)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Зубило 200 мм усиленное, KING TONY", "200"),
        ("Зубило 300мм NEO", "300"),
    ],
)
def test_three_digit_single_length_survives(rules, name, expected):
    """Регресс: разрядность поднята до трёх цифр, длина читается."""
    assert _v(rules, "zubila", "length", name) == Decimal(expected)


def test_center_punch_diameter_survives(rules):
    """Регресс: у кернера пара «диаметр × длина» осталась."""
    assert _v(rules, "zubila", "diameter", "Кернер 8х110мм РОС") == Decimal("8")
    assert _v(rules, "zubila", "length", "Кернер 8х110мм РОС") == Decimal("110")


# --- 5. Ножницы: диаметр трубы — не длина инструмента -------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Ножницы PNZ-12 диаметр трубки 12мм",
        "Ножницы для ПВХ труб 42 мм Вихрь",
    ],
)
def test_max_cut_diameter_is_not_a_length(rules, name):
    """Прежние стоп-слова промахивались мимо словоформы.

    «трубок» не покрывает «трубки», а «для труб» не покрывает «для ПВХ труб» —
    между словами стоит ещё одно. Поэтому стоп-слово укорочено до корня.
    """
    assert _v(rules, "nozhnitsy-ruchnye", "length", name) is None


# --- 6. Развёртки и фрезы -----------------------------------------------------


def test_reamer_length_is_not_a_diameter(rules):
    """«Развертка ручная шкворневых втулок, 450мм» — 450 это длина."""
    name = "Развертка ручная шкворневых втулок, 450мм, винтова"
    assert _v(rules, "razvertki-frezy", "diameter", name) is None


def test_slot_width_is_not_a_cutter_diameter(rules):
    """«на паз 22 мм» — ширина паза, под который фреза предназначена.

    Настоящий диаметр 40 из «40х18» этим правилом всё равно не извлекается,
    поэтому ось молчит целиком.
    """
    name = "Фреза Т-образная 40х18 к/х Р6АМ5 Z=8 КМ3 на паз 22 мм"
    assert _v(rules, "razvertki-frezy", "diameter", name) is None


# --- 7. Свёрла: приспособление — не сверло ------------------------------------


def test_jig_is_not_a_drill_bit(rules):
    """«Приспособление для сверления отверстий 30 мм» лежит в типе sverla."""
    name = "Приспособление для сверления отверстий 30 мм в газ"
    assert _v(rules, "sverla", "diameter", name) is None


def test_real_drill_diameter_survives(rules):
    """Регресс: настоящее сверло читается."""
    assert _v(rules, "sverla", "diameter", "Сверло по бетону  5х85мм БОЕКОМПЛЕКТ") == Decimal("5")
