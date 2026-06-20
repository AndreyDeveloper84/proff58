"""Поиск товара каталога по идентификаторам из 1С.

Правила связи (инвариант проекта):
  * сначала по `code_1c` (уникальный, главный ключ);
  * затем по `article` (НЕ уникальный — запасной ключ);
  * если по артикулу подходит несколько товаров — это неоднозначность
    (conflict): связывать молча нельзя, строка уходит в ручной разбор.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from apps.catalog.models import Product

from .normalizers import Item


class MatchStatus(StrEnum):
    MATCHED = "matched"  # найден ровно один товар
    NEW = "new"  # товара нет
    CONFLICT = "conflict"  # неоднозначный артикул


@dataclass
class MatchResult:
    status: MatchStatus
    product: Product | None = None
    reason: str = ""


def find_product(item: Item) -> Product | None:
    """Найти товар по коду 1С (приоритет), затем по артикулу (первый). Без conflict-логики."""
    if item.code_1c:
        product = Product.objects.filter(code_1c=item.code_1c).first()
        if product:
            return product
    if item.article:
        return Product.objects.filter(article=item.article).first()
    return None


def resolve_for_import(item: Item) -> MatchResult:
    """Разрешить товар для импорта/обновления с детекцией конфликтов (одиночный путь)."""
    if item.code_1c:
        product = Product.objects.filter(code_1c=item.code_1c).first()
        if product:
            return MatchResult(MatchStatus.MATCHED, product)
    if item.article:
        qs = Product.objects.filter(article=item.article)
        count = qs.count()
        if count > 1:
            return MatchResult(
                MatchStatus.CONFLICT,
                None,
                f"Неоднозначный артикул «{item.article}»: подходит товаров — {count}.",
            )
        if count == 1:
            return MatchResult(MatchStatus.MATCHED, qs.first())
    return MatchResult(MatchStatus.NEW)


# --- Пакетный matching: карты существующих товаров (без per-row запросов, #125) ---


@dataclass
class MatchMaps:
    """Карты существующих товаров для пакетного matching.

    Строятся 1–2 запросами на батч (вместо `filter().first()`/`.count()` на строку).
    Семантика разрешения — как у `resolve_for_import`.
    """

    by_code: dict[str, Product] = field(default_factory=dict)
    by_article: dict[str, list[Product]] = field(default_factory=dict)

    def register(self, product: Product) -> None:
        """Учесть только что созданный товар, чтобы дубль в том же батче нашёлся
        (как при свежем запросе к БД в построчном режиме)."""
        if product.code_1c:
            self.by_code[product.code_1c] = product
        if product.article:
            self.by_article.setdefault(product.article, []).append(product)


def build_match_maps(items: Iterable[Item]) -> MatchMaps:
    """Построить `by_code`/`by_article` для батча — 1–2 запроса (не на строку)."""
    items = list(items)
    codes = {it.code_1c for it in items if it.code_1c}
    articles = {it.article for it in items if it.article}
    maps = MatchMaps()
    if codes:
        maps.by_code = {p.code_1c: p for p in Product.objects.filter(code_1c__in=codes)}
    if articles:
        for p in Product.objects.filter(article__in=articles):
            maps.by_article.setdefault(p.article, []).append(p)
    return maps


def resolve_in_memory(item: Item, maps: MatchMaps) -> MatchResult:
    """Как `resolve_for_import`, но по предзагруженным картам — без запросов."""
    if item.code_1c:
        product = maps.by_code.get(item.code_1c)
        if product is not None:
            return MatchResult(MatchStatus.MATCHED, product)
    if item.article:
        products = maps.by_article.get(item.article, [])
        if len(products) > 1:
            return MatchResult(
                MatchStatus.CONFLICT,
                None,
                f"Неоднозначный артикул «{item.article}»: подходит товаров — {len(products)}.",
            )
        if len(products) == 1:
            return MatchResult(MatchStatus.MATCHED, products[0])
    return MatchResult(MatchStatus.NEW)
