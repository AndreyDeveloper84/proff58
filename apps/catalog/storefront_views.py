"""Тестовая витрина каталога (Django-templates).

Цель — глазами проверить данные после бутстрапа, не дизайн. Показывает
импортированные товары (а не только опубликованные): это инструмент контроля
загрузки и работы правил tool_type.
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render

from .models import Category, EnrichmentLog, EnrichmentResult
from .services import (
    FacetError,
    category_counts,
    get_category_tree,
    products_in,
    range_filter_attributes,
    tool_type_facets,
)

PAGE_SIZE = 24


def _parse_float(raw, *, field: str):
    """Пустое → None; непустое нечисло → FacetError (→ HTTP 400, не молчаливый игнор)."""
    if raw is None or raw == "":
        return None
    try:
        return float(raw.replace(",", "."))
    except (ValueError, AttributeError) as exc:
        raise FacetError(f"Неверное значение «{field}»: {raw!r}") from exc


def _parse_attr_ranges(request, category) -> dict:
    """GET ``<slug>_min`` / ``<slug>_max`` → ``{slug: (min, max)}`` (#96 range-фильтры).

    Берём только диапазонные характеристики-фильтры категории; пустые границы
    пропускаем, непустые нечисловые → FacetError (HTTP 400); атрибут попадает в
    фильтр, только если задана хоть одна граница.
    """
    ranges: dict = {}
    for attr in range_filter_attributes(category):
        slug = attr["slug"]
        lo = _parse_float(request.GET.get(f"{slug}_min"), field=f"{slug}_min")
        hi = _parse_float(request.GET.get(f"{slug}_max"), field=f"{slug}_max")
        if lo is not None or hi is not None:
            ranges[slug] = (lo, hi)
    return ranges


def catalog_index(request):
    """`/catalog/` — дерево категорий верхнего уровня со счётчиками."""
    return render(
        request,
        "catalog/index.html",
        {"categories": get_category_tree(on_site_only=True)},
    )


def category_detail(request, slug_path):
    """`/catalog/<path:slug_path>/` — категория: плитки tool_type + список товаров."""
    slug = slug_path.strip("/").split("/")[-1]
    category = get_object_or_404(Category, slug=slug)

    tool_type = request.GET.get("tool_type") or None
    in_stock = request.GET.get("in_stock") == "1"
    try:
        attr_ranges = _parse_attr_ranges(request, category)
    except FacetError as exc:
        return HttpResponseBadRequest(str(exc))

    qs = (
        products_in(category, tool_type=tool_type, in_stock=in_stock, attr_ranges=attr_ranges)
        .select_related("category")
        .order_by("name")
    )
    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    # Бейдж «сменить категорию» — по логам обогащения для товаров текущей страницы.
    codes = [p.code_1c for p in page.object_list if p.code_1c]
    recat_codes = set(
        EnrichmentLog.objects.filter(
            product_external_id__in=codes, result=EnrichmentResult.RECATEGORIZE
        ).values_list("product_external_id", flat=True)
    )

    rows = []
    for p in page.object_list:
        tt = (p.attrs_cache or {}).get("tool_type")
        is_recat = p.code_1c in recat_codes
        rows.append(
            {
                "product": p,
                "tool_type": tt,
                # recategorize — отдельная корзина, не смешиваем с модерацией.
                "needs_moderation": not tt and not is_recat,
                "recategorize": is_recat,
            }
        )

    ancestors = list(category.get_ancestors())
    return render(
        request,
        "catalog/category.html",
        {
            "category": category,
            "breadcrumbs": ancestors,
            "counts": category_counts(category),
            "facets": tool_type_facets(category),
            "rows": rows,
            "page": page,
            "active_tool_type": tool_type,
            "in_stock": in_stock,
        },
    )
