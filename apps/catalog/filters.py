"""Фильтрация товаров каталога — слой queryset-хелперов.

Намеренно НЕ зависит от `api/` (HTTP-слой): сюда вынесены `ProductFilter` и общая
выборка, чтобы и DRF-вьюхи, и сервисы (фасеты #25) опирались на один источник.
"""

from __future__ import annotations

import operator
from functools import reduce

import django_filters
from django.db.models import Q

from .models import Category, Product, ProductStatus


def visible_products():
    """Товары, видимые на витрине (is_visible нельзя использовать в queryset)."""
    return Product.objects.filter(is_active=True, status=ProductStatus.PUBLISHED)


class ProductFilter(django_filters.FilterSet):
    # Категория + все потомки: зайдя в «Электроинструмент», видим товары из «Дрелей».
    category = django_filters.CharFilter(method="filter_category")
    brand = django_filters.CharFilter(field_name="brand", lookup_expr="iexact")
    # tool_type — вторая ось навигации (slug варианта атрибута), in_stock — наличие.
    tool_type = django_filters.CharFilter(method="filter_tool_type")
    in_stock = django_filters.CharFilter(method="filter_in_stock")
    # Диапазон розничной цены (PLP-фасет «Цена»): price_min / price_max.
    price_min = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    price_max = django_filters.NumberFilter(field_name="price", lookup_expr="lte")

    class Meta:
        model = Product
        fields = ["stock_status"]  # category/brand — объявлены выше явными фильтрами

    def filter_category(self, queryset, name, value):
        try:
            cat = Category.objects.get(slug=value)
        except Category.DoesNotExist:
            return queryset.none()
        ids = [cat.pk, *cat.get_descendants().values_list("pk", flat=True)]
        return queryset.filter(category_id__in=ids)

    def filter_tool_type(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            attribute_values__attribute__slug="tool_type",
            attribute_values__value_option__slug=value,
        )

    def filter_in_stock(self, queryset, name, value):
        if str(value) in ("1", "true", "True", "yes"):
            return queryset.filter(stock_quantity__gt=0)
        return queryset


def filtered_products(category, *, brands=None, stock_status=None):
    """Видимые товары категории (+ все потомки) с опциональными фильтрами.

    brands — список брендов, OR с регистронезависимым сравнением.
    """
    ids = [category.pk, *category.get_descendants().values_list("pk", flat=True)]
    qs = visible_products().filter(category_id__in=ids)
    if brands:
        qs = qs.filter(reduce(operator.or_, (Q(brand__iexact=b) for b in brands)))
    if stock_status:
        qs = qs.filter(stock_status=stock_status)
    return qs
