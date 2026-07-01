"""Заливка остатков из выгрузки 1С (`Catalog_stocks.json`) + опциональная публикация.

Выгрузка 1С — вложенное дерево (группа ``ProductGroup=="1"`` с ``children``,
товар ``ProductGroup=="0"`` с ``external_id``/``stock``), часто в windows-1251 и с
дефектами JSON (пропущена запятая после ``"name"`` перед ``"barcode"``; висячие
запятые перед ``}``/``]``; управляющие символы в строках). Команда чинит это
детерминированно, обходит дерево (`ingest.iter_products`) и применяет остатки
через `use_cases.update_stocks_bulk` (матчинг по ``code_1c`` чанками + `bulk_update`
— низкая память на десятках тысяч строк; пишет только остаток + `SyncLog`).

С ``--publish-in-stock`` товары с остатком > 0 и видимой категорией
(``on_site=True``, активна) публикуются — зеркало admin-экшена ``action_publish``
(`status=PUBLISHED, is_active=True`), bulk `.update()` + ручная инвалидация кэша
дерева (на bulk сигналы не срабатывают).
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.catalog.category_tree import invalidate_category_tree_cache
from apps.catalog.facets import invalidate_facets_cache
from apps.catalog.ingest import iter_products
from apps.catalog.models import Product, ProductStatus
from apps.sync_1c import use_cases

# Дефекты выгрузки 1С (см. docstring модуля).
_MISSING_COMMA = re.compile(r'"\s*\n(\s*)"barcode"\s*:')
_TRAILING_COMMA = re.compile(r",(\s*\n\s*[}\]])")

_IN_CHUNK = 5000  # размер чанка для code_1c__in (не раздувать SQL IN)


def _repair(raw: str) -> str:
    """Починить известные дефекты JSON-выгрузки 1С."""
    raw = _MISSING_COMMA.sub(r'",\n\1"barcode":', raw)
    raw = _TRAILING_COMMA.sub(r"\1", raw)
    return raw


def parse_stock_items(raw: str) -> list[dict]:
    """Сырой текст выгрузки → список ``{"code_1c", "stock"}`` по товарам-листьям."""
    tree = json.loads(_repair(raw), strict=False)  # strict=False: control-символы в строках
    if isinstance(tree, dict):
        tree = tree.get("children") or [tree]
    items: list[dict] = []
    for node, _gid in iter_products(tree):
        ext = (node.get("external_id") or "").strip()
        if ext and node.get("stock") is not None:
            items.append({"code_1c": ext, "stock": node["stock"]})
    return items


def _is_positive(stock) -> bool:
    try:
        return Decimal(str(stock or 0)) > 0
    except (InvalidOperation, ValueError):
        return False


def _publish_in_stock(codes: list[str]) -> int:
    """Опубликовать товары с остатком и видимой категорией (зеркало action_publish)."""
    published = 0
    for start in range(0, len(codes), _IN_CHUNK):
        chunk = codes[start : start + _IN_CHUNK]
        qs = Product.objects.filter(
            code_1c__in=chunk,
            category__on_site=True,
            category__is_active=True,
        ).exclude(status=ProductStatus.PUBLISHED, is_active=True)
        published += qs.update(status=ProductStatus.PUBLISHED, is_active=True)
    if published:
        invalidate_category_tree_cache()
        invalidate_facets_cache()
    return published


class Command(BaseCommand):
    help = "Залить остатки из выгрузки 1С (JSON) и опционально опубликовать товары в наличии."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Путь к файлу выгрузки остатков (JSON).")
        parser.add_argument(
            "--encoding", default="cp1251", help="Кодировка файла (по умолч. cp1251)."
        )
        parser.add_argument(
            "--publish-in-stock",
            action="store_true",
            help="Опубликовать товары с остатком > 0 и видимой категорией.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только разобрать файл и показать счётчики, без записи в БД.",
        )

    def handle(self, *args, **opts):
        raw = Path(opts["path"]).read_text(encoding=opts["encoding"])
        items = parse_stock_items(raw)
        in_stock = [it["code_1c"] for it in items if _is_positive(it["stock"])]

        if opts["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY-RUN: товаров {len(items)}, с остатком {len(in_stock)} "
                    f"(публикация затронула бы их при наличии видимой категории). Запись не выполнена."
                )
            )
            return

        name = Path(opts["path"]).name
        # bulk-путь: чанками + bulk_update (низкая память, без построчных транзакций).
        _log, result = use_cases.update_stocks_bulk(
            items, source_file=f"cmd:apply_stocks_1c:{name}"
        )

        published = 0
        if opts["publish_in_stock"] and in_stock:
            published = _publish_in_stock(in_stock)

        self.stdout.write(
            self.style.SUCCESS(
                f"Остатки: товаров {len(items)}, обновлено {result.updated}, "
                f"пропущено {result.skipped}, ошибок {result.errors}. "
                f"Опубликовано {published}."
            )
        )
