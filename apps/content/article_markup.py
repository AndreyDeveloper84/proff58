"""Разметка статьи: простой текст → структура, которую рендерит витрина.

Почему не JSON в админке: структура статьи на сайте — секции с блоками четырёх
типов, и заставлять человека писать её руками в JSON значит не дать ему писать
статьи вовсе. Почему не WYSIWYG: это отдельный редактор в админке на неделю
работы, а разметка ниже осваивается за минуту.

Синтаксис (всё остальное — обычный абзац):

    ## Заголовок раздела
    Обычный абзац. Пустая строка разделяет абзацы.

    - пункт списка
    - ещё пункт

    > Важное замечание врезкой

    | Параметр | SDS-plus | SDS-max |
    | Диаметр  | 10 мм    | 18 мм   |

Первая строка таблицы — шапка. Текст до первого «##» попадает в секцию без
заголовка: витрина отрисует его вводными абзацами.
"""

from __future__ import annotations

import re

HEADING = "## "
LIST_ITEM = "- "
NOTE = "> "
TABLE_SEP = "|"

_WORDS_PER_MINUTE = 900  # знаков в минуту при спокойном чтении


def _flush_paragraph(lines: list[str], blocks: list[dict]) -> None:
    text = " ".join(part.strip() for part in lines if part.strip())
    if text:
        blocks.append({"kind": "text", "text": text})
    lines.clear()


def _parse_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip(TABLE_SEP).split(TABLE_SEP)]


def parse_body(body: str) -> list[dict]:
    """Разобрать текст статьи в секции с блоками.

    Возвращает ``[{"heading": str, "blocks": [...]}]`` — ровно то, что ждёт
    витрина (frontend/lib/articles.ts, тип ArticleSection).
    """
    sections: list[dict] = []
    current = {"heading": "", "blocks": []}
    paragraph: list[str] = []
    list_items: list[str] = []
    table_rows: list[list[str]] = []

    def flush_list() -> None:
        if list_items:
            current["blocks"].append({"kind": "list", "items": list(list_items)})
            list_items.clear()

    def flush_table() -> None:
        if table_rows:
            head, *rows = table_rows
            current["blocks"].append({"kind": "table", "head": head, "rows": rows})
            table_rows.clear()

    def flush_all() -> None:
        _flush_paragraph(paragraph, current["blocks"])
        flush_list()
        flush_table()

    for raw in (body or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith(HEADING):
            flush_all()
            if current["blocks"] or current["heading"]:
                sections.append(current)
            current = {"heading": stripped[len(HEADING) :].strip(), "blocks": []}
            continue

        if not stripped:
            flush_all()
            continue

        if stripped.startswith(LIST_ITEM):
            _flush_paragraph(paragraph, current["blocks"])
            flush_table()
            list_items.append(stripped[len(LIST_ITEM) :].strip())
            continue

        if stripped.startswith(NOTE):
            flush_all()
            current["blocks"].append({"kind": "note", "text": stripped[len(NOTE) :].strip()})
            continue

        if stripped.startswith(TABLE_SEP):
            _flush_paragraph(paragraph, current["blocks"])
            flush_list()
            table_rows.append(_parse_table_row(stripped))
            continue

        flush_list()
        flush_table()
        paragraph.append(stripped)

    flush_all()
    if current["blocks"] or current["heading"]:
        sections.append(current)
    return sections


def parse_summary(summary: str) -> list[str]:
    """«Коротко» — по пункту на строку, пустые выкидываем."""
    return [line.strip(" -–—\t") for line in (summary or "").splitlines() if line.strip(" -–—\t")]


def reading_minutes(body: str) -> int:
    """Оценка времени чтения. Не меньше минуты — «0 мин» выглядит поломкой."""
    plain = re.sub(r"[#>|-]", " ", body or "")
    return max(1, round(len(plain) / _WORDS_PER_MINUTE))
