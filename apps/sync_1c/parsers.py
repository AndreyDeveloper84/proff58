"""Парсеры файловых выгрузок 1С в единый список словарей-строк.

Легаси-путь (`manage.py import_1c`) для разовой загрузки из файла. Штатный
обмен идёт по HTTP-контракту `docs/1c-api-spec.md` (1С сама шлёт JSON в
`/api/1c/`, см. `api/`), и файловый формат там не участвует. Поддерживаем
универсальные JSON/CSV; маппинг названий колонок — в `normalizers.COLUMN_ALIASES`,
парсер отвечает только за «файл → list[dict]» (формат + кодировка).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

# Кодировки для авто-определения по порядку: 1С 7.7 часто отдаёт windows-1251.
_CSV_ENCODINGS = ("utf-8-sig", "cp1251")


def load_items(path: str | Path) -> list[dict]:
    """Загрузить строки из файла по расширению."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _load_json(path)
    if suffix == ".csv":
        return _load_csv(path)
    raise ValueError(f"Неподдерживаемый формат выгрузки: {suffix or '<нет расширения>'}")


def _load_json(path: Path) -> list[dict]:
    import json

    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        raise ValueError("JSON должен быть списком элементов или объектом с ключом items.")
    return data


def _decode(raw: bytes, encoding: str = "auto") -> str:
    if encoding != "auto":
        return raw.decode(encoding)
    for enc in _CSV_ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    # Последний шанс — utf-8 с заменой битых байтов, чтобы не падать на одной строке.
    return raw.decode("utf-8", errors="replace")


def _load_csv(path: Path, encoding: str = "auto") -> list[dict]:
    text = _decode(path.read_bytes(), encoding)
    # 1С часто отдаёт CSV с разделителем ';'.
    head = text[:4096]
    delimiter = ";" if head.count(";") >= head.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    return [dict(row) for row in reader]
