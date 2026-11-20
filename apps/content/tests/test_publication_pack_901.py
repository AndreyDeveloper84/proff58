"""Regression tests for the CMS article markup used by publication pack #01."""

from apps.content.article_markup import parse_body, parse_summary


def test_article_tables_lists_and_notes():
    sections = parse_body("""Intro.

## Выбор
| Задача | Инструмент |
| Дом | SDS-plus |

- Первый пункт
- Второй пункт

> Важно проверить паспорт.
""")
    assert sections[0]["blocks"][0] == {"kind": "text", "text": "Intro."}
    assert sections[1]["heading"] == "Выбор"
    assert [block["kind"] for block in sections[1]["blocks"]] == ["table", "list", "note"]
    assert sections[1]["blocks"][0]["rows"] == [["Дом", "SDS-plus"]]

def test_markdown_link_remains_plain_text_in_api():
    # Inline link rendering is handled by the Next.js frontend; the backend
    # deliberately does not emit untrusted HTML.
    sections = parse_body("[Каталог](/catalog/elektroinstrument)")
    assert sections[0]["blocks"][0]["text"] == "[Каталог](/catalog/elektroinstrument)"

def test_summary_lines():
    assert parse_summary("Первая мысль\nВторая мысль") == ["Первая мысль", "Вторая мысль"]
