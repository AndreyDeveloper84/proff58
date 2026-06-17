"""Цены: денормализация в Product + история в PriceRecord.

Инвариант: одна актуальная цена на (code_1c, price_type, currency). Защищаем
его транзакцией прямо здесь — функция публичная внутри слоя и обязана сама
гарантировать инвариант, даже если вызвана вне внешней транзакции.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product

from . import matching
from .models import PriceRecord
from .normalizers import Item

_PRICE_FIELDS = ["price", "old_price", "currency", "price_updated_at"]


def set_current_price(product: Product, item: Item) -> bool:
    """Записать цену в Product и завести актуальную PriceRecord. Не сохраняет Product."""
    if item.price is None:
        return False
    currency = item.currency or product.currency or "RUB"
    price_type = item.price_type or "retail"

    product.price = item.price
    if item.old_price is not None:
        product.old_price = item.old_price
    product.currency = currency
    product.price_updated_at = timezone.now()

    if product.code_1c:
        # Снять актуальность со старой цены и создать новую — атомарно.
        with transaction.atomic():
            PriceRecord.objects.filter(
                code_1c=product.code_1c,
                price_type=price_type,
                currency=currency,
                is_current=True,
            ).update(is_current=False)
            PriceRecord.objects.create(
                code_1c=product.code_1c,
                product=product,
                price_type=price_type,
                value=item.price,
                currency=currency,
                is_current=True,
            )
    return True


def update_price(item: Item) -> bool:
    """Точечно применить цену к найденному товару (find-first). Используется shim'ом."""
    product = matching.find_product(item)
    if product is None:
        return False
    if not set_current_price(product, item):
        return False
    product.save(update_fields=_PRICE_FIELDS)
    return True
