"""Жизненный цикл B2B-счёта (#559, эпик #557, Wave 1).

Единая точка issue/expire/paid. Инварианты:

- счёт выставляется РОВНО один раз при оформлении B2B-заказа;
- ``valid_until == Order.reserved_until`` (счёт и резерв истекают вместе);
- истечение атомарно: счёт → EXPIRED, заказ → payment=EXPIRED + fulfillment=
  CANCELLED (по матрице переходов), резерв освобождается В ТОЙ ЖЕ транзакции —
  «живой» заказ со снятым резервом невозможен;
- двойной возврат остатков исключён: release идемпотентен по
  ``Order.reservation_status`` (HELD → RELEASED, повтор — no-op);
- оплата: счёт → PAID, заказ → payment=PAID, резерв СПИСЫВАЕТСЯ (confirm),
  а не освобождается. Оплатить можно только действующий (ISSUED) счёт.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core import events

from .models import B2BInvoice, FulfillmentStatus, InvoiceStatus, Order, PaymentStatus
from .reservation import confirm_reservation, release_reservation
from .transitions import can_transition

logger = logging.getLogger(__name__)


def issue_invoice(order: Order) -> B2BInvoice:
    """Выставить счёт по B2B-заказу. Идемпотентно (второй вызов вернёт существующий).

    Вызывается из ``place_order`` внутри транзакции оформления: ``valid_until``
    привязывается к уже назначенному ``order.reserved_until`` — счёт и резерв
    истекают в один момент.
    """
    existing = B2BInvoice.objects.filter(order=order).first()
    if existing is not None:
        return existing
    issued_at = timezone.now()
    valid_until = order.reserved_until or (issued_at + timezone.timedelta(hours=24))
    invoice = B2BInvoice.objects.create(
        order=order,
        # Номер производен от номера заказа (он уникален) — человекочитаемо и
        # без отдельного счётчика: «СЧ-П-20260720-ABC123».
        number=f"СЧ-{order.order_number}",
        status=InvoiceStatus.ISSUED,
        issued_at=issued_at,
        valid_until=valid_until,
    )
    logger.info("B2B invoice %s issued for order #%s", invoice.number, order.order_number)
    return invoice


def mark_invoice_paid(invoice_id: int) -> B2BInvoice:
    """Отметить счёт оплаченным (менеджер/система).

    Счёт → PAID, заказ → payment_status=PAID, резерв списывается (confirm).
    Оплатить можно только ISSUED-счёт: после EXPIRED заказ уже отменён и резерв
    возвращён в остаток — «оживление» такого заказа только руками, отдельным
    решением (иначе можно продать уже освобождённый товар).
    """
    with transaction.atomic():
        invoice = B2BInvoice.objects.select_for_update().select_related("order").get(pk=invoice_id)
        if invoice.status == InvoiceStatus.PAID:
            return invoice  # идемпотентно
        if invoice.status != InvoiceStatus.ISSUED:
            raise ValidationError(
                f"Счёт {invoice.number} нельзя отметить оплаченным: "
                f"он в статусе «{invoice.get_status_display()}»."
            )
        order = Order.objects.select_for_update().get(pk=invoice.order_id)

        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=["status", "paid_at", "updated_at"])

        order.payment_status = PaymentStatus.PAID
        order.save(update_fields=["payment_status", "updated_at"])

        # Товар уходит покупателю — резерв списываем, СВОБОДНЫЙ остаток не меняется.
        confirm_reservation(order.pk)

        transaction.on_commit(
            lambda oid=order.pk: events.payment_succeeded.send(
                sender=B2BInvoice, order_id=oid, payment_id=None
            )
        )
    logger.info("B2B invoice %s marked paid (order #%s)", invoice.number, order.order_number)
    return invoice


def _expire_one(invoice_id: int) -> bool:
    """Истечь один счёт. Атомарно и идемпотентно. True — если счёт истёк здесь."""
    now = timezone.now()
    with transaction.atomic():
        invoice = (
            B2BInvoice.objects.select_for_update()
            .filter(pk=invoice_id, status=InvoiceStatus.ISSUED, valid_until__lt=now)
            .first()
        )
        if invoice is None:
            return False  # уже оплачен/истёк/отменён параллельным процессом
        order = Order.objects.select_for_update().get(pk=invoice.order_id)
        if order.payment_status == PaymentStatus.PAID:
            # Рассинхрон (оплату отметили мимо счёта) — счёт приводим к PAID,
            # заказ не трогаем. Не отменять оплаченный заказ важнее симметрии.
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = invoice.paid_at or now
            invoice.save(update_fields=["status", "paid_at", "updated_at"])
            logger.warning(
                "B2B invoice %s: order already paid, invoice aligned to PAID", invoice.number
            )
            return False

        invoice.status = InvoiceStatus.EXPIRED
        invoice.save(update_fields=["status", "updated_at"])

        old_fulfillment = order.fulfillment_status
        order.payment_status = PaymentStatus.EXPIRED
        update_fields = ["payment_status", "updated_at"]
        if can_transition(old_fulfillment, FulfillmentStatus.CANCELLED):
            order.fulfillment_status = FulfillmentStatus.CANCELLED
            update_fields.append("fulfillment_status")
        else:  # терминальный статус (completed) — заказ не трогаем, только счёт
            logger.warning(
                "B2B invoice %s expired, but order #%s is %s — fulfillment kept",
                invoice.number,
                order.order_number,
                old_fulfillment,
            )
        order.save(update_fields=update_fields)

        # Возврат резерва В ТОЙ ЖЕ транзакции: невозможен «отменённый заказ с
        # удержанным резервом». Идемпотентно (HELD→RELEASED), двойного возврата нет.
        release_reservation(order.pk)

        if FulfillmentStatus.CANCELLED == order.fulfillment_status != old_fulfillment:
            transaction.on_commit(
                lambda oid=order.pk, old=old_fulfillment: events.order_status_changed.send(
                    sender=Order,
                    order_id=oid,
                    old_status=old,
                    new_status=FulfillmentStatus.CANCELLED,
                )
            )
    logger.info("B2B invoice %s expired → order #%s cancelled", invoice.number, order.order_number)
    return True


def expire_due_invoices(limit: int = 500) -> int:
    """Истечь все просроченные неоплаченные счета. Возвращает число истёкших."""
    now = timezone.now()
    ids = list(
        B2BInvoice.objects.filter(status=InvoiceStatus.ISSUED, valid_until__lt=now)
        .order_by("valid_until")
        .values_list("pk", flat=True)[:limit]
    )
    expired = 0
    for invoice_id in ids:
        if _expire_one(invoice_id):
            expired += 1
    if expired:
        logger.info("expire_due_invoices: expired %s invoice(s)", expired)
    return expired
