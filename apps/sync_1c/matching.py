"""Поиск товара каталога по идентификаторам из 1С.

Правила связи (инвариант проекта):
  * сначала по `code_1c` (уникальный, главный ключ);
  * затем по `article` (НЕ уникальный — запасной ключ);
  * если по артикулу подходит несколько товаров — это неоднозначность
    (conflict): связывать молча нельзя, строка уходит в ручной разбор.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    """Разрешить товар для импорта/обновления с детекцией конфликтов."""
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
