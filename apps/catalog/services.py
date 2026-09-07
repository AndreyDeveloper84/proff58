"""Фасад каталога над специализированными модулями.

Исторически здесь жили attrs_cache, фасеты, дерево категорий и product-queries.
После рефакторинга код разнесён по модулям, а этот фасад сохраняет публичный
контракт ``apps.catalog.services`` (ADR-0004). Новый код импортирует напрямую
из специализированных модулей:

- ``read_models`` — денормализация EAV в ``attrs_cache``;
- ``facets`` — фасетные фильтры (#25);
- ``category_tree`` — дерево категорий со счётчиками для витрины;
- ``queries`` — товары поддерева, счётчики, range-/tool_type-фасеты.
"""

from __future__ import annotations

from .category_tree import get_category_tree, invalidate_category_tree_cache
from .facets import (
    FacetError,
    apply_product_attr_filters,
    build_facets,
    build_facets_cached,
    build_search_facets,
    invalidate_facets_cache,
)
from .models import CompatibilityKind, ProductCompatibility
from .queries import (
    CompatibilityItem,
    accessories_of,
    analogs_of,
    category_counts,
    compatibility_sections,
    compatible_of,
    cross_sell_of,
    fits_of,
    products_in,
    range_filter_attributes,
    tool_type_facets,
)
from .read_models import attr_value_to_json, rebuild_attrs_cache

__all__ = [
    "FacetError",
    "attr_value_to_json",
    "rebuild_attrs_cache",
    "build_facets",
    "build_facets_cached",
    "build_search_facets",
    "invalidate_facets_cache",
    "apply_product_attr_filters",
    "get_category_tree",
    "invalidate_category_tree_cache",
    "products_in",
    "range_filter_attributes",
    "category_counts",
    "tool_type_facets",
    # Совместимость товаров (#79)
    "CompatibilityItem",
    "CompatibilityKind",
    "ProductCompatibility",
    "accessories_of",
    "fits_of",
    "compatible_of",
    "cross_sell_of",
    "analogs_of",
    "compatibility_sections",
]
