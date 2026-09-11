"""Пакет C: сварка и СИЗ.

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


CASES_SVAR_PROVOLOKA = [
    ("diameter", "Проволока алюминиевая ER-4043 (Al Si 5.) ф 1,0мм 2кг", "1.0"),
    ("diameter", "Проволока порошковая E71T-GS д. 0,8 (1,0кг)", "0.8"),
    ("diameter", "Проволока сварочная омедненная 1,2/15 кг", "1.2"),
    ("diameter", "Проволока сварочная омедненная СВ-08Г2С-О Ф-0,8/5", "0.8"),
    ("diameter", "Пруток присадочный по чугуну DT-NiFe d 3.2 мм", "3.2"),
    ("diameter", "Пруток БраЖ 9-4 ф100мм", None),
    ("diameter", "Припой ПОС 61 пруток ф-8.0 мм", None),
    ("diameter", "Пруток Л63 ф 16", None),
    ("weight_kg", "Проволока алюминиевая ER-5356 (Al Mg 5.) ф 0,8мм 2кг", "2"),
    ("weight_kg", "Проволока сварочная омедненная 0,8/15 кг", "15"),
    ("weight_kg", "Проволока сварочная нержавеющая SELLER ER-308LSi  д. 0,8мм, кат.1кг", "1"),
    ("weight_kg", "Проволока сварочная флюсовая 0,8 мм, 0,45 кг.", "0.45"),
    ("weight_kg", "Проволока сварочная омедненная Св-08Г2С-0 2,0мм-10", None),
    ("weight_kg", "Припой ПОС 61 проволока ф-3.0 мм (катушка 100 гр)", None),
    ("material", "Проволока сварочная порошковая E71T-GS (1 кг; 0.8 мм)", "poroshkovaya"),
    ("material", "Пруток алюминиевый TIG 5356 d 2,4 мм AiMg5", "alyuminiy"),
    ("material", "Пруток присадочный по нержавейке ф2,0мм", "inox"),
    ("material", "Пруток омедненный TIG ER 70S-6/SG2. СВ-08Г2С, ф 2мм", "omednennaya-stal"),
    ("material", "Проволока Е71Т-GS GROVERS d 0.8 мм 1 кг", "poroshkovaya"),
    ("material", "Пруток присадочный по чугуну DT-NiFe d 3.2 мм", None),
    ("material", "Припой медно-фосфорный ХАРРИС-0 пруток 1.3х3.2х500мм 20гр", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_SVAR_PROVOLOKA)
def test_svar_provoloka(rules, axis, name, expected):
    got = _v(rules, "svar-provoloka", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_SIZ_STEKLA = [
    ("width", "Стекло для маски сварщика 110x90 DIN 10 (комтлект темное+прозрачное) РОСОМЗ", "110"),
    (
        "width",
        "Стекло для маски сварщика ЗУБР 115,2х104мм (5шт) мод 11070,11073,11076 поликарбонат 1мм",
        "115.2",
    ),
    ("width", "Стекло защитное (поликарб.) 114*133 наружное", "114"),
    ("width", "Стекло для масок сварщика FUBAG 40х107мм OPTIMA внутреннее", "40"),
    ("width", "Стекло внешнее защитное для маски сварщика Hanskonner 380х1550мм HAW180VIEW", None),
    ("width", "Набор стекол защитных для маски сварщика KRAFTOOL EXTREM мод 11062", None),
    ("width", "Стекло защитное (поликарб.)  ф50мм Г2 круглое", None),
    ("length", "Стекло для маски сварщика 110x90 DIN 10 (комтлект темное+прозрачное) РОСОМЗ", "90"),
    (
        "length",
        "Стекло для маски сварщика ЗУБР 115,2х104мм (5шт) мод 11070,11073,11076 поликарбонат 1мм",
        "104",
    ),
    ("length", "Стекло поликарбонат 1мм, сменное для маски ЗУБР МАСТЕР 200х400мм", "400"),
    ("length", "Стекло для масок сварщика FUBAG 47х96мм BLITZ 9,13 внутреннее новый корпус", "96"),
    ("length", "Стекло для масок сварщика Ultima (внешнее 133.35х1", None),
    ("length", "Стекло для замешивания без лунок", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_SIZ_STEKLA)
def test_siz_stekla(rules, axis, name, expected):
    got = _v(rules, "siz-stekla", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_SVAR_MASKI = [
    ("width", 'Маска сварщика "Хамелеон"ЗУБР АР 9-13 затемнение 4/9-13 стекло 95х34мм', "95"),
    ("width", 'Маска сварщика "Хамелеон" Fubag ULTIMA 9-13, зона обзора 100ммх49мм', "100"),
    ("width", 'Маска сварщика "Хамелеон" ULTIMA 5-13 Visor (зона обзора 100 мм х 67 мм)', "100"),
    ("width", "Маска сварщика (110*90)", "110"),
    (
        "width",
        "яяМаска сварщика Зубр МАСТЕР 92x42мм, изменяемое затемнение 9-13, режим Шлифование",
        "92",
    ),
    ("width", 'Маска сварщика "Хамелеон" Hanskonner 108х82/74х50х59мм DIN 3/4-8/9-13', None),
    ("width", 'Маска сварщика "Хамелеон" KRAFTOOL EXTREM затемнение 3/4-8/9-13', None),
    ("width", "Маска сварщика ЗУБР МС-10, стеклянный светофильтр, затемнение 10", None),
    ("length", 'Маска сварщика "Хамелеон"ЗУБР АР 9-13 затемнение 4/9-13 стекло 95х34мм', "34"),
    (
        "length",
        'Маска сварщика "Хамелеон" Fubag BLITZ 9.13 VISOR экран 133х114 мм. автомат.затемнение с 3-мя регулир',
        "114",
    ),
    ("length", "Светофильтр ТС-3 121х69 С-4 (DIN 9)", "69"),
    ("length", "Маска сварщика 102х52мм с откидным стеклом НН-С 702", "52"),
    ("length", 'Маска сварщика "Хамелеон" Hanskonner 108х82/74х50х59мм DIN 3/4-8/9-13', None),
    ("length", "Маска сварщика 400 PATRIOT", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_SVAR_MASKI)
def test_svar_maski(rules, axis, name, expected):
    got = _v(rules, "svar-maski", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_SIZ_RUKAVA = [
    ("diameter", "Рукав напорный всасывающий ф100, 4 м В-1 ГОСТ 5398", "100"),
    ("diameter", "Рукав напорно-всасывающий ПВХ  19мм со спиралью 30м, 10атм", "19"),
    (
        "diameter",
        "Рукав пожарный РПК(В)-Н/В-100-0,8-М-УХЛ1 «Классик»  для пожар. кранов и мотопомп масл. морозостойкий",
        "100",
    ),
    (
        "diameter",
        'Рукав пожарный РПМ (П)-65-1,6-М-УХЛ1 "Типа Латекс" с внутренним гидроизоляционным покрытием из полим',
        "65",
    ),
    ("diameter", "Рукав напорный всасывающий 80 с головкой ГР-80 (4м)", "80"),
    ("diameter", "Рукав резиновый В-2-75-3 6 м", "75"),
    ("diameter", "Рукав для воды В (II) 50-64 мм (10 атм) ГОСТ 18698-79 (м)", None),
    ("diameter", 'Рукав напорно-всасывающий для мотопомпы FHT 2/8  2" / 8 м Fubag', None),
    ("diameter", "Задержка рукавная ЗР-80", None),
    ("diameter", "Мостик рукавный МПР-80 металл.", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_SIZ_RUKAVA)
def test_siz_rukava(rules, axis, name, expected):
    got = _v(rules, "siz-rukava", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_SVAR_RUKAVA = [
    ("diameter", "Рукав резин для газосварки 6,3мм бухта 40м класс3", "6.3"),
    ("diameter", "Рукав резин для газосварки 9мм бухта 10м цвет крас", "9"),
    ("diameter", "Рукав с нит. усил. 14х23мм (16Атм) ГОСТ 10362-2017", "14"),
    ("diameter", "Рукав резин. напорный 32х43-1,6 с нитян. каркасом", "32"),
    ("diameter", "Рукав III-12-2.0 КВАРТ 50метров в бухте", "12"),
    ("diameter", "Рукав пневматический ВГ-20*1", None),
    ("diameter", "Рукав пескоструйный Extra Blast-19, бухта 40 м CONTRACOR", None),
    ("diameter", "Рукав спаренный кслород/ацетилен 6,3/6,3  40 м", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_SVAR_RUKAVA)
def test_svar_rukava(rules, axis, name, expected):
    got = _v(rules, "svar-rukava", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"


CASES_SVAR_CANGI = [
    ("diameter", "Держатель цанги д/горелки газ. линза 1,6мм (TS 17–18–26) IGF0001-16", "1.6"),
    ("diameter", "Цанга 2,4х50,0мм", "2.4"),
    ("diameter", "Цанга д. 3,2 х 50,0 мм", "3.2"),
    ("diameter", "Цанга 2,4 зажимная KEMPPI", "2.4"),
    ("diameter", "Цанга изоляционная тефлоновая газового сопла, плас", None),
    ("diameter", "Набор цанг 1,6/2,4/3,2 мм", None),
]


@pytest.mark.parametrize(("axis", "name", "expected"), CASES_SVAR_CANGI)
def test_svar_cangi(rules, axis, name, expected):
    got = _v(rules, "svar-cangi", axis, name)
    assert _eq(got, expected), f"{axis}: {got!r} != {expected!r} | {name}"
