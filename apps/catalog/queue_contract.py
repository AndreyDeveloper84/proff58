"""Общий контракт для catalog queue create/export/import.

Хелперы, которые нужны сразу нескольким management-командам. Живут вне
``management/commands/``, чтобы команды не импортировали приватные функции друг
друга.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from apps.catalog.models import Attribute, AttributeOption, Category, Product

TOOL_TYPE_SLUG = "tool_type"


def _category_paths() -> dict[int, str]:
    """id категории → полный путь вида "Родитель / Ребёнок / Лист".

    treebeard кодирует предков префиксами ``path`` кратными ``steplen``.
    Загружаем все категории один раз, чтобы избежать N+1 в ``_product_snapshot``.
    """
    cats = list(Category.objects.all())
    name_by_path = {c.path: c.name for c in cats}
    step = Category.steplen
    paths: dict[int, str] = {}
    for c in cats:
        chain = [name_by_path.get(c.path[: step * i], "") for i in range(1, c.depth + 1)]
        chain = [n for n in chain if n]
        paths[c.id] = " / ".join(chain) if chain else c.name
    return paths


def _product_snapshot(product: Product, category_paths: dict[int, str] | None = None) -> dict:
    """Канонический snapshot товара для export/audit.

    ``category_paths`` передаётся извне, чтобы не делать N+1 запросов к
    предкам категории.
    """
    category_path = ""
    if product.category_id:
        if category_paths is not None:
            category_path = category_paths.get(product.category_id, "")
        else:
            category_path = " / ".join(
                [category.name for category in product.category.get_ancestors()]
                + [product.category.name]
            )
    return {
        "product_id": product.pk,
        "code_1c": product.code_1c or "",
        "article": product.article or "",
        "barcode": product.barcode or "",
        "brand": product.brand or "",
        "name": product.name or "",
        "original_name": product.original_name or "",
        "category_id": product.category_id,
        "category_path": category_path,
        "source_group": product.source_group or "",
    }


def _allowed_tool_type_options() -> list[dict[str, Any]]:
    """Список разрешённых option для tool_type, отсортированный по slug."""
    attr = Attribute.objects.filter(slug=TOOL_TYPE_SLUG).first()
    if attr is None:
        return []
    return [
        {"slug": opt.slug, "value": opt.value}
        for opt in AttributeOption.objects.filter(attribute=attr).order_by("slug")
    ]


def _taxonomy_hash(options: list[dict[str, Any]]) -> str:
    """Стабильный SHA-256 от списка options."""
    payload = json.dumps(options, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
