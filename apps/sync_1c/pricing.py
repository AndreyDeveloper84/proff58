"""Адаптер цен 1С: Item → spec, skip-unchanged (#111), денормализация Product, события 1С.

Здесь живёт семантика интеграции 1С: решение skip-unchanged, мутация
денормализованных полей ``Product`` (price/old_price/currency/price_updated_at) и
формирование плана пакетного импорта (``PriceChange``).

Запись истории цены (``PriceRecord``) этот слой НЕ делает напрямую — она
делегируется в :mod:`apps.pricing.repositories` (домен ``pricing`` — владелец
модели цены). Этот модуль не обращается к менеджеру модели цены напрямую.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.utils import timezone

from apps.catalog.models import Product
from apps.pricing import repositories as pricing_repo

from . import matching
from .normalizers import Item

_PRICE_FIELDS = ["price", "old_price", "currency", "price_updated_at"]


def set_current_price(product: Product, item: Item) -> bool:
    """Записать цену в Product и завести актуальную PriceRecord. Не сохраняет Product.

    Если цена реально не изменилась — НИЧЕГО не пишем (не плодим PriceRecord, не
    трогаем Product, не эмитим price_changed): 1С часто шлёт полный прайс без
    изменений. Возвращаем False (строка уйдёт в skipped).
    """
    if item.price is None:
        return False
    currency = item.currency or product.currency or "RUB"
    price_type = item.price_type or "retail"

    # Skip-unchanged: текущая актуальная цена этого типа/валюты совпадает, денормализация
    # Product совпадает, и old_price не меняется. old_price=None трактуем как «не менять»
    # (1С часто шлёт только price; контракт — в docs/1c-api-spec.md).
    # Без code_1c история не пишется, но skip-unchanged всё равно работает по денормализованному
    # полю Product (#282: без code_1c skip-unchanged не срабатывал → лишние writes).
    if product.code_1c:
        current_value = pricing_repo.current_price_value(product.code_1c, price_type, currency)
    else:
        current_value = product.price
    old_price_unchanged = item.old_price is None or product.old_price == item.old_price
    if (
        current_value is not None
        and current_value == item.price
        and product.price == item.price
        and product.currency == currency
        and old_price_unchanged
    ):
        return False

    product.price = item.price
    if item.old_price is not None:
        product.old_price = item.old_price
    product.currency = currency
    product.price_updated_at = timezone.now()

    if product.code_1c:
        # Запись истории цены — атомарно, инвариант «одна current» держит repository.
        pricing_repo.write_current_price(
            code_1c=product.code_1c,
            product=product,
            value=item.price,
            price_type=price_type,
            currency=currency,
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


# --- Пакетные цены (#125B): отдельный сервис, не размазан по use_cases ---


@dataclass
class PriceChange:
    """Запланированное изменение цены (Product уже промутирован в памяти)."""

    product: Product
    code_1c: str
    price_type: str
    currency: str
    value: Decimal
    price_event: bool  # цена реально изменилась (для price_changed)
    old_price_for_event: Decimal | None


def prefetch_current_prices(codes) -> dict[tuple[str, str, str], tuple[int, Decimal]]:
    """Карта актуальных цен батча: (code_1c, price_type, currency) → (record_id, value). 1 запрос."""
    return pricing_repo.current_price_map(codes)


def plan_price(
    product: Product, item: Item, *, current: dict[tuple[str, str, str], tuple[int, Decimal]]
) -> PriceChange | None:
    """Решить изменение цены и промутировать денормализацию Product (БЕЗ записи в БД).

    Логика skip-unchanged (#111) идентична `set_current_price`, но «текущая цена» берётся
    из префетча, а PriceRecord не пишется — это делает `apply_prices_bulk` пачкой.
    """
    if item.price is None:
        return None
    currency = item.currency or product.currency or "RUB"
    price_type = item.price_type or "retail"
    current_value = None
    if product.code_1c:
        found = current.get((product.code_1c, price_type, currency))
        current_value = found[1] if found else None
    old_price_unchanged = item.old_price is None or product.old_price == item.old_price
    if (
        current_value is not None
        and current_value == item.price
        and product.price == item.price
        and product.currency == currency
        and old_price_unchanged
    ):
        return None

    old_price_denorm = product.price
    product.price = item.price
    if item.old_price is not None:
        product.old_price = item.old_price
    product.currency = currency
    product.price_updated_at = timezone.now()
    return PriceChange(
        product=product,
        code_1c=product.code_1c or "",
        price_type=price_type,
        currency=currency,
        value=item.price,
        price_event=old_price_denorm != item.price,
        old_price_for_event=old_price_denorm,
    )


def apply_prices_bulk(
    changes: list[PriceChange],
    current: dict[tuple[str, str, str], tuple[int, Decimal]],
    *,
    batch_size: int = 1000,
) -> None:
    """Записать историю цен пачкой через repository.

    Маппит `PriceChange` → `pricing_repo.PriceWrite` (только товары с code_1c, как
    `set_current_price`) и делегирует снятие актуальности/создание новых записей в
    :func:`apps.pricing.repositories.apply_prices_bulk` (там же дедуп last-wins и
    атомарность инварианта «одна current»).
    """
    writes = [
        pricing_repo.PriceWrite(
            code_1c=ch.code_1c,
            product=ch.product,
            price_type=ch.price_type,
            currency=ch.currency,
            value=ch.value,
        )
        for ch in changes
        if ch.code_1c
    ]
    pricing_repo.apply_prices_bulk(writes, current, batch_size=batch_size)
