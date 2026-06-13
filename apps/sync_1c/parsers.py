"""Парсеры выгрузок 1С в единый список словарей-элементов.

Точная структура выгрузки 1С 7.7 пока неизвестна, поэтому поддерживаем
универсальные форматы (JSON, CSV). Когда появится реальный формат (DBF
и т.п.), добавляем сюда ещё один загрузчик — остальной конвейер не меняется.

Каждый элемент — dict с ключами, которые понимает importer
(external_id/code_1c, sku/article, name, brand, price, stock, ...).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


def load_items(path: str | Path) -> list[dict]:
    """Загрузить элементы из файла по расширению."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _load_json(path)
    if suffix == ".csv":
        return _load_csv(path)
    raise ValueError(f"Неподдерживаемый формат выгрузки: {suffix or '<нет расширения>'}")


def _load_json(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        raise ValueError("JSON должен быть списком элементов или объектом с ключом items.")
    return data


def _load_csv(path: Path) -> list[dict]:
    # 1С часто отдаёт CSV в windows-1251 с разделителем ';'.
    with path.open(encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(fh, delimiter=delimiter)
        return [dict(row) for row in reader]
