"""Применение сопоставления «группа 1С → категория сайта».

Расставляет товары группы (по ``Product.source_group == group.name``) в
``group.mapped_category``. Используется и из админки (действие), и из команды
``catalog_apply_group_mapping``. Помечает товары ``category_is_manual=True`` —
сопоставление куратора авторитетно (обмен 1С его не перетирает).
"""

from __future__ import annotations

from django.db import transaction

from apps.catalog.category_tree import invalidate_category_tree_cache
from apps.catalog.facets import invalidate_facets_cache
from apps.catalog.models import OneCGroup, Product
from apps.core.events import EventSource, product_updated


def apply_group_mapping(group: OneCGroup, *, only_unmanual: bool = True) -> int:
    """Перенести товары группы в ``group.mapped_category``. Вернуть число перемещённых.

    ``only_unmanual`` — не трогать товары с ручной категорией (по умолчанию True).
    Возвращает 0, если у группы нет ``mapped_category`` или нет подходящих товаров.
    """
    if not group.mapped_category_id:
        return 0
    qs = Product.objects.filter(source_group=group.name)
    if only_unmanual:
        qs = qs.filter(category_is_manual=False)
    ids = list(qs.values_list("id", flat=True))
    if not ids:
        return 0

    Product.objects.filter(id__in=ids).update(
        category_id=group.mapped_category_id, category_is_manual=True
    )

    def _post(pids=tuple(ids)):
        for pid in pids:
            product_updated.send(
                sender=Product,
                product_id=pid,
                source=EventSource.SYSTEM,
                changed_fields=["category"],
            )
        invalidate_facets_cache()
        invalidate_category_tree_cache()

    transaction.on_commit(_post)
    return len(ids)
