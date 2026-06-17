"""Сигналы каталога: поддержание Product.attrs_cache в актуальном виде.

Тонкие обработчики — только вызывают пересборку кэша. Пересборка планируется
через transaction.on_commit, чтобы не обновлять кэш по откатившейся транзакции.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Product, ProductAttributeValue
from .services import rebuild_attrs_cache


def _schedule_rebuild(product: Product | None) -> None:
    if product is not None:
        transaction.on_commit(lambda: rebuild_attrs_cache(product))


@receiver(post_save, sender=ProductAttributeValue)
def rebuild_cache_on_save(sender, instance: ProductAttributeValue, **kwargs) -> None:
    _schedule_rebuild(instance.product)


@receiver(post_delete, sender=ProductAttributeValue)
def rebuild_cache_on_delete(sender, instance: ProductAttributeValue, **kwargs) -> None:
    try:
        product = instance.product
    except Product.DoesNotExist:
        return  # товар удалён каскадом — пересобирать нечего
    _schedule_rebuild(product)
