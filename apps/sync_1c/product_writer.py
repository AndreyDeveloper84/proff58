"""Создание и обновление Product из данных 1С.

Знает только про домен каталога (Product, категоризация, цена, остаток).
НЕ знает про staging, SyncLog, source_file, ImportResult и API — это слой
оркестрации (`use_cases.py`).

Главное правило: повторное обновление НЕ трогает ручной контент сайта
(категорию, витринное `name`, описание, SEO, фото, slug).
"""

from __future__ import annotations

from apps.catalog.categorization import ProductHint, categorize
from apps.catalog.models import Product, ProductStatus

from . import pricing, stock
from .normalizers import Item


def create_product(item: Item) -> tuple[Product, bool]:
    """Создать товар из строки 1С. Вернуть (product, categorized?)."""
    category, rule = categorize(
        ProductHint(
            name=item.name,
            article=item.article,
            brand=item.brand,
            source_group=item.source_group,
        )
    )
    product = Product(
        code_1c=item.code_1c or None,
        article=item.article,
        barcode=item.barcode,
        original_name=item.name,
        name=item.name,  # витринное имя при создании = имя из 1С; далее правится вручную
        brand=item.brand,
        source_group=item.source_group,
        unit=item.unit,
        is_active_1c=item.is_active,
        category=category,
        matched_rule=rule,
        status=ProductStatus.DRAFT if category else ProductStatus.NEEDS_REVIEW,
    )
    product.save()  # нужен pk для записей цены/остатка
    pricing.set_current_price(product, item)
    stock.set_current_stock(product, item)
    product.save()
    return product, category is not None


def update_existing(product: Product, item: Item, *, allow_basic_fields: bool = True) -> None:
    """Обновить существующий товар, не затрагивая ручной контент сайта."""
    pricing.set_current_price(product, item)
    stock.set_current_stock(product, item)

    if allow_basic_fields:
        if item.name:
            product.original_name = item.name  # витринное name НЕ трогаем
        if item.brand and not product.brand:
            product.brand = item.brand
        if item.barcode:
            product.barcode = item.barcode
        if item.unit:
            product.unit = item.unit
        if item.is_active is not None:
            product.is_active_1c = item.is_active
        if item.source_group:
            product.source_group = item.source_group

    # Категория, name(витрина), description, SEO, фото, slug — НЕ трогаем.
    product.save()
