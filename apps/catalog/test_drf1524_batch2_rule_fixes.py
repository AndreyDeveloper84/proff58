"""ДРФ-1524: восемь дефектов правил, найденных сверкой ПЕРЕД записью.

Замер по каталогу показал 3564 значения, которые правила извлекают, но которые
не записаны в БД. При попытке прогнать типы сверка остановила восемь осей: они
писали неверные значения. Каждый случай ниже подтверждён на стенде поимённо, и
каждый — отдельный класс ошибки, а не опечатка.

Общее у всех: значение выглядит правдоподобно, пока не сверишь его со смыслом
названия. Число из бренда, число из соседней величины, число из другой шкалы —
всё это проходит любую проверку «а есть ли тут цифры».
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


# --- 1. Наборы: «шт» — подстрока бренда «ШТОК» -------------------------------


def test_brand_shtok_is_not_a_piece_count(rules):
    """«Набор инструмента диэл. №3 ШТОК» — это бренд, а не три предмета."""
    for name in (
        "Набор инструмента диэл. №3 ШТОК",
        "Набор инструмента диэл. №2 ШТОК",
        "Набор инструмента диэл. №5 ШТОК",
    ):
        assert _v(rules, "nabory-instrumenta", "piece_count", name) is None, name


def test_real_piece_counts_survive(rules):
    """Правая граница не должна мешать ни «шт.», ни «штук», ни «предметов»."""
    tt = "nabory-instrumenta"
    assert _v(rules, tt, "piece_count", "Набор инструмента 12 предметов") == Decimal("12")
    assert _v(rules, tt, "piece_count", "Набор бит 32 шт.") == Decimal("32")
    assert _v(rules, tt, "piece_count", "Набор головок 24 штук") == Decimal("24")
    assert _v(rules, tt, "piece_count", "Набор ключей 8 пр.") == Decimal("8")


# --- 2. Наборы: многоприводной набор записывался одним приводом ---------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ('Набор инструмента 141 пр. 1/2",3/8", 1/4" OMT141S Ombra', "d-1-4-3-8-1-2"),
        ('Набор инструмента 150 пр. 1/4",3/8",1/2" Sata', "d-1-4-3-8-1-2"),
        ('Набор инструмента 216 пр 1/2"&1/4"&3/8"DR', "d-1-4-3-8-1-2"),
        ('Набор вставок F-4401: 1/2"& 3/8"& 1/4"DR торкс', "d-1-4-3-8-1-2"),
        ("Набор инструмента 101 пр 1/4- 1/2 HiKoki", "d-1-4-1-2"),
        ('Набор инструмента 143 предмета 1/4" и 1/2" 6гр. LI', "d-1-4-1-2"),
        ('Набор инструмента 127 пр. универсальный 1/2" и 1/4" Jonnesway', "d-1-4-1-2"),
        ('Набор инструмента 109 предметов 1/2", 1/4" STELS', "d-1-4-1-2"),
    ],
)
def test_multi_drive_set_is_not_a_single_drive(rules, name, expected):
    """Разделитель бывает запятой, амперсандом, дефисом и союзом «и».

    Прежде комбинированные варианты ловились только при порядке через запятую,
    остальные 21 из 80 проваливались на одиночную «1/4». Ключевые слова
    выписаны из данных: 52 набора, 25 форм записи.
    """
    assert _v(rules, "nabory-instrumenta", "drive", name) == expected


def test_single_drive_set_still_reads(rules):
    """Регресс: набор с одним приводом читается как раньше."""
    assert _v(rules, "nabory-instrumenta", "drive", "Набор головок 1/4 DR 12 предметов") == "d-1-4"


# --- 3. Шурупы: «57мм 1500мм» → диаметр 1500 ---------------------------------


def test_second_m_of_millimetres_is_not_a_thread_mark(rules):
    """«Свая-шуруп ф57мм 1500мм» получала ДИАМЕТР 1500.

    Шаблон принимал вторую «м» из «57мм» за обозначение метрической резьбы и
    брал следующее число. Дефект повторялся бы на любом «…N мм M мм».
    """
    assert _v(rules, "krep-shurupy", "diameter", "Свая-шуруп ф57мм 1500мм оцинк") is None


def test_normal_screw_thread_still_reads(rules):
    """Регресс: обычная запись резьбы не пострадала."""
    assert _v(rules, "krep-shurupy", "diameter", "Шуруп М10х100 оцинк") == Decimal("10")
    assert _v(rules, "krep-shurupy", "length", "Шуруп М10х100 оцинк") == Decimal("100")
    assert _v(rules, "krep-shurupy", "diameter", "Шуруп-глухарь 8х80") == Decimal("8")


# --- 4. Саморезы: дробь через слэш --------------------------------------------


def test_slash_pair_yields_nothing_rather_than_the_smaller_size(rules):
    """«Саморез для сэндвич панелей 6,3/5,5*135» давал диаметр 5,5.

    Вторая половина дроби через слэш читалась как самостоятельное число.
    Теперь пара молчит целиком — как уже сделано у шурупов.
    """
    name = "Саморез для сэндвич панелей 6,3/5,5*135"
    assert _v(rules, "krep-samorezy", "diameter", name) is None
    assert _v(rules, "krep-samorezy", "length", name) is None


def test_normal_self_tapping_screw_still_reads(rules):
    """Регресс: обычная пара «3,5х25» не пострадала."""
    assert _v(rules, "krep-samorezy", "diameter", "Саморез 3,5х25 ЗУБР") == Decimal("3.5")
    assert _v(rules, "krep-samorezy", "length", "Саморез 3,5х25 ЗУБР") == Decimal("25")


# --- 5. Оснастка коронок: длина удлинителя уходила в диаметр -------------------


@pytest.mark.parametrize(
    "name",
    [
        "Удлинитель для коронок алмазных М16 SDS+ 600мм",
        "Удлинитель для коронок по бетону SDS-MAX 800мм СЕБ",
        "Удлинитель для коронок буровых SDS-Plus 450мм резьба М22 ЗУБР",
        "Удлинитель для биметаллических коронок 300 мм, ЗУБР",
    ],
)
def test_extension_length_is_not_a_core_diameter(rules, name):
    """Самый дорогой из восьми: 30 таких значений легли бы на живые карточки.

    В листе 79 «Коронки» уже 267 настоящих диаметров — рядом с ними в фасете
    встали бы «600 мм» и «800 мм». Правило писалось по выборке товаров в
    наличии («пул 17»), где удлинителей не было; в лист они попали позже, при
    разборе свалки 383.
    """
    assert _v(rules, "osnastka-koronok", "diameter", name) is None


def test_extension_keeps_its_real_axes(rules):
    """Гейт снимает только диаметр: хвостовик и посадка читаются по-прежнему."""
    name = "Удлинитель для коронок алмазных М16 SDS+ 600мм"
    assert _v(rules, "osnastka-koronok", "shank_type", name) == "sds-plus"
    assert _v(rules, "osnastka-koronok", "mount", name) == "m16"


def test_compatibility_bound_is_not_a_diameter(rules):
    """Форма «до 30мм» была закрыта, «свыше 30мм» — нет."""
    assert (
        _v(rules, "osnastka-koronok", "diameter", "Адаптер для биметал.коронок HITACHI свыше 30мм")
        is None
    )


def test_real_core_diameter_still_reads(rules):
    """Регресс: у настоящего переходника диаметр остаётся."""
    assert _v(
        rules, "osnastka-koronok", "diameter", "Переходник для коронок М16, 100 мм"
    ) == Decimal("100")


# --- 6. Наждачка: советская шкала ГОСТ 3647 в оси FEPA -------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Шкурка на ткан.основе №10 в рулоне",
        "Шкурка на ткан.основе №16 в рулоне",
        "Шкурка на ткан.основе №25 в рулоне",
        "Шкурка на ткан.основе №32 в рулоне",
    ],
)
def test_soviet_grit_number_is_not_fepa(rules, name):
    """«№10» по ГОСТ 3647 — это Р120, а не зернистость 10.

    Соседние карточки доказывают несовпадение шкал: №16=Р80, №8=Р150,
    №4=Р320. Советские номера это 0…32, FEPA начинается с 40.
    """
    assert _v(rules, "nazhdachka", "grit", name) is None


def test_fepa_grit_after_hash_still_reads(rules):
    """«Сетка шлифовальная №200» — здесь «№» и есть FEPA, значение верное."""
    assert _v(rules, "nazhdachka", "grit", "Сетка шлифовальная 115х280мм №200") == Decimal("200")


def test_both_scales_in_one_name_still_prefers_fepa(rules):
    """Случай с двумя шкалами правило разбирало верно и раньше."""
    assert _v(rules, "nazhdachka", "grit", "Шкурка №10 (Р120) БАЗ") == Decimal("120")


def test_roll_length_in_metres_is_not_millimetres(rules):
    """«Бумага наждачная 800х30» — это 800 мм на 30 МЕТРОВ."""
    assert _v(rules, "nazhdachka", "length", "Бумага наждачная 800х30 БАЗ") is None


def test_five_digit_length_is_not_truncated(rules):
    """«Рулон нетканный абразивный 115х10000мм» давал 1000."""
    name = "Рулон нетканный абразивный 115х10000мм"
    assert _v(rules, "nazhdachka", "length", name) == Decimal("10000")
    assert _v(rules, "nazhdachka", "width", name) == Decimal("115")


# --- 7. Хомуты: ширина ленты и длина корпуса вместо диаметра зажима ------------


@pytest.mark.parametrize(
    "name",
    [
        "Лента хомута 9 мм W2 нерж 30 м",
        "Замок ленты хомута Norma 12мм (W3)",
        "Лента хомутовая 12мм NORMAFIX",
        "Хомут ремонтный стальной Ду 80 L=103 мм",
        "Рукав напорно-всасывающий 75мм с усиленными хомутами",
    ],
)
def test_tape_width_and_body_length_are_not_clamp_diameter(rules, name):
    """Одиночный шаблон «N мм» брал не тот размер у 15 товаров из 105."""
    assert _v(rules, "krep-styazhki", "hose_diameter_from", name) is None
    assert _v(rules, "krep-styazhki", "hose_diameter_to", name) is None


def test_clamp_range_still_reads(rules):
    """Диапазонная форма чиста на всех 90 остальных — её не трогали."""
    name = "Хомут червячный 105-127 мм"
    assert _v(rules, "krep-styazhki", "hose_diameter_from", name) == Decimal("105")
    assert _v(rules, "krep-styazhki", "hose_diameter_to", name) == Decimal("127")


def test_band_width_beside_a_valid_range_does_not_kill_it(rules):
    """Стоп-слово — ФРАЗА «лента хомут», а не голое «лента».

    У настоящего «Хомут обжимной 40-62 мм, лента 9 мм» ширина ленты стоит в том
    же названии рядом с верным диапазоном. Голое «лента» погасило бы ось целиком
    и увезло 90 честных диапазонов вместе с 15 ложными — это и произошло в первой
    версии правки, тест test_band_width_never_wins_over_clamp_diameter её поймал.
    """
    name = "Хомут обжимной  40-62 мм, лента 9 мм, нерж.сталь,"
    assert _v(rules, "krep-styazhki", "hose_diameter_from", name) == Decimal("40")
    assert _v(rules, "krep-styazhki", "hose_diameter_to", name) == Decimal("62")


# --- 8. Струбцины: ложные срабатывания раскрытия ------------------------------


def test_single_value_fills_both_bounds_on_purpose(rules):
    """«Струбцина 200мм» даёт «от 200 до 200», и это НЕ дефект.

    Выглядит как ошибка, но так работает диапазонный фильтр: по запросу
    «раскрытие 150–250» струбцина ровно на 200 обязана находиться, а для этого
    нужны обе границы. Инвариант старше этой задачи и закреплён отдельно —
    test_no_inverted_bounds_anywhere («обе или ни одной») и
    test_clamp_range_and_single_share_one_axis_pair в test_drf1450_mm_axis.py.
    Попытка убрать одиночный шаблон из нижней границы уронила оба и откачена.
    """
    assert _v(rules, "strubtsiny", "clamp_from", "Струбцина 200мм тип G") == Decimal("200")
    assert _v(rules, "strubtsiny", "clamp_to", "Струбцина 200мм тип G") == Decimal("200")


@pytest.mark.parametrize(
    "name",
    [
        "Струбцина F-образная, 250 х 50 х 300 мм// SPARTA",
        "Струбцина угловая НСС-80 KRAFTOOL глубина зажима 73мм",
        "Струбцина угловая KRAFTOOL АС-80, две опорные поверхности по 88мм",
        "Тиски 63мм слесарные со струбциной",
    ],
)
def test_clamp_false_positives_are_gated(rules, name):
    """Глубина зажима, длина опор, тройка размеров и вообще не струбцина."""
    assert _v(rules, "strubtsiny", "clamp_to", name) is None
    assert _v(rules, "strubtsiny", "clamp_from", name) is None
