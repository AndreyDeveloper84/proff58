"""Рабочие очереди каталога — единственное определение «что требует внимания».

Одни и те же выборки нужны в двух местах: фильтрам списка товаров в админке и
счётчикам стартового экрана. Если считать их по отдельности, числа разъедутся
(«написано 12, открыл — 8»), и человек перестанет верить дашборду. Поэтому
условие живёт здесь, а фильтры и дашборд только вызывают его.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from .models import Product, ProductStatus


def _base(queryset: QuerySet | None = None) -> QuerySet:
    return Product.objects.all() if queryset is None else queryset


def needs_attention(queryset: QuerySet | None = None) -> QuerySet:
    """Не опубликован И (без категории ИЛИ импортирован/требует проверки).

    Нехватку обязательных характеристик на уровне SQL не ловим — она видна в
    колонке «Причина в очереди» (проверка построчная и для выборки тяжёлая).
    """
    return (
        _base(queryset)
        .exclude(status=ProductStatus.PUBLISHED)
        .filter(
            Q(category__isnull=True)
            | Q(status__in=[ProductStatus.IMPORTED, ProductStatus.NEEDS_REVIEW])
        )
    )


def without_category(queryset: QuerySet | None = None) -> QuerySet:
    return _base(queryset).filter(category__isnull=True)


def without_image(queryset: QuerySet | None = None) -> QuerySet:
    return _base(queryset).filter(images__isnull=True)


def without_description(queryset: QuerySet | None = None) -> QuerySet:
    return _base(queryset).filter(description="", short_description="")


def without_price(queryset: QuerySet | None = None) -> QuerySet:
    return _base(queryset).filter(Q(price__isnull=True) | Q(price=0))
