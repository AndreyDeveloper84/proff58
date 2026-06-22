"""Сигналы каталога: поддержание Product.attrs_cache и кэша дерева в актуальном виде.

Тонкие обработчики — только вызывают пересборку кэша. Пересборка attrs_cache
планируется через transaction.on_commit, чтобы не обновлять кэш по откатившейся
транзакции. Инвалидация дерева каталога — это безопасное удаление ключа, его
делаем сразу (если транзакция откатится, следующее чтение пересоберёт дерево из
зафиксированных данных).
"""

from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Category, Product, ProductAttributeValue
from .services import invalidate_category_tree_cache, rebuild_attrs_cache


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


# Счётчики дерева каталога зависят от товаров (категория, остаток) и от самих
# категорий (состав, on_site, is_active, порядок) — сбрасываем кэш при их изменении.
@receiver(post_save, sender=Product)
@receiver(post_delete, sender=Product)
@receiver(post_save, sender=Category)
@receiver(post_delete, sender=Category)
def invalidate_category_tree(sender, **kwargs) -> None:
    invalidate_category_tree_cache()
