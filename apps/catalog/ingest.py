"""Хелперы чтения входных файлов каталога (``data/``).

Формат файлов описан в задании бутстрапа:

* ``group_mapping.json`` — массив ``{external_id, group_1c, site_path[], on_site}``;
* ``catalog_fixed.json`` — дерево узлов 1С: группа ``ProductGroup=="1"`` (с
  ``children``), товар ``ProductGroup=="0"`` с полями
  ``external_id, sku, name, source_group, unit, is_active, stock``.

Товар привязывается к категории по ``external_id`` его РОДИТЕЛЬСКОЙ группы 1С
(а не по ``source_group`` — имя не уникально).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from django.conf import settings

GROUP_NODE = "1"
PRODUCT_NODE = "0"


def data_dir() -> Path:
    """Каталог с входными файлами (по умолчанию ``<BASE_DIR>/data``)."""
    return Path(settings.BASE_DIR) / "data"


def load_json(name: str, base: str | Path | None = None) -> object:
    path = (Path(base) if base else data_dir()) / name
    return json.loads(path.read_text(encoding="utf-8"))


def load_group_mapping(base: str | Path | None = None) -> list[dict]:
    return load_json("group_mapping.json", base)  # type: ignore[return-value]


def group_index(mapping: list[dict]) -> dict[str, dict]:
    """Индекс ``external_id`` группы 1С → запись маппинга."""
    return {str(row["external_id"]): row for row in mapping}


def iter_products(tree: list[dict]) -> Iterator[tuple[dict, str | None]]:
    """Обойти дерево 1С, отдавая ``(узел_товара, external_id_родительской_группы)``."""

    def _walk(node: dict, parent_gid: str | None) -> Iterator[tuple[dict, str | None]]:
        if str(node.get("ProductGroup")) == GROUP_NODE:
            gid = str(node.get("external_id")) if node.get("external_id") else None
            for child in node.get("children") or []:
                yield from _walk(child, gid)
        else:
            yield node, parent_gid

    for root in tree:
        yield from _walk(root, None)


def stock_value(node: dict) -> float:
    """Остаток товара как число (в 1С приходит строкой)."""
    try:
        return float(node.get("stock") or 0)
    except (TypeError, ValueError):
        return 0.0
