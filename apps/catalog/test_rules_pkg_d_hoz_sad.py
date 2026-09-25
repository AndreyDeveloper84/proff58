"""Пакет D: хозтовары, сад, стройка, бензо.

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


CASES_HOZ_TACHKI = [
    ("capacity", "Тачка двухколесная БЕЛАМОС 500P (200 кг)", "0.2"),
    ("capacity", "Тачка садовая 1 кол GRINDA (160кг) 90 л", "0.16"),
    ("capacity", "Тачка садовая одноколесная, 75 кг, 80 л, YARD", "0.075"),
    (
        "capacity",
        "Тачка строительная, 2-х колесная, усиленная, грузоподъемность 320 кг, объем 100 л// PALISAD",
        "0.32",
    ),
    ("capacity", "Тачка строительная 2-х колес. 1800 кг 90л. Т-21 ЗУБР", None),
    ("capacity", "Тележка-разбрасыватель (дозатор-сеялка) 44 кг/46л Great Wolt", None),
    ("capacity", "Тачка строит. 2-колесн., корыто оцинк. 1мм, 78л БИ", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_HOZ_TACHKI)
def test_hoz_tachki(rules, axis, name, expected):
    got = _v(rules, "hoz-tachki", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_OBOR_TELEZHKI = [
    ("capacity", "Тележка паллетная гидрвл. TOR RHP г/п 2,5 т, длинна вил 1,15м", "2.5"),
    (
        "capacity",
        "Тележка паллетная, гидравл. JUNGHEINRICH AM 22, гп 2,2 тн, длинна вилл 1150м ширина вил 550мм",
        "2.2",
    ),
    (
        "capacity",
        "Тележка паллетная, гидравл., PROLIFT AC 30, грузоподъемность 3000 кг, вилы 1150x550мм",
        "3",
    ),
    (
        "capacity",
        "Тележка платформ. с бортиком 40мм ТПО7-250 , 800*1400, (колёса d=250мм) г/п 450кг",
        "0.45",
    ),
    ("capacity", "Тележка паллетная гидравл. TOR DF-25 (2.5т)", "2.5"),
    (
        "capacity",
        "Тележка паллетная гидравлическая RHP 3000т, 1150х550 мм TOR полиуретановые колеса",
        None,
    ),
    ("capacity", "Тележка КГ-250 двухколёсная (колёса d=250мм), гп 2", None),
    ("capacity", "Тележка 200л ФЦ1В из нержавеющей стали aisi 304 для мясосырья", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_OBOR_TELEZHKI)
def test_obor_telezhki(rules, axis, name, expected):
    got = _v(rules, "obor-telezhki", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_HOZ_KOLESA = [
    ("diameter", "Колесо пневматическое 380 мм, КП-1 ЗУБР", "380"),
    (
        "diameter",
        "Колесо d=250 мм, г/п 210 кг, резина/металл, игольчатый подшипник, ЗУБР Профессионал",
        "250",
    ),
    ("diameter", "Колесо пенополиуретановое 360/65/16 мм", "360"),
    (
        "diameter",
        "Колесо запасное 4.80/4.00-8 D 380 мм, подш. вн. д.20 мм, длина оси 90 мм  для тачки PALISAD",
        "380",
    ),
    ("diameter", "Колесо запасное 4,8/4,00-80 d-16 мм", None),
    ("diameter", "Камера для пнемат. колеса 3,25/8 D360мм", None),
    ("diameter", "Колесо запасное 16'' х 4'' для тачки 77552", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_HOZ_KOLESA)
def test_hoz_kolesa(rules, axis, name, expected):
    got = _v(rules, "hoz-kolesa", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_HOZ_SHCHETKI = [
    ("width", "Щетка уличная 40см GRINDA с метал держателем для черенка 25мм", "400"),
    ("width", "Щетка тротуарная 400 мм", "400"),
    ("width", "Щетка для подметания, 300 мм, мягкий/расщеплённый", "300"),
    ("width", "Щетка для пола 26х9 см", "260"),
    ("width", "Щетка-швабра 600мм с металл.кроншт.d=22мм, б/ч, (д", "600"),
    ("width", "Щетка ЗУБР уличная деревянная с ручкой, волокно 90мм, ПЭТ, 140см, 40х7см", None),
    ("width", "Щетка-сметка АВТО 540мм ЗУБР со скребком", None),
    ("width", "Швабра резиновая с отжимом 126см, ширина 27см FIT", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_HOZ_SHCHETKI)
def test_hoz_shchetki(rules, axis, name, expected):
    got = _v(rules, "hoz-shchetki", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_HOZ_GRABLI = [
    ("teeth_count", "Грабли 12-зубые витые б/чер. г.Павлово", "12"),
    ("teeth_count", "Грабли веерные  22 плос.зуба, аллюм.черенок, ЗУБР", "22"),
    ("teeth_count", "Грабли витые 14  зубьев, 340 мм, нерж. сталь, без черенка СИБРТЕХ", "14"),
    ("teeth_count", "Грабли веерные оцинк.провол.18зуб ГВ-С 662", "18"),
    ("teeth_count", "Грабли витые 12-з  ПО ГВ-12", "12"),
    ("teeth_count", "Грабли веерные раздвижные ГВР-15 г.Москва", None),
    ("teeth_count", "Грабли пластиковые веерные регулируемые Gardena (насадка комбисистемы)", None),
    (
        "width",
        "Грабли GRINDA PS-12 WOOD 370х105х1300мм 12 зуб витые нерж сталь дерев черенок",
        "370",
    ),
    ("width", "Грабли витые РОСТОК 312х72мм 12 зуб без черенка", "312"),
    ("width", "Грабли веерные проволочные 450мм 22 зуба", "450"),
    (
        "width",
        "Грабли веерные стальные, 360 мм, 18 круглых зубьев, оцинкованные, без черенка, Россия// Сибртех",
        "360",
    ),
    ("width", "Грабли для сена большие 13зуб. длина 650мм", None),
    (
        "width",
        "Грабли веерные GRINDA GX-30 регулируемые дл 1240мм, шир 170-420мм стал, алюм черенок",
        None,
    ),
    ("width", "Грабли веерные РОСТОК PB-22L 385х450 пластинчатые без черенка", None),
    ("length", "Грабли GRINDA SR-10 цветочные 250х70х1550мм 10 зуб алюм черенок", "1550"),
    (
        "length",
        "Грабли веерные  22 плос.зуба, аллюм.черенок, 440 х 250 х 1630 мм GRINDA PROLine",
        "1630",
    ),
    ("length", "Грабли витые GRINDA PR-12T ALU 380х95х1500мм 12 зуб алюм черенок", "1500"),
    ("length", "Грабли веерные 15-зуб с черенком 1600мм PALISAD", None),
    ("length", "Грабли веерные GRINDA GP-22F 400х260х150мм 22 плоск зуба дерев черенок", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_HOZ_GRABLI)
def test_hoz_grabli(rules, axis, name, expected):
    got = _v(rules, "hoz-grabli", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_OBOR_SMAZKA = [
    ("thread_diameter", "Пресс-масленка GROZ для смазки, резьба 10ммх1мм прямая", "10"),
    ("thread_diameter", "Пресс-масленка БелАК M8x1 прямая (150 шт)", "8"),
    ("thread_diameter", "Пресс-масленка Н2, М 6х1 45 град. Pressol нерж. ст", "6"),
    ("thread_diameter", "Пресс-масленка GROZ 6 мм 45гр. GFT/6/1/45", "6"),
    ("thread_diameter", "яяПресс-маслёнка 8 мм прямая GFT/8/1", "8"),
    ("thread_diameter", 'Пресс-масленка GROZ прямая для смазки резба 1/8"Х28 BSPT', None),
    ("thread_diameter", 'Насадка на шприц G1/8" d15мм', None),
    ("thread_diameter", "Приспособление GROZ ESO/2 для замены пресс-масленок 9-11мм", None),
    ("thread_pitch", "Пресс-масленка для смазки, резьба 12ммх1,5мм прямая", "1.5"),
    ("thread_pitch", "Пресс-масленка GROZ для смазки, резьба 8ммх1мм угол 90 град", "1"),
    ("thread_pitch", "Пресс-масленка Н3, М 10х1, 90 град. Pressol нерж.", "1"),
    ("thread_pitch", "Пресс-масленка GROZ 6 мм 45гр. GFT/6/1/45", None),
    (
        "thread_pitch",
        'Шприц GROZ рычажный 500см3, 690 атм, стал трубка 150мм, 1г/ход, 1/8" BSPT',
        None,
    ),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_OBOR_SMAZKA)
def test_obor_smazka(rules, axis, name, expected):
    got = _v(rules, "obor-smazka", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_BP_MOTOBURY = [
    ("diameter", "Бур д/бурения земли 200мм HUTER", "200"),
    ("diameter", "Шнек почвенный CHAMPION 150мм", "150"),
    ("diameter", "Шнек для бензобура GIGANT 250х800мм", "250"),
    ("diameter", "Бур 200мм Profi 2х.шнек с накопителем ф27 Slit", "200"),
    ("diameter", 'Бур д/бурения земли EBF-12; d 12", 880х840 мм (для DA300E)', None),
    ("diameter", "Мотобур ЗУБР МБ1-200Н ф 60-200мм, 52см3, со шнеком ф150ммх800мм", None),
    ("diameter", "Удлинитель для шнека L1000мм ЗУБР", None),
    ("power", "Мотобур CHAMPION AG252 (1,46кВт, 51,7см3, 9,2кг) шнек 200х550мм", "1460"),
    ("power", "Мотобур PEGAS P-GD1600, 3600Вт без шнека", "3600"),
    ("power", "Мотобур DA300E;  1,54кВт,", "1540"),
    ("power", "Мотобур HUTER GGD-52", None),
    ("power", "Бензобур ADA Ground Drill-8 А00367", None),
    ("engine_displacement", "Мотобур STURM EA1520, 53см3, 2,4кВт/3,2лс", "53"),
    ("engine_displacement", "Мотобур CHAMPION AG352 (1,4кВт, 51,7см3, 9,4кг) без шнека", "51.7"),
    (
        "engine_displacement",
        "Мотобур ЗУБР МБ2-300Н ф 60-300мм, 71см3, со шнеком ф250ммх800мм",
        "71",
    ),
    ("engine_displacement", "Мотобур ДИОЛД МР-1-62", None),
    ("engine_displacement", "Шнек почвенный CHAMPION 100мм", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_BP_MOTOBURY)
def test_bp_motobury(rules, axis, name, expected):
    got = _v(rules, "bp-motobury", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_BP_VOZDUKHODUVKI = [
    ("power", "Воздуходувка бенз CHAMPION GB226 (0.75кВт, 26см3, 4кг, 512м3/ч)", "750"),
    ("power", "Воздуходувка бенз ECHO PB-770 (2,85кВт 63,3см3,1314м3/ч 104,6м/с 10,8кг)", "2850"),
    ("power", "Воздуходувка бенз RB65EF;  64.7см3, 3кВт,", "3000"),
    ("power", "Воздуходувка бензиновая RB24E; 23,9 см3, 0,84кВт,1", "840"),
    (
        "power",
        "Воздуходувка аккум DENZEL RB180-36, Li-ion 36В 4Ач, 180км/ч 820м3/ч 2 аккум 18В 4Ач",
        None,
    ),
    ("power", "Воздуходувка бензиновая Makita BHX2501", None),
    (
        "engine_displacement",
        "Воздуходувка бенз CHAMPION GBR333 (0,9кВт, 32,6см3, 6,4кг, 800м3/ч",
        "32.6",
    ),
    ("engine_displacement", "Воздуходувка бензиновая STURM GB1963 63,3сс, 1440м3/ч", "63.3"),
    ("engine_displacement", "Воздуходувка бензиновая RB24EA; 23,9 см3, 0,84кВт,", "23.9"),
    ("engine_displacement", "Воздуходувка бенз RB100EF;  43.1см, 2,0 кВт,", None),
    (
        "engine_displacement",
        "Воздуходувка аккумуляторная Einhell TE-CB 18 Li-Solo без АККУМ и ЗУ",
        None,
    ),
    ("weight_kg", "Воздуходувка бенз CHAMPION GB227 (0.7кВт, 26см3, 4,2кг, 720м3/ч)", "4.2"),
    ("weight_kg", "Воздуходувка бенз CHAMPION GBR476 (3,3кВт, 75,6см3, 12,4кг, 1480м3/ч)", "12.4"),
    ("weight_kg", "Воздуходувка бенз ECHO PB-2520 (0,91кВт 25,4см3,768м3/ч, 3,9кг)", "3.9"),
    ("weight_kg", "Воздуходувка бенз RB65EF;  64.7см3, 3кВт,", None),
    ("weight_kg", "Воздуходувка бензиновая ранцевая SBP 375 Stiga 255", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_BP_VOZDUKHODUVKI)
def test_bp_vozdukhoduvki(rules, axis, name, expected):
    got = _v(rules, "bp-vozdukhoduvki", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_VIBRATORY_BETONA = [
    ("power", "Вибратор портативный STURM CV71101 1000Вт, вал 35мм 1м", "1000"),
    (
        "power",
        "Вибратор глубинный по бетону ENAR DINOGO (2,3 кВт, 220В, 1800 об/мин, 5,4 кг) (привод)",
        "2300",
    ),
    (
        "power",
        "Вибратор площадочный ИВ-99Б 380В 0,25кВт потребл. 0,50кВт 12кг 3000колеб/мин Кр. Маяк Ярославль",
        "250",
    ),
    ("power", "Вибратор ручной 850Вт вал 1м, вибронаконечник 35мм", "850"),
    ("power", "Вибратор портативный Zitrek Z-1100 (220В) вал 2,0", None),
    (
        "power",
        "Вал гибкий ВС-350 (ЭВ-260) L=4,5м 16кг к любым электроприводам для глубинного вибратора",
        None,
    ),
    ("voltage", "Вибратор площадочный ИВ-127Э (380 В) 0,12кВт 0,63-", "380"),
    ("voltage", "Вибратор портативный Zitrek Z-900 (220В) вал 2,0 м", "220"),
    (
        "voltage",
        "Электропривод к вибратору ИВ-117 (ИВ-75, ИВ-113, ИВ-116) 42В 3-х фазн. 1,4кВт 12,5кг 18000колеб/мин",
        "42",
    ),
    ("voltage", "Вибратор глубинный VPK 65T/42/5/10 ВЧ подключаемый к преобразователю", None),
    ("voltage", "Вибратор портативный PIT 1100Вт, вал 1,5м", None),
    (
        "weight_kg",
        "Вибратор глубинный по бетону ENAR DINOGO (2,3 кВт, 220В, 1800 об/мин, 5,4 кг) (привод)",
        "5.4",
    ),
    (
        "weight_kg",
        "Вал гибкий ВС-400 (ЭВ-260.02) L=4,5м 16кг к любым электроприводам для глубинного вибратора",
        "16",
    ),
    (
        "weight_kg",
        "Вибронаконечник d=51мм к валу гибкому ВС-350 4,5кг (ИВ-117А) Кр. Маяк Ярославль для глубинного вибра",
        "4.5",
    ),
    ("weight_kg", "Вибратор площадочный ИВ-98Б 380В Красны Маяк", None),
    (
        "weight_kg",
        "Вибратор портативный Zitrek ZKVD1500 (220В) вал 2,0м со встроенной булавой ф 35мм",
        None,
    ),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_VIBRATORY_BETONA)
def test_vibratory_betona(rules, axis, name, expected):
    got = _v(rules, "vibratory-betona", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_STR_PRAVILA = [
    ("length", "Правило 1,5 м алюм, с ребром жесткости СИБИН", "1500"),
    ("length", "Правило  1м с ребром жесткости STAYER ДВУХВАТ", "1000"),
    ("length", "Правило 3.0 м с ребром жесткости Трапеция STAYER", "3000"),
    ("length", 'Правило "БИ-Металл", 2,5 м, ЗУБР', "2500"),
    ("length", "Правило для финишной отделки 2 м FINISH STAYER Pro", "2000"),
    ("length", "Отвес 300г строительный со шнуром STAYER 5м", None),
    ("length", "Шнур-отвес разметочный 30м 110г STAYER", None),
    ("length", "Отвес 100 г., строительный длина шнура 5м", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_STR_PRAVILA)
def test_str_pravila(rules, axis, name, expected):
    got = _v(rules, "str-pravila", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_LEBEDKI_TALI = [
    (
        "capacity",
        'Лебедка 0,5т, 8м ручная барабанная ЗУБР "ПРОФЕССИОНАЛ", тяговая, ленточная',
        "0.5",
    ),
    ("capacity", "Таль рычажная MEKO г/п 1,5тн, высота подъёма 6м (M", "1.5"),
    ("capacity", "Таль ручная шестеренная TOR ТРШ (C) 0,5тх3м", "0.5"),
    ("capacity", "Лебедка барабанная TOR ТЛ-5Т г/п 5000 кг Н-130 м (без каната)", "5"),
    ("capacity", "Лебедка потолочная 1600 кг", "1.6"),
    ("capacity", "Лебедка  0,75/1,5 т  СЕРВИС КЛЮЧ", None),
    ("capacity", "Лебедка рычажная, тяга - 2т, подъем - 0,8т, двойно", None),
    ("capacity", "Таль электрическая QUATRO ELEMENTI TL-1000, 1600Вт, 500/1000кг, трос 12м", None),
    ("capacity", "Труборез 10 - 60 мм ЗУБР ТС-700 для стальных труб", None),
    ("lift_height", "Таль цепная 1т высота подъема 2,5м STAYER PROF", "2500"),
    ("lift_height", "Таль рычажная ручная HSZ-E г/п 1,0 т. (Н= 6 м.) Ки", "6000"),
    ("lift_height", "Таль ручная цепная GEARSEN HSZ-C, 2 т, 9 м", "9000"),
    ("lift_height", "Таль ручная шестеренная TOR ТРШ (C) 0,5тх6м", "6000"),
    ("lift_height", "Тельфер электрический 0,8т, 1300Вт высота 12м TF-8", "12000"),
    (
        "lift_height",
        'Лебедка 0,9т, 10м ручная барабанная ЗУБР "ПРОФЕССИОНАЛ", тяговая, ленточная',
        None,
    ),
    ("lift_height", "Таль электрическая TOR PA-250/500кг, 20/10м", None),
    ("lift_height", "Таль балансир 2,0-4,0 кг,ход троса 2,5м", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_LEBEDKI_TALI)
def test_lebedki_tali(rules, axis, name, expected):
    got = _v(rules, "lebedki-tali", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"
