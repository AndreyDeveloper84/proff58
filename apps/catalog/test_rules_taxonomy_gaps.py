"""Регресс на добор словарей под таксономические пробелы (Пожарное/Знаки/Вышки/адаптеры).

Чистые функции classify/load_rules — БД не нужна. Проверяет, что новые правила ловят
целевые имена и не дают очевидных ложных срабатываний.
"""

from __future__ import annotations

import pytest

from apps.catalog.semantic import classify, load_rules

CASES = [
    # siz — новые узлы
    ("data/product_type_rules-siz.json", "Огнетушитель ОП-4 порошковый", "Пожарное оборудование"),
    ("data/product_type_rules-siz.json", "Пожарный рукав РПК-50", "Пожарное оборудование"),
    ("data/product_type_rules-siz.json", "Знак безопасности «Выход» F09", "Знаки безопасности"),
    ("data/product_type_rules-siz.json", "Перчатки ХБ с ПВХ", "Перчатки и рукавицы"),  # не сломали
    # stroitelnyy — новый узел
    (
        "data/product_type_rules-stroitelnyy.json",
        "Стремянка алюминиевая 5 ступеней",
        "Вышки, леса, лестницы и стремянки",
    ),
    (
        "data/product_type_rules-stroitelnyy.json",
        "Лестница приставная 3х9",
        "Вышки, леса, лестницы и стремянки",
    ),
    (
        "data/product_type_rules-stroitelnyy.json",
        "Валик малярный 250мм",
        "Малярный инструмент",
    ),  # не сломали
    # osnastka — адаптеры/втулки в Держатели
    (
        "data/product_type_rules.json",
        "Адаптер с SDS-max на SDS+ ЗУБР",
        "Держатели, адаптеры и патроны",
    ),
    (
        "data/product_type_rules.json",
        "Втулка переходная 5/3 СТАЛЬ 40Х ГОСТ 13598-85",
        "Держатели, адаптеры и патроны",
    ),
]


@pytest.mark.parametrize("path,name,expected", CASES)
def test_new_rules_classify(path, name, expected):
    _doc, compiled = load_rules(path)
    hit = classify(name, compiled)
    assert hit is not None, f"не классифицировано: {name}"
    assert hit[0] == expected


def test_akb_adapter_not_holder():
    # «Адаптер для АКБ» — это запчасти, а НЕ оснастка-Держатели (адаптер.*sds не матчит).
    _doc, compiled = load_rules("data/product_type_rules.json")
    hit = classify("Адаптер для АКБ LMS 20V Max", compiled)
    assert hit is None or hit[0] != "Держатели, адаптеры и патроны"
