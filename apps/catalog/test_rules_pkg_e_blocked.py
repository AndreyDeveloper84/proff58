"""Пакет E: типы, помеченные BLOCKED_BY_ATTRIBUTE — оси нашлись в БД.

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
            if v.boolean is not None:
                return v.boolean
            return v.option_slug or v.number
    return None


def _eq(got, exp):
    if exp is None or got is None:
        return got is None and exp is None
    if isinstance(got, bool) or isinstance(exp, bool):
        return got is exp
    if isinstance(got, str):
        return got == str(exp)
    return got == Decimal(str(exp))


CASES_BP_CEPI = [
    ("chain_pitch", 'Цепь 50 зв 3/8" 1,3мм HANSKONNER получизель', "pitch-3-8"),
    ("chain_pitch", "Цепь 64 зв шаг-0,325, паз-1,3мм PRO (BP) CHAMPION", "pitch-0-325"),
    ("chain_pitch", 'яяЦепь 15" .325 Пиксель 1.3 H30 E64', "pitch-0-325"),
    ("chain_pitch", "Цепь 36 звеньев C9 1/4 для ELS-20LI  HUTER", "pitch-1-4"),
    ("chain_pitch", 'яяЦепь 16" .3/8 Пиксель .050/1.3мм Н36 56E', "pitch-3-8"),
    ("chain_pitch", "яяЦепь 62 зв 3,25, 1,6 (26RSC/RSC3)  Stihl", None),
    ("chain_pitch", "Цепь передаточная 726405", None),
    ("chain_pitch", "яяЦепь 46 зв., 1,1мм Rezer для MAKITA.BOSCH", None),
    ("chain_gauge", "Цепь 40 зв шаг-3/8, паз-1,3мм PRO (VS) CHAMPION", 1.3),
    ("chain_gauge", 'Цепь 15" 3/8 ЛоуВиб .058/1.5 56 H42 Е56', 1.5),
    ("chain_gauge", 'Цепь 50 зв 3/8" 1,1мм HANSKONNER', 1.1),
    ("chain_gauge", 'Шина с цепью CHAMPION 16"-3/8-1,6-60', 1.6),
    ("chain_gauge", "яяЦепь 64 зв, 0,325,1,3 мм FORZA", 1.3),
    ("chain_gauge", 'Цепь 18" ЗУБР тип 2, шаг 0,325", паз 0,058", для шины  (45 см)', None),
    ("chain_gauge", 'яяЦепь 56 зв., 3/8, 16" OREGON', None),
    ("chain_gauge", 'Цепь 45 звена C10 1/4  8" HUTER для ELS-20/8', None),
    ("chain_links", 'Цепь 57 звеньев C1 3/8 1.3мм 16" HUTER', 57),
    ("chain_links", 'яяЦепь 28" 3/8 91зв 1,6мм Stihl', 91),
    ("chain_links", 'Шина с цепью CHAMPION 14"-3/8-1,3-50', 50),
    ("chain_links", 'яяЦепь 15" 0.325 Пиксель 1,3 H30 E64 для пилы 440, 4', 64),
    ("chain_links", 'яяЦепь 18" 3/8 ЛоуВиб .058/1,5 68 H42 для пилы 365', 68),
    ("chain_links", 'Шина с цепью 40см (16"), 0,325" 1,3мм(0,050) 66', 66),
    ("chain_links", 'Цепь 50 зв.  3/8" , 1,3мм 14" REZER', 50),
    ("chain_links", 'яяЦепь 16" 3/8" 1,3 Oleo-Mac', None),
    ("chain_links", 'яяЦепь 45см шаг 3/8", паз 1,3мм MAKITA', None),
    ("chain_links", "Цепь передаточная 726406", None),
    ("bar_length", 'Цепь 64 зв., 15"/38см, 3/8", 1.5мм, CHAMPION', 380),
    ("bar_length", 'Цепь 18" ЗУБР тип 2, шаг 0,325", паз 0,058", для шины  (45 см)', 450),
    ("bar_length", 'яяЦепь 92 зв., 3/8", 1.5 мм, H42, 28"/71см', 710),
    ("bar_length", "Цепь 40 зв 25см, шаг-3/8, паз-1,3мм HITACHI", 250),
    ("bar_length", 'Цепь 57 звеньев C1 3/8 1.3мм 16" HUTER', None),
    ("bar_length", 'Шина с цепью CHAMPION 15"-0,325-1,5-64', None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_BP_CEPI)
def test_bp_cepi(rules, axis, name, expected):
    got = _v(rules, "bp-cepi", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_BP_SHINY = [
    ("chain_pitch", 'Шина 16" 3/8" 1.3mm 56 HANSKONNER', "pitch-3-8"),
    ("chain_pitch", 'Шина 18" 0,325" 1.5mm 72 CHAMPION', "pitch-0-325"),
    ("chain_pitch", 'Цепь 66 зв.шаг 325, , 1.5, шина 16"  HUSQVARNA', "pitch-0-325"),
    ("chain_pitch", 'яяШина для пилы OREGON 16" D.G. паз 1,3 шаг 3,8 хвос', None),
    ("chain_pitch", "Шина направляющая Makita для SP6000; 1,4 м", None),
    ("chain_gauge", 'Шина 14" 3/8" 1.1mm 50 Hanskonner', 1.1),
    ("chain_gauge", 'Шина 18"-0,325-1,5-72 для BS-45, BS-52M HUTER', 1.5),
    ("chain_gauge", 'яяШина 14" 1,3мм/0,05 3/8" R35 Stihl', 1.3),
    ("chain_gauge", 'яяШина 35см 3/8",1,3 Stihl', 1.3),
    ("chain_gauge", "Шина направляющая Hitachi ; 1,4 м", None),
    ("chain_gauge", 'яяШина пильная 15 " Hitachi', None),
    ("chain_links", 'Шина 16" 3/8" 1.3mm 56 HANSKONNER', 56),
    ("chain_links", 'Шина 18"-3/8 63зв CS-181Е для электропилы Huter ELS-2400, ELS-2800', 63),
    ("chain_links", 'Шина 16" 3/8" 1.3мм -56 HUSQVARNA', 56),
    ("chain_links", 'яяШина 15" 0,325" 1.3mm 64E RedVerg', 64),
    ("chain_links", 'яяШина 18" 3/8" SN, 1.5 мм, 68 (5859508-68)', 68),
    ("chain_links", 'яяШина 16" 3/8" 1.3 E1700, 1900, 936, 940 Oleo-Mac', None),
    ("chain_links", 'яяШина 16" 3/8" 5019592-56 HUSQVARNA', None),
    ("chain_links", "Шина направляющая CG-150. 1500мм KRAFTOOL", None),
    ("bar_length", 'Шина 16"/40см 0,325" 1.3mm 66 DDE', 400),
    ("bar_length", 'яяШина 45см шаг 3/8", паз 1,3мм MAKITA', 450),
    ("bar_length", 'яяШина 40 см /1,3 мм, 3/8" + цепь (2 шт) Oregon', 400),
    ("bar_length", 'Шина 20" 3/8" 1.3mm 72 CHAMPION', None),
    ("bar_length", "Шина направляющая ППШ-300, 3000мм ЗУБР", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_BP_SHINY)
def test_bp_shiny(rules, axis, name, expected):
    got = _v(rules, "bp-shiny", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_GAIKOVERTY = [
    ("torque", "Гайковерт аккум Einhell PXC Impaxxo 18/400, 18В, 400Нм без АККУМ и ЗУ", 400),
    (
        "torque",
        'Гайковерт аккум. ЗУБР ГБУ-1000-41 20 В, 3/4" 1000 Н·м, 1 АКБ LMS (4 А·ч), бесщеточный',
        1000,
    ),
    (
        "torque",
        "Гайковерт аккум. ЗУБР GB-500 500Hm 20В бесщеточная без АКБ и ЗУ Профессионал. в коробке",
        500,
    ),
    (
        "torque",
        'яяГайковерт аккум ударный AEG BSS18C12ZBL LI-402C [квадрат 1/2", ударный, 2700 об/мин, 500 Н*м, 18',
        500,
    ),
    (
        "torque",
        "Гайковерт аккум ударный Metabo SSW 18 LTX 300 BL Акк.гайковерт,18В,300Нм,1/2 без зу и аккум",
        300,
    ),
    ("torque", 'Гайковерт удар. ЗУБР ЗГУЭ-350 ударный, 300Нм, 1/2", 2,9кг, 350Вт', 300),
    ("torque", "Гайковерт удар. Metabo SSW 650", None),
    ("torque", "Гайковерт аккум ударный Metabo SSW 18 LTX 300 BL 18V 2х4а/ч", None),
    ("torque", 'Гайковерт аккум РЕСАНТА АГ-300/20Li 300Нм, 1/2" 2АКБ', 300),
    ("voltage", "Гайковерт аккум ударный WR14DSL;14,4V,2х3А/ч,Li-io", 14.4),
    ("voltage", 'Гайковерт аккум ударный MAKITA XGT BL 40В, 1/2", 750Нм, 2х2,5Ач', 40),
    ("voltage", "Гайковерт аккум ударный GDS 18 V-LI Bosch; 18В, 2х", 18),
    ("voltage", "Гайковерт аккум. ЗУБР 18 В, 1.7 Ач Li-Ion, 350 Нм, ЗУБР", 18),
    ("voltage", 'Гайковерт аккум РЕСАНТА АГ-300/20Li 300Нм, 1/2" 2АКБ', None),
    ("voltage", 'Гайковерт удар. ЗУБР ГС-300 К ударный, 300Нм, 1/2" в кейсе', None),
    (
        "voltage",
        'Гайковерт удар. Makita TW1000; 1200Вт, 1000Нм, 1", 1400об/мин, 1500уд/мин, М24-М30, реверс, 8,4кг',
        None,
    ),
    ("power", 'Гайковерт удар. Einhell CC-IW 950, 950Вт, 450Нм 1/2"', 950),
    ("power", 'Гайковерт удар. Makita 6906, 850 Вт, 3/4", 588 Нм', 850),
    ("power", 'Гайковерт удар. STURM ID2111 1000Вт, 1/2", 380Нм', 1000),
    ("power", 'Гайковерт аккум THORVIK бесщеточный  1" 21В 2400Нм BBIW012400', None),
    ("power", "Гайковерт удар. Einhell CC-IW 450.450Вт, 300Нм, 1/2", None),
    ("drive", 'Гайковерт аккум Makita DTW251RME 18В, 230Нм, 1/2" 2акк*4Ач', "d-1-2"),
    ("drive", 'Гайковерт аккум THORVIK бесщеточный 3/4" 21В 1700Нм BBIW341700', "d-3-4"),
    ("drive", 'Гайковерт удар. WR25SE; 900Вт; 1000Нм, 1", 1100об/', "d-1"),
    (
        "drive",
        "Гайковерт аккум ударный Metabo SSW 18 LT 300 BL Акк.гайковерт,18В,300Нм,1/2 без зу и аккум",
        "d-1-2",
    ),
    (
        "drive",
        "Гайковерт аккум ЗУБР ГУЛ-410-41, 18В, 400Нм 1 АКБ (4Ач), в кейсе, гайковерт ударный. ЗУБР",
        None,
    ),
    ("drive", "Гайковерт аккум Makita DTW285RME", None),
    ("battery_capacity", 'Гайковерт аккум Hanskonner HCD18350S 18В 350Нм 1/2", 2х2,4Ач кейс', 2.4),
    ("battery_capacity", "Гайковерт аккум Makita DTW300RTJ 18В, 330Нм 2х5,0А/ч ЗУ", 5.0),
    ("battery_capacity", "Гайковерт аккум. ЗУБР 18 В, 1.7 Ач Li-Ion, 350 Нм, ЗУБР", 1.7),
    ("battery_capacity", 'Гайковерт аккум THORVIK бесщеточный 3/4" 21В 2400Нм BBIW342400', None),
    ("battery_capacity", 'Гайковерт удар. WR22SA; 850Вт; 610Нм, 3/4", 1800об', None),
    ("power_source", "Гайковерт аккум Makita DTW285RME", "battery"),
    (
        "power_source",
        "Гайковерт аккум. ударный DENZEL безщеточ CIW-IB-300-0, Li-ion 18В 300Нм БЕЗ аккум",
        "battery",
    ),
    (
        "power_source",
        'Гайковерт удар. WR16SE; 450Вт; 360Нм 1/2", бесщ.,1900об/мин,2100уд/мин М12-М22,эл.тормоз, 2,4кг',
        "mains",
    ),
    ("power_source", "Гайковерт удар. Makita TW 0350", None),
    ("power_source", "Гайковерт угловой Makita LXT 18V", None),
    (
        "motor_type",
        "Гайковерт аккум Hanskonner HCD18100S 18В 1000Нм бесщеточнаый без аккум и зу",
        "brushless",
    ),
    ("motor_type", 'Гайковерт удар. WR14VE; 500Вт; 250Нм,1/2",бесщет.,', "brushless"),
    (
        "motor_type",
        "Гайковерт аккум. ударный DENZEL безщеточ CIW-IB-300-0, Li-ion 18В 300Нм БЕЗ аккум",
        "brushless",
    ),
    ("motor_type", 'Гайковерт аккум Makita DTW251RME 18В, 230Нм, 1/2" 2акк*4Ач', None),
    ("motor_type", "Гайковерт удар. DW 292 DeWalt", None),
    ("battery_included", "Гайковерт аккум Makita DTW190Z (без аккум. и з/у)", False),
    (
        "battery_included",
        "Гайковерт аккум ударный Ryobi ONE+ R18IW3-0 3002436 без аккумулятора в комплекте",
        False,
    ),
    (
        "battery_included",
        "Гайковерт аккум ЗУБР ГУЛ-410-41, 18В, 400Нм 1 АКБ (4Ач), в кейсе, гайковерт ударный. ЗУБР",
        True,
    ),
    (
        "battery_included",
        'Гайковерт аккум THORVIK бесщеточный 1/2" 20В  700Нм BWI2037 2аккум 4А/ч',
        True,
    ),
    ("battery_included", 'Гайковерт аккум Makita DTW251RME 18В, 230Нм, 1/2" 2акк*4Ач', None),
    ("battery_included", 'Гайковерт удар. STURM ID2111 1000Вт, 1/2", 380Нм', None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_GAIKOVERTY)
def test_gaikoverty(rules, axis, name, expected):
    got = _v(rules, "gaikoverty", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_ZAP_TARELKI_OPORNYE = [
    (
        "disc_diameter",
        "Тарелка опорная 125 мм ЗУБР МАСТЕР резиновая для дрели под круг на липучке, шпилька 8мм",
        125,
    ),
    (
        "disc_diameter",
        "Тарелка опорная 100 мм ЗУБР алюминиевая для УШМ под круг на липучке, М14",
        100,
    ),
    ("disc_diameter", "Тарелка опорная 125мм для ЭШМ 125 КИТАЙ", 125),
    (
        "disc_diameter",
        "Тарелка опорная 180 мм ЗУБР ПРОФЕССИОНАЛ плстик для УШМ под фибр круг, посадка М14",
        180,
    ),
    ("disc_diameter", "Тарелка опорная шлифовальная EINHELL TC-DW 225", None),
    ("mount", "Тарелка опорная 125 мм STAYER пластиковая для УШМ на липучке, М14", "m14"),
    ("mount", "Тарелка опорная 115 мм; M14 QUICK-STICK", "m14"),
    (
        "mount",
        "Тарелка опорная 125 мм ЗУБР МАСТЕР резиновая для дрели под круг на липучке, шпилька 8мм",
        "shpilka",
    ),
    ("mount", "Тарелка опорная 150мм под липучку для дрели и УШМ", None),
    ("mount", "Тарелка опорная 125мм аналог MAKITA 743081-8", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_ZAP_TARELKI_OPORNYE)
def test_zap_tarelki_opornye(rules, axis, name, expected):
    got = _v(rules, "zap-tarelki-opornye", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_KABEL_PROVOD = [
    ("cable_section", "Кабель ВВГ-Пнг(A)-LS 3х2,5 ГОСТ", "3x2-5"),
    ("cable_section", "Провод ПВС 2x1,5 ГОСТ 50м Партнер-Электро", "2x1-5"),
    ("cable_section", "Кабель КГВВнг(А)- LS 3 х 2,5", "3x2-5"),
    ("cable_section", "Провод ПВС 4х1.5 (бухта) (50м) ЭлектрокабельНН M00", "4x1-5"),
    ("cable_section", "Провод ШВВП 2 х 0,75", "2x0-75"),
    ("cable_section", "Кабель КГтп-ХЛ 3х2,5+1х1,5", None),
    ("cable_section", "Кабель КВВГнг- LS 10х2,5", None),
    ("cable_section", "Кабель КГ 2х16", None),
    (
        "cable_section",
        "Витая пара UTP 4 пары AWG 24 Cat.5e внутренняя CCA Net.on 305м (UTP 4х2х0,5In/CCA)",
        None,
    ),
    ("cable_length", "Провод ПВС 2х1,5 ГОСТ 50м", 50),
    ("cable_length", "Кабель витая пара UTP 4PR 305м", 305),
    ("cable_length", "Кабель для электроинструмента 1,5ммх3м", 3),
    ("cable_length", "Кабель силовой ВВГ-Пнг(А)-LS 3х1.5ок(N.PE)-0.66 100м ТРТС", 100),
    ("cable_length", "Кабель саморегулир. греющий Proconnect SRL 16-2 (неэкранит) (16Вт/1м)", None),
    ("cable_length", "Кабель спиральный 24V, Type N, 7 pol., 4500мм, ISO1185", None),
    ("cable_length", "Кабель КГ 3х2,5", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_KABEL_PROVOD)
def test_kabel_provod(rules, axis, name, expected):
    got = _v(rules, "kabel-provod", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"
