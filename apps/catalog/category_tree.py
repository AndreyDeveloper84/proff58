"""Дерево категорий каталога для витрины со счётчиками товаров.

Контракт каталога для витрины (ADR-0004: только через services) — другие модули
и шаблоны не лезут в модели напрямую. Результат кэшируется, инвалидация — по
сигналам изменения товаров/категорий (apps/catalog/signals.py).
"""

from __future__ import annotations

from django.core.cache import cache as cache_store
from django.db.models import Count, Q
from django.db.models.functions import Substr

from .models import Category, Product

CATEGORY_TREE_CACHE_KEY = "catalog:category_tree"
CATEGORY_TREE_CACHE_TTL = 300  # сек; плюс инвалидация по сигналам изменения данных


def invalidate_category_tree_cache() -> None:
    """Сбросить кэш дерева каталога. Зовётся из сигналов при изменении товаров/категорий."""
    cache_store.delete_many([f"{CATEGORY_TREE_CACHE_KEY}:0", f"{CATEGORY_TREE_CACHE_KEY}:1"])


def get_category_tree(*, on_site_only: bool = True):
    """Категории верхнего уровня сайта со счётчиками товаров и «в наличии».

    Возвращает список словарей для витрины ``/catalog/``: имя, slug и счётчики
    по всему поддереву категории. Это контракт каталога — другие модули и шаблоны
    не лезут в модели напрямую (ADR-0004).

    Счётчики считаются ОДНИМ агрегатом с GROUP BY по корню дерева (а не 2×N
    запросами на каждую корневую категорию), результат кэшируется. Инвалидация —
    по сигналам изменения товаров/категорий (apps/catalog/signals.py).
    """
    cache_key = f"{CATEGORY_TREE_CACHE_KEY}:{int(on_site_only)}"
    cached = cache_store.get(cache_key)
    if cached is not None:
        return cached

    qs = Category.objects.filter(depth=1, is_active=True)
    if on_site_only:
        qs = qs.filter(on_site=True)
    tops = list(qs.order_by("sort_order", "name"))

    # Один проход по товарам: группируем по корневой ветке дерева. У treebeard
    # (MP_Node) путь любого потомка начинается с пути его корня длиной ``steplen``,
    # поэтому первые ``steplen`` символов ``path`` однозначно задают корневую
    # категорию. Так считаем счётчики всех поддеревьев одним запросом.
    steplen = Category.steplen
    by_root: dict[str, dict] = {}
    if tops:
        agg = (
            Product.objects.filter(category__isnull=False)
            .annotate(root=Substr("category__path", 1, steplen))
            .values("root")
            .annotate(
                total=Count("id"),
                in_stock=Count("id", filter=Q(stock_quantity__gt=0)),
            )
        )
        by_root = {row["root"]: row for row in agg}

    tree = []
    for cat in tops:
        row = by_root.get(cat.path[:steplen], {})
        tree.append(
            {
                "id": cat.id,
                "name": cat.name,
                "slug": cat.slug,
                "total": row.get("total", 0),
                "in_stock": row.get("in_stock", 0),
            }
        )

    cache_store.set(cache_key, tree, CATEGORY_TREE_CACHE_TTL)
    return tree
