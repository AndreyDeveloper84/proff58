"""Разбор разметки статьи.

Разметка — это то, что человек набирает руками, поэтому разбор должен быть
предсказуемым и прощать мелочи: лишние пробелы, отсутствие заголовка в начале,
разное тире в «коротко».
"""

from __future__ import annotations

import pytest

from apps.content.article_markup import parse_body, parse_summary, reading_minutes


def kinds(sections):
    return [[block["kind"] for block in s["blocks"]] for s in sections]


def test_заголовок_открывает_секцию():
    sections = parse_body("## Первый\nТекст\n\n## Второй\nЕщё")

    assert [s["heading"] for s in sections] == ["Первый", "Второй"]
    assert kinds(sections) == [["text"], ["text"]]


def test_текст_до_первого_заголовка_идёт_вступлением():
    sections = parse_body("Вводный абзац.\n\n## Раздел\nТело")

    assert sections[0]["heading"] == ""
    assert sections[0]["blocks"][0]["text"] == "Вводный абзац."


def test_абзацы_разделяются_пустой_строкой():
    sections = parse_body("Первый абзац.\n\nВторой абзац.")

    assert kinds(sections) == [["text", "text"]]


def test_соседние_строки_склеиваются_в_один_абзац():
    sections = parse_body("Начало строки\nпродолжение строки")

    assert sections[0]["blocks"] == [{"kind": "text", "text": "Начало строки продолжение строки"}]


def test_список_собирается_целиком():
    sections = parse_body("- первый\n- второй\n- третий")

    assert sections[0]["blocks"][0] == {
        "kind": "list",
        "items": ["первый", "второй", "третий"],
    }


def test_врезка_отдельным_блоком():
    sections = parse_body("> Важно помнить")

    assert sections[0]["blocks"][0] == {"kind": "note", "text": "Важно помнить"}


def test_таблица_первая_строка_шапка():
    sections = parse_body("| Параметр | SDS-plus |\n| Диаметр | 10 мм |\n| Пазы | 4 |")

    assert sections[0]["blocks"][0] == {
        "kind": "table",
        "head": ["Параметр", "SDS-plus"],
        "rows": [["Диаметр", "10 мм"], ["Пазы", "4"]],
    }


def test_смешанная_секция_сохраняет_порядок_блоков():
    body = "## Раздел\nАбзац.\n\n- пункт\n\n> врезка\n\n| A | B |\n| 1 | 2 |"

    assert kinds(parse_body(body)) == [["text", "list", "note", "table"]]


def test_пустой_текст_даёт_пустой_разбор():
    assert parse_body("") == []
    assert parse_body("   \n\n  ") == []


def test_список_прерывается_абзацем():
    sections = parse_body("- пункт\nОбычный текст")

    assert kinds(sections) == [["list", "text"]]


@pytest.mark.parametrize("prefix", ["- ", "– ", "— ", ""])
def test_коротко_прощает_разное_тире(prefix):
    assert parse_summary(f"{prefix}Первый\n{prefix}Второй") == ["Первый", "Второй"]


def test_коротко_выкидывает_пустые_строки():
    assert parse_summary("Первый\n\n   \nВторой") == ["Первый", "Второй"]


def test_время_чтения_не_меньше_минуты():
    assert reading_minutes("Коротко") == 1


def test_время_чтения_растёт_с_объёмом():
    короткая = reading_minutes("слово " * 100)
    длинная = reading_minutes("слово " * 2000)

    assert длинная > короткая
