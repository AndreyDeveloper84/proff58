"""Пакет B: ручной инструмент, оснастка и крепёж.

Кейсы собраны субагентом из реальных названий стенда и перепроверены оркестратором
движком до интеграции. Негативные (`expected=None`) держат стоп-слова и границы.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir


@pytest.fixture(scope="module")
def rules() -> AttributeRules:
    return AttributeRules.from_file(data_dir() / "attribute_rules.json")


def _v(rules, tt, axis, name):
    for v in rules.extract(tt, name):
        if v.slug == axis:
            return v.option_slug or v.number
    return None


def _eq(got, exp):
    if exp is None or got is None:
        return got is None and exp is None
    if isinstance(got, str):
        return got == str(exp)
    return got == Decimal(str(exp))


CASES_LOMY_GVOZDODERY = [
    ("length", "Гвоздодер 17 мм, длина 800", 800),
    ("length", 'Лом-гвоздодер 19*1200мм KRAFTOOL "EXPERT" KraftBAR', 1200),
    ("length", "Лом-гвоздодер 400х17мм", 400),
    ("length", "Лом-гвоздодер усиленный, 25х12х450 MATRIX", 450),
    ("length", "Лом-гвоздодер, двутавровый профиль, 600х30х17 мм//", 600),
    ("length", "Гвоздодер металлический  45 см TRUPER", 450),
    ("length", "Лом строительный диам. 22мм длина 1250-1300мм", None),
    ("length", "Лом 1350/ст45мм d25", None),
    ("length", "Монтировка 9ВК41-53 KING TONY", None),
    ("diameter", "Гвоздодер 600 мм Ф16", 16),
    ("diameter", "Гвоздодер 400 мм, D-17 мм", 17),
    ("diameter", 'Лом-гвоздодер 19*1200мм KRAFTOOL "EXPERT" KraftBAR', 19),
    ("diameter", "Лом-гвоздодер 400х17мм", 17),
    ("diameter", "Лом 1350/ст45мм d25", 25),
    ("diameter", "Лом-гвоздодер KRAFTOOL  600 мм, 30х17 мм, кованый двутавровый,", None),
    ("diameter", "Лом-гвоздодер 22х12х600 мм кованый усиленный, STAY", None),
    ("diameter", "Гвоздодер 300х25х14мм обрезиненный Hanskonner", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_LOMY_GVOZDODERY)
def test_lomy_gvozdodery(rules, axis, name, expected):
    got = _v(rules, "lomy-gvozdodery", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_HOZ_SEKATORY = [
    ("length", "Секатор 200мм плоскостной с 2-хкомпонентными рукоятками GRINDA G-24", 200),
    ("length", "Кусторез RACO 420мм для точной подрезки алюмин ручки", 420),
    ("length", "Сучкорез прямого реза, 520 мм, стальные обрезиненн", 520),
    ("length", "Секатор GRINDA PROLine P-25 200 мм с эргономичными алюминиевыми рукоятками", 200),
    (
        "length",
        "Кусторез GRINDA PROLine FH-800T 630-800мм с кован лезвием, телескоп, алюм рукоятки",
        None,
    ),
    ("length", "Сучкорез плоскостной  телескопический GRINDA TX-980.645-885мм", None),
    ("length", "Секатор аккумуляторный HUTER CP-20Li-2K EA+ 2АКБ и ЗУ", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_HOZ_SEKATORY)
def test_hoz_sekatory(rules, axis, name, expected):
    got = _v(rules, "hoz-sekatory", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_BOLTOREZY = [
    ("length", "Болторез 450 мм STAYER", 450),
    ("length", 'Болторез 1050/42"мм ЗУБР "\'ЭКСПЕРТ"', 1050),
    ("length", "Болторез 600 мм арматура до 6мм Hobbi", 600),
    ("length", "Болторез 750 ММ, кованые губки из инструментальной", 750),
    ("length", "Губки к болторезу 600мм", None),
    ("length", "Болторез БР-1200 КВТ", None),
    ("length", "Кусачки для шурупов болторезы 30 дюймов Sata", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_BOLTOREZY)
def test_boltorezy(rules, axis, name, expected):
    got = _v(rules, "boltorezy", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_TROSOREZY_KABELEREZY = [
    ("length", "Кабелерез 160мм ЗУБР НК-16 ф9мм", 160),
    ("length", "Тросорез 200 мм/d4 цельнокованный ЗУБР КАТРАН", 200),
    (
        "length",
        'Кабелерез 600мм до 150 мм2 ЗУБР "ЭКСПЕРТ" для резки небронированного кабеля из цв металлов.',
        600,
    ),
    ("length", "Тросорез-кусачки KRAFTOOL EXPERT универсальный, кабель до 5мм, длина 190мм", 190),
    ("length", 'Кабелерез  60кв.мм  1000В ЗУБР "ЭЛЕКТРИК"', None),
    ("length", "Тросорез KRAFTOOL WR-800 профессиональный, длина 6", None),
    ("length", "Кабелерез до 150 мм2", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_TROSOREZY_KABELEREZY)
def test_trosorezy_kabelerezy(rules, axis, name, expected):
    got = _v(rules, "trosorezy-kabelerezy", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_PINTSETY = [
    ("length", "Пинцет 120 мм  прямой с острыми кончиками NP120-01 REXANT", 120),
    ("length", "Пинцет 150х0,8мм прямой медицинский BAKU", 150),
    ("length", "Пинцет изогнутый ПСм 150х0,8", 150),
    ("length", "Пинцет 1PK-105T ProsKit антистатический 140мм", 140),
    ("length", "Набор пинцетов  4 пр. нержавеющая сталь, 120мм", None),
    ("length", "Пинцеты антистатические 6 шт. для BGA", None),
    ("length", "Пинцет 1-PK-117T ProsKit", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_PINTSETY)
def test_pintsety(rules, axis, name, expected):
    got = _v(rules, "pintsety", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_IZM_KLEYMA = [
    ("height", "Клейма ЗУБР буквенные кириллица, шрифт 6мм", 6),
    ("height", "Клейма цифровые, шрифт 12мм тв. сплав", 12),
    ("height", "Клейма цифровые ударные 3 мм СИБРТЕХ", 3),
    ("height", "Клейма цифровых 8 мм. (повышенной твердости) АвтоDело", 8),
    ("height", "Клейма цифровые, шрифт  №4", None),
    (
        "height",
        "Набор резьбовых шаблонов АвтоDело для метрической резьбы М60 0.5-7.0 мм 40384",
        None,
    ),
    (
        "height",
        'Шаблон STAYER "PROFI" для определения шага метрич резьбы,0,5-1,75мм и трубной резьбы с шагом 0,907 и',
        None,
    ),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_IZM_KLEYMA)
def test_izm_kleyma(rules, axis, name, expected):
    got = _v(rules, "izm-kleyma", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_KREP_SVP = [
    ("width", "Крестики 2,0 мм,   200шт для плитки STAYER", 2.0),
    ("width", "Крестики 3.0 мм    150 шт FIT", 3.0),
    ("width", "Зажим СВП 1,0мм система выравнивания плитки 100штЗУБР", 1.0),
    ("width", "Крестики 6.0 мм    100 шт FIT", 6.0),
    ("width", "Клинья для кафеля 24х5,5 мм (100 шт.) Remocolor", None),
    ("width", "яяКлинья для кафеля 35х9 мм (50 шт.) БИБЕР", None),
    ("width", "Кольцо СВП система выравнивания плитки 1,5мм зажим+клин 50+50штЗУБР", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_KREP_SVP)
def test_krep_svp(rules, axis, name, expected):
    got = _v(rules, "krep-svp", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_HOZ_TROSY = [
    ("diameter", "Трос сантехнический 10 м/ 9,0 мм для чистки труб", 9.0),
    ("diameter", 'Трос сантехнический 3м, d6мм ЗУБР"ЭКСПЕРТ" в пласт', 6),
    ("diameter", "Трос сантехнический 1,4ммх6,0ммх5,0 м", 6.0),
    ("diameter", "Шнур резиновый крепежный 100см ф 8мм 2шт ЗУБР стальные крюки", 8),
    ("diameter", "Шнур резиновый 10мм 100м", 10),
    ("diameter", "Трос сантехнический ТС-12, L=20 м", None),
    ("diameter", "Трос альпинистский  6 т. СУПЕР УСИЛЕННЫЙ (5 метров", None),
    ("diameter", "Шнур резиновый для ремонта шин 25шт JTC", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_HOZ_TROSY)
def test_hoz_trosy(rules, axis, name, expected):
    got = _v(rules, "hoz-trosy", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_TSANGI_I_TSANGOVYE_PATRONY = [
    ("diameter", "Цанга 3,2мм", 3.2),
    ("diameter", "Цанга 4,0х50,0мм", 4.0),
    ("diameter", "Цанга 505 d-2,4мм АГНИ", 2.4),
    ("diameter", "Цанга ER32 - 6 мм", 6),
    ("diameter", "Цанга д. 2,0 х 50,0 мм", 2.0),
    ("diameter", "Набор цанг 1-10мм (10) ER16 тип 0762/0700", None),
    ("diameter", "Патрон КМ2/М10/ER25 с набором цанг ER25 (1,5-16мм,", None),
    ("diameter", "Патрон цанговый для ER32 тип 4000 ВТ40хER32-70", None),
    ("tool_kind", "Цанга 6мм тип 0700", "tsanga"),
    ("tool_kind", "Набор зажимных цанг КМ2/М10 3мм/4мм/5мм/6мм/8мм/10", "nabor"),
    ("tool_kind", "Патрон цанговый КМ2 с набором цанг ER32 из 18 шт.", "tsangovyy-patron"),
    ("tool_kind", "Патрон КМ2/М10/ER25 с набором цанг ER25 (1,5-16мм,", "tsangovyy-patron"),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_TSANGI_I_TSANGOVYE_PATRONY)
def test_tsangi_i_tsangovye_patrony(rules, axis, name, expected):
    got = _v(rules, "tsangi-i-tsangovye-patrony", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_OSNASTKA_BUROV = [
    ("length", "Удлинитель для бура SDS-Plus 300мм ЗУБР", 300),
    ("length", "Удлинитель 25х280мм для наборного бура", 280),
    ("length", "Удлинитель для бура 110см, ф 25мм", 1100),
    ("length", "Удлинитель д/бура (l=80см, d=25 мм)", 800),
    ("length", "Удлинитель для бура садового, длина 1,10 м", 1100),
    ("length", "яяУдлинитель д/бура L750 HUTER", 750),
    ("length", "яяАдаптер SDS+ на биту длиной 50мм", None),
    ("length", "Удлинитель SDS-MAX 530 402YH-M530", None),
    ("length", "Адаптер (переходник) SDS+ на патрон с M12*1.25 мм Hardax", None),
    ("diameter", "Удлинитель для бура  80см, ф 20мм", 20),
    ("diameter", "Удлинитель 25х280мм для наборного бура", 25),
    ("diameter", "Удлинитель д/бура (l=110см, d=25 мм)", 25),
    ("diameter", "яяУдлинитель для бура 100см ф27 Slit", 27),
    ("diameter", "яяАдаптер с SDS+ конич хвостовик сверло 11-17,5мм Hitachi", None),
    ("diameter", "Адаптер с HEX 13 на SDS+  Hitachi", None),
    ("shank_type", "Удлинитель для бура SDS-Plus 300мм ЗУБР", "sds-plus"),
    ("shank_type", "Удлинитель SDS-MAX 600 мм. 402YH-M600", "sds-max"),
    ("shank_type", "Удлинитель SDS-MAX 530 402YH-M530", "sds-max"),
    ("shank_type", "Адаптер с SDS-Max на SDS+  СЕБ", None),
    ("shank_type", "яяАдаптер SDS-Max на SDS+  CrV", None),
    ("shank_type", 'Адаптер (переходник) SDS+ на патрон с 1/2"-20 UNF Hardax', None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_OSNASTKA_BUROV)
def test_osnastka_burov(rules, axis, name, expected):
    got = _v(rules, "osnastka-burov", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_BRUSKI_SHLIF = [
    ("length", "Брусок абразивный 180х68х28мм,белый корунд, Р1000/Р3000 Sturm", 180),
    ("length", "Брусок БП 25х15х165 25А 25СМ1 6К", 165),
    ("length", "Брусок БКа 15х165 25А 10СМ2 6К", 165),
    ("length", "Брусок для шлифования, 210 х 105 мм, пластиковый с зажимами Matrix", 210),
    ("length", "Брусок абразивный 230мм Sturm", 230),
    ("length", 'Брусок косный "Лодочка" в упаковке', None),
    ("length", "Точилка для ножей керамическая компактная STAYER", None),
    ("width", "Брусок абразивный 180х68х28мм,белый корунд, Р1000/Р3000 Sturm", 68),
    ("width", "Брусок БКв 20х20х200 16СМ 64С", 20),
    ("width", "Брусок БКа 15х165 25А 10СМ2 6К", 15),
    ("width", "Брусок для шлифования 212х105мм STAYER", 105),
    ("width", "Брусок абразивный 230мм Sturm", None),
    ("width", "Брусок точильный для косы NAREX", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_BRUSKI_SHLIF)
def test_bruski_shlif(rules, axis, name, expected):
    got = _v(rules, "bruski-shlif", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"
