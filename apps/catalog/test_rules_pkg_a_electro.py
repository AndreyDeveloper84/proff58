"""Пакет A: электроинструмент и оборудование.

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


CASES_BP_KOMPRESSORY = [
    ("power", "Компрессор Abac Pole Position L30P 310л/мин_24л_10бар_2.2 кВт_рапид", 2200),
    ("power", "Компрессор безмасляный ЗУБР 200 л/мин, 24 л, 1500 Вт", 1500),
    (
        "power",
        "Компрессор поршневой СБ4/С-100LB50 ресивер 100л, 690л/мин., 10атм.,4,0кВт, 380В, 2 цилиндра р-р:1200",
        4000,
    ),
    ("power", "Компрессор автомобильный ECO AE-028-2, 280Вт, 12В, 10Атм, 70л/мин", 280),
    ("power", "Компрессор поршневой METABO MEGA 350-100 W", None),
    ("power", "яяКомпрессор Hitachi GM300; 220 В, 2,5 л.с., 285 л", None),
    ("power", "Реле давления PEGAS SP038 для компрессора 220В", None),
    ("voltage", "Компрессор AET 100л 240л/мин 380В ТК-100-2", 380),
    ("voltage", "Компрессор безмасляный Fubag FC 230/24CM2; 220 В,", 220),
    ("voltage", "Компрессор автомобильный DENZEL АС-37 12В, 7атм, 37л/мин", 12),
    ("voltage", "Компрессор Remeza СБ 4/С-100.J2047 В", None),
    ("voltage", "Реле давления для компрессора 380В", None),
    ("voltage", "Компрессор QUATTRO ELEMENTI В400-50, поршневой масляный", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_BP_KOMPRESSORY)
def test_bp_kompressory(rules, axis, name, expected):
    got = _v(rules, "bp-kompressory", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_OBOR_PUSHKI = [
    ("power", "Тепловая завеса КЭВ-12П3041Е 12кВт, 380В", 12000),
    (
        "power",
        "Тепловая пушка ЗТП-М1-3000, 3/1,5 кВт, 220 В, круглая, электрическая, гладкий нерж ТЭН, двойные стен",
        3000,
    ),
    ("power", "Тепловентилятор STURM FH3022C керамический 3кВт/1,5кВт", 3000),
    ("power", "Тепловая пушка дизельная PEGAS PD-200, 20Квт", 20000),
    ("power", "Тепловентилятор керам. GENIRAL KRP-5  1.5кВт повор", 1500),
    ("power", "Тепловентилятор DHC 2-100, 220В, 0,025/1/2 кВт кер", None),
    ("power", "Тепловая пушка РЕСАНТА ТЭП-5000 380В ТЭН", None),
    ("power", "Тепловентилятор ТВК-5 (завеса) 220-240 В, 50 Гц, 2000В Ресанта", None),
    ("voltage", "Тепловая пушка Hitachi HF9T 9кВт 380В", 380),
    ("voltage", "Тепловая пушка РЕСАНТА ТЭП-2000Н 220В ТЭН компакт", 220),
    ("voltage", "Тепловентилятор ТВК-1 220-240 В, 50 Гц, 900/1800 В Ресанта", 220),
    ("voltage", "Тепловая пушка дизельная непрямого нагрева ELITECH ДП 5 5кВт, 12/24/220В", None),
    ("voltage", "Тепловая пушка газовая ТГП-15000 18кВт, 1,2 кг ч.", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_OBOR_PUSHKI)
def test_obor_pushki(rules, axis, name, expected):
    got = _v(rules, "obor-pushki", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_OBOR_MOYKI = [
    ("power", "Мойка Bosch AQT 33-10; 220 В, 1300 Вт, 330 л/ч, 10", 1300),
    (
        "power",
        "Мойка высокого давления HUSQVARNA PW 345C (220В,2.4кВт, 135-145 бар, 420-550л/час, шланг 8м)",
        2400,
    ),
    ("power", "яяМойка NILFISK C110.4-5 X-TRA1400 Вт,110 бар,440л", 1400),
    ("power", "Мойка ЗУБР П-240, 240атм, 3300Вт Профессионал", 3300),
    ("power", "Аппарат высокого давления Karcher HD 10/25-4 S", None),
    ("power", "Мойка без нагрева воды NILFISK MC 5M-200/1000 (Pos", None),
    ("voltage", "Мойка без нагрева воды Karcher HD 9/20-4M ;380 В,7", 380),
    ("voltage", "Мойка Hitachi AW100; 220В, 1400 Вт, 5,5 л/мин, 100", 220),
    ("voltage", "Мойка высокого давления TX 13.180 380В", 380),
    ("voltage", "Мойка аккумуляторная HUTER W-20Li  1АКБ и ЗУ", None),
    ("voltage", "Мойка ЗУБР АВД-140 140атм, 1700Вт пистолет МИГ-180", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_OBOR_MOYKI)
def test_obor_moyki(rules, axis, name, expected):
    got = _v(rules, "obor-moyki", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_PYLESOSY = [
    (
        "power",
        "Пылесос строительный ЗУБР ПУ-20-1400, 20 л, 1400 Вт, Розетка до 2 квт, сухая и влажная уборка",
        1400,
    ),
    ("power", "Пылесос BOSCH GAS 12-25 PL, сух/влаж,25л,1250 Вт,L", 1250),
    (
        "power",
        "Пылесос/воздуходувка RВ40SA; 550 Вт, 5,5кРа, 3,8м3/мин, 16000 об/мин, 1,7кг Hitachi",
        550,
    ),
    ("power", "Пылесос M-06012 SILVER 65W для сухой и влажной убо", 65),
    ("power", "Станок шлифовальный двухдисковый BKL-3000 с пылесосом VISPROM", None),
    ("power", "Пылесос строительный РЕСАНТА ПС-1500/20", None),
    ("voltage", "Пылесос HITACHI R14DSL 14В аккумуляторный без акку", 14),
    ("voltage", "Пылесос аккум Einhell PXC TE-VC 18/10 Li-Solo 18В, 125мм без АККУМ и ЗУ", 18),
    ("voltage", "Пылесос аккумуляторный AS 18 L PC Metabo, 18В, 2аккум 5,2А/Ч", 18),
    (
        "voltage",
        "Пылесос/воздуходувка BSS-900-R Bort  280 км/ч, 1 300 м3/ч, режим всасывания, сеть 220В, 1,8 кг",
        None,
    ),
    ("voltage", "Пылесос Makita DCL180Z", None),
    ("power_source", "Пылесос аккумуляторный AS 18 L PC Metabo, 18В без аккум и ЗУ", "battery"),
    (
        "power_source",
        "Воздуходувка-пылесос аккум Einhell PXC VENTURBO 18В 210км/ч, мешок 45л, Solo без АККУМ и ЗУ",
        "battery",
    ),
    (
        "power_source",
        "Пылесос/воздуходувка BSS-900-R Bort  280 км/ч, 1 300 м3/ч, режим всасывания, сеть 220В, 1,8 кг",
        "mains",
    ),
    ("power_source", "Пылесос Karcher WD 3 P PREMIUM", None),
    (
        "power_source",
        "Пылесос строительный ЗУБР ПУ-30-1400, 30 л, 1400 Вт, Розетка до 2 квт, сухая и влажная уборка",
        None,
    ),
    (
        "weight_kg",
        "Пылесос д/сухой и влажной уборки Hitachi RP150YB; 2400Вт, 3,5м3/мин, 15л, 7,1кг",
        7.1,
    ),
    (
        "weight_kg",
        "Пылесос/воздуходувка BSS-900-R Bort  280 км/ч, 1 300 м3/ч, режим всасывания, сеть 220В, 1,8 кг",
        1.8,
    ),
    (
        "weight_kg",
        "Пылесос д/сухой и влажной уборки Hitachi RP350YE; 2400Вт, 3,5м3/мин,35л, 12,6кг",
        12.6,
    ),
    ("weight_kg", "Пылесос Hanskonner HVC20WD 1500Вт 20л", None),
    ("weight_kg", "Пылесос ЗУБР, 30 л, 1400 Вт, Розетка до 2 квт, сух", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_PYLESOSY)
def test_pylesosy(rules, axis, name, expected):
    got = _v(rules, "pylesosy", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_PAYALNIKI = [
    ("power", "Паяльник  25 Вт, дер.ручка", 25),
    ("power", "Паяльник 100Вт, клин, STAYER", 100),
    ("power", "Паяльник ЭПСН 500Вт/220В ) дер. ручка (топор)", 500),
    ("power", "Паяльник с регулировкой температуры 5 жал 65Вт REXANT", 65),
    ("power", "Паяльник 30-130Вт, пист рукояткой", None),
    ("power", "Паяльник газовый KRAFTOOL, 3в1, регулировка пламени, 1300С", None),
    ("power", "Подставка для паяльников  штампованная стальная STAYER", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_PAYALNIKI)
def test_payalniki(rules, axis, name, expected):
    got = _v(rules, "payalniki", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_MIKSERY = [
    ("power", "Миксер Einhell TC-MX 1200 E, 1200Вт", 1200),
    (
        "power",
        "Миксер ЗУБР, одинарный, универсальный 1050 Вт, 2 скорости: 0-500 / 0-700 об/мин, 120л",
        1050,
    ),
    ("power", "Миксер Stanley Fatmax FME190-QS, 1600 Вт", 1600),
    ("power", "Миксер ВИХРЬ СМ-1200Э", None),
    ("power", "Миксер КМД-120/1200 Э-Н  Интерскол", None),
    ("no_load_speed", "Миксер Makita UT1400, 1300Вт, 0-900об/мин, M14, 5,", 900),
    (
        "no_load_speed",
        "Миксер ЗУБР одинарный строительный 2-х скор 1400Вт, 0-620/0-810 об/мин М14, перемеш верх-низ",
        810,
    ),
    (
        "no_load_speed",
        "Миксер UM12VST;  1100Вт, М14, 150-300/300-650об/мин, плав. пуск, 5,6кг",
        650,
    ),
    ("no_load_speed", "Миксер STURM DM2016CE 1600Вт, 0-600/0-900 об мин", 900),
    ("no_load_speed", 'Миксер ЗУБР МРД-1400, двойной 1400 Вт 0-520 об/мин, "сверху-вниз"', 520),
    ("no_load_speed", "яяМиксер ЗУБР МР-1400-2, 1400 Вт, 2 скорости, 13Нм, 0-620/0-810 М14", None),
    ("no_load_speed", "Миксер Elitech CM2000ED2 2000Вт, 2х110мм", None),
    ("spindle_thread", "Миксер Makita UT1400, 1300Вт, 0-900об/мин, M14, 5,", "m14"),
    (
        "spindle_thread",
        "Миксер ЗУБР одинарный строительный 1100Вт, 0-600 об/мин М14, перемеш верх-низ",
        "m14",
    ),
    (
        "spindle_thread",
        "Миксер UM16VST;  1500Вт, М14, 150-300/300-650об/мин, плав. пуск, 5,6кг",
        "m14",
    ),
    ("spindle_thread", "Миксер строительный СМ-1600Э-2 РЕСАНТА", None),
    ("spindle_thread", "Миксер Einhell TE-MX 1600-2 CE, 1600Вт", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_MIKSERY)
def test_miksery(rules, axis, name, expected):
    got = _v(rules, "miksery", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_SVERLILNYE_STANKI = [
    ("power", "Станок сверлильный B16RM; 750Вт, б/з 16мм, 250-310", 750),
    (
        "power",
        "Станок сверлильный ЗУБР 350вт,патрон 13 мм, ход 50мм, посадка В16, тиски 63*63 мм",
        350,
    ),
    ("power", "Станок сверлильный Zitrek DP-116. 220В/600Вт/12скор/D16мм с тисками", 600),
    ("power", "Станок сверлильный ТС-BD 630, 630Вт, 250-2450об/ми", 630),
    ("power", "Станок сверлильный PROMA VR-6DF/230.1,5 квт, 6мм", None),
    ("power", "Станок сверлильный Калибр СС-13/400А", None),
    (
        "no_load_speed",
        "Станок сверлильный STURM BD7037 370Вт, 5скор 600-2600 об/мин патрон 13мм",
        2600,
    ),
    (
        "no_load_speed",
        "Станок сверлильный ЗУБР 450вт,патрон 16 мм, 12 скоростей,220-2450 об/мин, ход шпинделя 50мм, ЗУБР",
        2450,
    ),
    ("no_load_speed", "Станок сверлильный ТС-BD 630, 630Вт, 250-2450об/ми", None),
    ("no_load_speed", "Станок вертикально-сверлильный настольный 16 скоро", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_SVERLILNYE_STANKI)
def test_sverlilnye_stanki(rules, axis, name, expected):
    got = _v(rules, "sverlilnye-stanki", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_OTREZNYE_MASHINY_METALL = [
    ("power", "Машина отр. по метал. CC14SF;  2000Вт, d355х25,4мм", 2000),
    ("power", "Машина отр. по металлу Bosch GCO 14-24 J; 2400 Вт,", 2400),
    ("power", "Машина отр. по металлу STURM CF7325S 355мм, 2600Вт, 4200об/мин, пл пуск", 2600),
    ("power", "Машина отр. по метал. ОП-355/2500 Вихрь", None),
    ("power", "Машина отр. по металлу ДИОЛД ПМ-2,2-2", None),
    ("disc_diameter", "Машина отр. по метал. CC14ST;  2200Вт, d355х25,4мм, 3800об/мин", 355),
    ("disc_diameter", "Машина отр. по металлу Makita LW1401 2200Вт, d=355", 355),
    ("disc_diameter", "Машина отр. по металлу ЗУБР ПО-355 ф 355мм, 2400Вт ПРОФЕССИОНАЛ", 355),
    ("disc_diameter", "Машина отр. по металлу Elitach ПМ 1218, ф180мм", 180),
    ("disc_diameter", "Машина отр. по метал. ОП-355/2500 Вихрь", None),
    ("disc_diameter", "Машина отр. по металлу, камню, керамике Makita 241", None),
    ("no_load_speed", "Машина отр. по метал. CC14ST;  2200Вт, d355х25,4мм, 3800об/мин", 3800),
    (
        "no_load_speed",
        "Машина отр. по металлу STURM CF7325S 355мм, 2600Вт, 4200об/мин, пл пуск",
        4200,
    ),
    ("no_load_speed", "Машина отр. по металлу Metabo CS 23-355, 2300Вт, 355мм", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_OTREZNYE_MASHINY_METALL)
def test_otreznye_mashiny_metall(rules, axis, name, expected):
    got = _v(rules, "otreznye-mashiny-metall", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_PISTOLETY_KLEEVYE = [
    ("power", "Пистолет термо-клеевой  7мм RAPID 80Вт", 80),
    ("power", "Пистолет термо-клеевой KRAFTOOL д-11-12 мм, 220Вт, GRAND", 220),
    ("power", "Пистолет термо-клеевой Engy EGG-80, с подставкой, 80 Вт (PARK) арт.357118", 80),
    ("power", "Пистолет термо-клеевой, д-12 мм, 300вт, регул.темп", 300),
    ("power", "Пистолет термо-клеевой Bosch PKP 18E; 100-240В, 20", None),
    ("power", "Насадка сменная длинная с отверстием срезанным под углом KRAFTOOL", None),
    ("diameter", "Пистолет термо-клеевой 11 мм 45Вт Профи", 11),
    ("diameter", "Пистолет термо-клеевой ЗУБР d=7мм,", 7),
    ("diameter", "Пистолет термо-клеевой KRAFTOOL д-12 мм, 220Вт, PRO", 12),
    ("diameter", "Пистолет термо-клеевой 8 мм 30Вт Профи", 8),
    ("diameter", "Пистолет термо-клеевой KRAFTOOL д-11-12 мм, 220Вт, INDUSTRIAL 300", None),
    ("diameter", "Пистолет термо-клеевой ARZ-A-60-100 (+30 стержней)", None),
    ("diameter", "Пистолет термо-клеевой, METABO KE 3000", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_PISTOLETY_KLEEVYE)
def test_pistolety_kleevye(rules, axis, name, expected):
    got = _v(rules, "pistolety-kleevye", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_PLITKOREZY = [
    (
        "power",
        "Плиткорез ЗУБР ЭП-180-600, макс глубина 90°-34мм/45°-17мм, стол 330х360мм, 180х25.4х2.2мм, 600Вт",
        600,
    ),
    ("power", "Плиткорез Bosch GCT 115; 720Вт, 115мм, 1100об/мин,", 720),
    ("power", 'Плиткорез ПЭ 450 "Elitech" 450 вт, 2950 об/мин,115', 450),
    ("power", "Плиткорез 600мм  на подшипниках Remocolor", None),
    ("power", "Плиткорез ЗУБР ЗЭП-1400, макс глубина 90°-38 мм/45", None),
    ("power", "Режущий элемент д/плитк. 16/3мм  ЗУБР", None),
    ("disc_diameter", "Плиткорез ЗУБР МАСТЕР диск 200мм, 800Вт стол 690х3", 200),
    (
        "disc_diameter",
        "Плиткорез ЗУБР ЭП-180-600, макс глубина 90°-34мм/45°-17мм, стол 330х360мм, 180х25.4х2.2мм, 600Вт",
        180,
    ),
    (
        "disc_diameter",
        'Электроплиткорез ЗУБР "МАСТЕР", длина реза 1200 мм, диск 300 мм, глубина реза 90°-65мм/45°-40 мм, ст',
        300,
    ),
    ("disc_diameter", "Плиткорез Bosch GCT 115; 720Вт, 115мм, 1100об/мин,", 115),
    ("disc_diameter", "Плиткорез 600х14 мм MATRIX", None),
    ("disc_diameter", "Плиткорез 330мм  STAYER", None),
    ("disc_diameter", "Плиткорез ЗУБР ЗЭП-1100С, макс глубина 90°-30мм/45", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_PLITKOREZY)
def test_plitkorezy(rules, axis, name, expected):
    got = _v(rules, "plitkorezy", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_SVETILNIKI = [
    ("power", "Светильник  LED универсальный 36W 6500K", 36),
    ("power", "Светильник LED SPP-402-0-50K-150 IP65 150Bт 15000Лм 5000К ЭРА", 150),
    ("power", "Светильник Led Stick 90 см 1041led 22w6500k", 22),
    ("power", "Светильник светодиодный ДКУ-92Вт, IP67, 10000Лм, 5000К", 92),
    ("power", "Светильник взрывозащищенный НСП ВЗГ-200 1Х200Вт Е2", 200),
    ("power", "Драйвер ДВ 36,300mA для светильников 36Вт-25мм", None),
    (
        "power",
        "Светильник уличный консольный ДКУ 150, Вт 18000, лм 5000К АС 220В IP65 535х260х64мм",
        None,
    ),
    ("power", "Светильник светодиодный ДКУ-100 Победа", None),
    ("color_temperature", "Светильник  PPL 595/U 36w 6500K 3000Lm IP40 AC200-", 6500),
    ("color_temperature", "Светильник светодиод. ДВО, 36Вт,4500К,", 4500),
    ("color_temperature", "Светильник ОНЛАЙТ 71 686 OBL-R1-12-4K-WH-IP65-LED", 4000),
    ("color_temperature", "Светильник светодиод. Luxet Street 100-120-5К-NR-NL-6 MW", 5000),
    (
        "color_temperature",
        "Светодиодный светильник ЭРА SPO-7-72-6K-P 4 1200x180x19 72Вт 5000Лм 6500К призма",
        6500,
    ),
    ("color_temperature", "Светильник GAUSS матовый 7в 60*2,2*3 см 4100", None),
    ("color_temperature", "Светильник светодиодный уличный ДКУ-150Вт 840 IP65", None),
    ("color_temperature", "Светильник светодиод.ССП 40Вт 6500К 1200мм Фарлайт", 6500),
    ("color_temperature", 'Рассеиватель для 595*595 "Опал"', None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_SVETILNIKI)
def test_svetilniki(rules, axis, name, expected):
    got = _v(rules, "svetilniki", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"
