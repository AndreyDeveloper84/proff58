"""Изменение состава и количества заказа менеджером (T8).

Единственная точка правки строк вне ``place_order``. Админка не сохраняет
инлайн строк напрямую — она передаёт сюда желаемые количества, а сервис под
замком заказа и товаров:

* проверяет, что заказ ещё можно править (`editable_reason`);
* меняет резерв склада согласованно с новым количеством (только пока резерв
  удержан — ``HELD``; снятый резерв остаток не трогает, списанный — править
  нельзя);
* пересчитывает ``line_total``, итог заказа и НДС по тем же правилам, что
  ``place_order``; цены строк не пересматриваются (снимок на момент заказа).

Заказы с промо-скидками не правятся: пересчёт акции вне checkout не
реализован, а править итог «на глаз» нельзя. Уведомление покупателю здесь не
шлётся: события смены состава нет, а письмо о статусе (T2) идёт по своим
переходам — так дублей не возникает.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.accounts.models import CustomerType
from apps.catalog.models import Product

from .models import (
    DeliveryCalcStatus,
    FulfillmentStatus,
    Order,
    OrderItem,
    PaymentStatus,
    ReservationStatus,
)

logger = logging.getLogger(__name__)
_ZERO = Decimal("0.00")

# Пока заказ здесь — состав ещё не собран и не отгружен.
EDITABLE_FULFILLMENT = {FulfillmentStatus.NEW, FulfillmentStatus.CONFIRMED}


def editable_reason(order: Order) -> str:
    """Пусто — состав и доставку править можно; иначе понятная причина отказа."""
    if order.payment_status != PaymentStatus.PENDING:
        return (
            f"заказ в статусе оплаты «{order.get_payment_status_display()}» — состав и суммы "
            "заморожены; возврат или доплата оформляются отдельно"
        )
    if order.fulfillment_status not in EDITABLE_FULFILLMENT:
        return (
            f"заказ уже «{order.get_fulfillment_status_display()}» — состав менять поздно, "
            "отмените заказ или оформите новый"
        )
    if order.reservation_status == ReservationStatus.CONFIRMED:
        return "резерв уже списан со склада — состав заморожен"
    if order.promo_code or (order.items_discount_total or _ZERO) > _ZERO:
        return "по заказу применена акция — пересчёт скидки вне оформления не поддерживается"
    return ""


def financial_fields_locked(order: Order) -> bool:
    """Суммы и доставка заморожены (оплачен/возврат/отгружен/отменён)."""
    return order.payment_status != PaymentStatus.PENDING or order.fulfillment_status in {
        FulfillmentStatus.SHIPPED,
        FulfillmentStatus.COMPLETED,
        FulfillmentStatus.CANCELLED,
    }


def expected_total(order: Order, *, delivery_cost: Decimal | None, items=None) -> Decimal:
    """Итог по правилам place_order: товары − скидка + доставка − скидка на доставку.
    Неизвестная доставка (None) в итог не входит — он предварительный."""
    rows = items if items is not None else order.items.all()
    goods = sum((i.line_total or _ZERO for i in rows), _ZERO)
    total = goods - (order.items_discount_total or _ZERO)
    if delivery_cost is not None:
        total += delivery_cost - (order.delivery_discount or _ZERO)
    return max(total, _ZERO)


def _apply_totals(order: Order, items) -> None:
    from django.conf import settings

    cost = (
        order.delivery_cost if order.delivery_calc_status == DeliveryCalcStatus.CALCULATED else None
    )
    order.total = expected_total(order, delivery_cost=cost, items=items)
    if order.customer_type == CustomerType.B2B:
        from apps.pricing.vat import vat_breakdown

        rate = int(getattr(settings, "VAT_RATE_PERCENT", 0))
        net, vat = vat_breakdown(order.total, rate)
        order.vat_rate, order.amount_without_vat, order.vat_amount = rate, net, vat


def update_quantities(
    order_id: int, quantities: dict[int, int], *, actor_id: int | None = None
) -> tuple[Order, list[str]]:
    """Применить новые количества строк ``{item_id: qty}``; ``qty=0`` — убрать строку.

    Всё или ничего: любая ошибка (нет остатка, отрицательное количество,
    заморозка) → ValidationError и откат. Возвращает заказ и список изменений
    для журнала. Повторный вызов с теми же количествами ничего не меняет.
    """
    for qty in quantities.values():
        if qty < 0:
            raise ValidationError("Количество не может быть отрицательным.")

    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        reason = editable_reason(order)
        if reason:
            raise ValidationError(f"Состав заказа изменить нельзя: {reason}.")

        items = {it.pk: it for it in OrderItem.objects.filter(order=order).order_by("pk")}
        unknown = set(quantities) - set(items)
        if unknown:
            raise ValidationError("Строка не принадлежит этому заказу.")
        changes = {pk: qty for pk, qty in quantities.items() if items[pk].quantity != qty}
        if not changes:
            return order, []
        if all(qty == 0 for pk, qty in changes.items()) and len(changes) == len(items):
            raise ValidationError("Нельзя убрать все строки — отмените заказ кнопкой перехода.")

        # Замки товаров в том же порядке, что place_order/rehold: по id.
        held = order.reservation_status == ReservationStatus.HELD
        product_ids = sorted({items[pk].product_id for pk in changes if items[pk].product_id})
        locked = {
            p.pk: p
            for p in Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")
        }
        # Суммарная дельта по товару (одна позиция может встречаться в двух строках).
        delta: dict[int, int] = {}
        for pk, qty in changes.items():
            pid = items[pk].product_id
            if pid:
                delta[pid] = delta.get(pid, 0) + (qty - items[pk].quantity)
        if held:
            for pid, d in delta.items():
                if d <= 0:
                    continue
                product = locked.get(pid)
                free = (product.available_quantity or Decimal("0")) if product else Decimal("0")
                if free < d:
                    name = next(items[pk].name for pk in changes if items[pk].product_id == pid)
                    raise ValidationError(
                        f"Товара нет в наличии: {name} — свободно {free:g}, нужно ещё {d}."
                    )

        log: list[str] = []
        for pk, qty in changes.items():
            it = items[pk]
            if qty == 0:
                log.append(f"убрана строка «{it.name}» ({it.quantity} {it.unit or 'шт'})")
                it.delete()
                del items[pk]
                continue
            log.append(f"«{it.name}»: {it.quantity} → {qty}")
            it.quantity = qty
            it.line_total = (it.price_final * qty).quantize(Decimal("0.01"))
            it.save(update_fields=["quantity", "line_total"])

        if held:
            for pid, d in delta.items():
                if d:
                    Product.objects.filter(pk=pid).update(
                        available_quantity=models.F("available_quantity") - d,
                        reserved_quantity=models.F("reserved_quantity") + d,
                    )

        _apply_totals(order, list(items.values()))
        order.save(
            update_fields=["total", "vat_rate", "amount_without_vat", "vat_amount", "updated_at"]
        )
    logger.info(
        "Order %s items edited by user %s: %s", order.order_number, actor_id, "; ".join(log)
    )
    return order, log
