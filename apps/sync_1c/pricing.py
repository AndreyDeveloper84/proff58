"""Цены: денормализация в Product + история в PriceRecord.

Инвариант: одна актуальная цена на (code_1c, price_type, currency). Защищаем
его транзакцией прямо здесь — функция публичная внутри слоя и обязана сама
гарантировать инвариант, даже если вызвана вне внешней транзакции.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Product

from . import matching
from .models import PriceRecord
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
    current_value = None
    if product.code_1c:
        current_value = (
            PriceRecord.objects.filter(
                code_1c=product.code_1c,
                price_type=price_type,
                currency=currency,
                is_current=True,
            )
            .values_list("value", flat=True)
            .first()
        )
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
        # Снять актуальность со старой цены и создать новую — атомарно.
        # select_for_update на товар сериализует два параллельных обновления цены одного
        # code_1c (защита existing-товаров, #126): второй поток ждёт коммита первого и
        # видит уже новую актуальную цену вместо гонки на partial-unique-констрейнте.
        with transaction.atomic():
            if product.pk:
                Product.objects.select_for_update().filter(pk=product.pk).first()
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
    codes = {c for c in codes if c}
    out: dict[tuple[str, str, str], tuple[int, Decimal]] = {}
    if not codes:
        return out
    for r in PriceRecord.objects.filter(code_1c__in=codes, is_current=True).values(
        "id", "code_1c", "price_type", "currency", "value"
    ):
        out[(r["code_1c"], r["price_type"], r["currency"])] = (r["id"], r["value"])
    return out


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
    """Снять актуальность со старых цен и создать новые — пачками.

    Дедуп по (code_1c, price_type, currency) с last-wins: защищает от двух is_current=True
    при дубле code_1c в одном батче (иначе partial-unique даст IntegrityError).
    Только товары с code_1c пишут PriceRecord (как `set_current_price`).
    """
    by_key: dict[tuple[str, str, str], PriceChange] = {}
    for ch in changes:
        if ch.code_1c:
            by_key[(ch.code_1c, ch.price_type, ch.currency)] = ch  # last-wins
    if not by_key:
        return
    flip_ids = [
        current[k][0] for k in by_key if k in current
    ]  # id старых актуальных записей этого батча
    if flip_ids:
        PriceRecord.objects.filter(id__in=flip_ids).update(is_current=False)
    creates = [
        PriceRecord(
            code_1c=ch.code_1c,
            product=ch.product,
            price_type=ch.price_type,
            value=ch.value,
            currency=ch.currency,
            is_current=True,
        )
        for ch in by_key.values()
    ]
    PriceRecord.objects.bulk_create(creates, batch_size=batch_size)
