"""Контракт персистентности цены: доступ к ``PriceRecord`` живёт здесь.

Домен ``pricing`` — владелец модели ``PriceRecord``, поэтому он же владеет и
примитивами чтения/записи истории цены. Интеграционный слой ``sync_1c`` больше
НЕ обращается к ``PriceRecord.objects`` напрямую — он зовёт функции этого модуля
(тонкий адаптер ``apps/sync_1c/pricing.py``).

Инвариант: одна актуальная цена на ``(code_1c, price_type, currency)``
(partial-unique ``uniq_current_price_per_code_type_currency``). Записи здесь
обёрнуты в ``transaction.atomic()``, чтобы гарантировать инвариант даже вне
внешней транзакции.

Здесь — ТОЛЬКО персистентность PriceRecord: skip-unchanged-решение и
денормализация ``Product`` (price/old_price/currency/price_updated_at) остаются
в адаптере ``sync_1c`` (это семантика 1С, не домена цены).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from apps.catalog.models import Product

from .models import PriceRecord


def current_price_value(code_1c: str, price_type: str, currency: str) -> Decimal | None:
    """Текущая актуальная цена ``(code_1c, price_type, currency)`` или None. 1 запрос."""
    return (
        PriceRecord.objects.filter(
            code_1c=code_1c,
            price_type=price_type,
            currency=currency,
            is_current=True,
        )
        .values_list("value", flat=True)
        .first()
    )


def current_price_map(codes) -> dict[tuple[str, str, str], tuple[int, Decimal]]:
    """Карта актуальных цен батча: ``(code_1c, price_type, currency) → (record_id, value)``.

    ``record_id`` нужен для bulk-flip (снять is_current со старых одним запросом).
    Пустые коды игнорируются. Один запрос.
    """
    codes = {c for c in codes if c}
    out: dict[tuple[str, str, str], tuple[int, Decimal]] = {}
    if not codes:
        return out
    for r in PriceRecord.objects.filter(code_1c__in=codes, is_current=True).values(
        "id", "code_1c", "price_type", "currency", "value"
    ):
        out[(r["code_1c"], r["price_type"], r["currency"])] = (r["id"], r["value"])
    return out


def write_current_price(
    *,
    code_1c: str,
    product: Product,
    value: Decimal,
    price_type: str,
    currency: str,
) -> None:
    """Атомарно снять актуальность со старой цены и завести новую актуальную.

    БЕЗ денормализации ``Product`` и БЕЗ skip-решения (это семантика адаптера 1С) —
    здесь только запись истории цены.

    ``select_for_update`` на ``catalog.Product`` сохранён как существующий
    lock-target ради сериализации гонок обновления цены одного code_1c (#126):
    второй поток ждёт коммита первого и видит уже новую актуальную цену вместо
    гонки на partial-unique-констрейнте. Замечание: цена идентифицируется по
    ``(code_1c, price_type, currency)``, а блокируем мы ``catalog.Product`` — это
    перенос существующего поведения, а не новый замок.
    """
    with transaction.atomic():
        if product.pk:
            Product.objects.select_for_update().filter(pk=product.pk).first()
        PriceRecord.objects.filter(
            code_1c=code_1c,
            price_type=price_type,
            currency=currency,
            is_current=True,
        ).update(is_current=False)
        PriceRecord.objects.create(
            code_1c=code_1c,
            product=product,
            price_type=price_type,
            value=value,
            currency=currency,
            is_current=True,
        )


@dataclass
class PriceWrite:
    """Запланированная запись цены в историю (для пакетного пути)."""

    code_1c: str
    product: Product
    price_type: str
    currency: str
    value: Decimal


def apply_prices_bulk(
    writes: list[PriceWrite],
    current_map: dict[tuple[str, str, str], tuple[int, Decimal]],
    *,
    batch_size: int = 1000,
) -> None:
    """Снять актуальность со старых цен и создать новые — пачками, в одной транзакции.

    Дедуп по ``(code_1c, price_type, currency)`` с last-wins: защищает от двух
    is_current=True при дубле code_1c В ОДНОМ батче (иначе partial-unique даст
    IntegrityError). Только записи с непустым ``code_1c`` пишут PriceRecord.

    Flip is_current=False по старым актуальным записям (их id берём из
    ``current_map``) и ``bulk_create`` новых обёрнуты в ОДИН ``transaction.atomic()``
    ради доменного инварианта «одна current»: happy-path не меняется, но окно между
    flip и create больше не оставляет 0 или 2 актуальных записи при сбое.

    Замечание: last-wins защищает только дубли ВНУТРИ батча; межбатчевые гонки —
    отдельной задачей, retry здесь НЕ добавляется.
    """
    by_key: dict[tuple[str, str, str], PriceWrite] = {}
    for w in writes:
        if w.code_1c:
            by_key[(w.code_1c, w.price_type, w.currency)] = w  # last-wins
    if not by_key:
        return
    flip_ids = [
        current_map[k][0] for k in by_key if k in current_map
    ]  # id старых актуальных записей этого батча
    creates = [
        PriceRecord(
            code_1c=w.code_1c,
            product=w.product,
            price_type=w.price_type,
            value=w.value,
            currency=w.currency,
            is_current=True,
        )
        for w in by_key.values()
    ]
    with transaction.atomic():
        if flip_ids:
            PriceRecord.objects.filter(id__in=flip_ids).update(is_current=False)
        PriceRecord.objects.bulk_create(creates, batch_size=batch_size)
