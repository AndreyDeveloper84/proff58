"""Пагинация API с потолком размера страницы (DRF-2733).

У ``LimitOffsetPagination`` из DRF потолка нет (``max_limit = None``): публичный
``GET /api/catalog/products/?limit=100000`` материализовал весь каталог с prefetch
фото и характеристик в памяти одного воркера — одного запроса хватало, чтобы его
положить. Любой список в API отдаётся через этот класс; запрос сверх потолка
молча усекается до него.
"""

from __future__ import annotations

from rest_framework.pagination import LimitOffsetPagination

#: Сколько записей отдаём за один запрос максимум. Витрина просит до 48 товаров
#: на страницу, 100 заказов в истории и до ``catalog.filters.MAX_IDS_FILTER``
#: (200) товаров по списку id — потолок не меньше этого (сверяет тест каталога).
MAX_PAGE_LIMIT = 200


class BoundedLimitOffsetPagination(LimitOffsetPagination):
    """``?limit=&offset=`` как в DRF, но ``limit`` не больше ``MAX_PAGE_LIMIT``."""

    max_limit = MAX_PAGE_LIMIT
