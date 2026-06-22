"""Тесты транслитерации значений характеристик в slug (P2, slug-URL)."""

import pytest

from apps.catalog.translit import slugify_value, translit


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Коронки", "koronki"),
        ("Сверла по металлу", "sverla-po-metallu"),
        ("Ёршики", "ershiki"),
        ("Шлифовальные круги", "shlifovalnye-krugi"),
        ("SDS-Plus", "sds-plus"),
        ("HSS-Co 8%", "hss-co-8"),
        ("Насадки/адаптеры", "nasadki-adaptery"),
        ("Бур SDS 12мм", "bur-sds-12mm"),  # смешанные кириллица+латиница+цифры
        ("!!!", ""),  # после slugify пусто → вызывающий код подставит base "option"
        ("", ""),
    ],
)
def test_slugify_value(value, expected):
    assert slugify_value(value) == expected


def test_translit_keeps_latin_and_digits():
    assert translit("ABC-123") == "ABC-123"


def test_translit_cyrillic_basic():
    assert translit("Жук") == "Zhuk"
