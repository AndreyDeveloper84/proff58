"""Celery-задачи заказов (#423, B-03).

Janitor освобождения просроченного резерва: незавершённые/неоплаченные заказы
не должны навсегда «съедать» свободный остаток.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from .models import Order, PaymentStatus, ReservationStatus
from .reservation import release_reservation

logger = logging.getLogger(__name__)


@shared_task(name="apps.orders.tasks.release_expired_reservations")
def release_expired_reservations(limit: int = 500) -> int:
    """Освободить резерв у просроченных неоплаченных заказов.

    Кандидаты: reservation_status=HELD, reserved_until в прошлом, платёж не PAID.
    Каждый заказ освобождается идемпотентно (release_reservation под
    select_for_update). Возвращает число фактически освобождённых.
    """
    now = timezone.now()
    ids = list(
        Order.objects.filter(
            reservation_status=ReservationStatus.HELD,
            reserved_until__lt=now,
        )
        .exclude(payment_status=PaymentStatus.PAID)
        .order_by("reserved_until")
        .values_list("pk", flat=True)[:limit]
    )
    released = 0
    for order_id in ids:
        if release_reservation(order_id):
            released += 1
    if released:
        logger.info("release_expired_reservations: released %s reservation(s)", released)
    return released


@shared_task(name="apps.orders.tasks.expire_b2b_invoices")
def expire_b2b_invoices(limit: int = 500) -> int:
    """#559: истечь неоплаченные B2B-счета старше 24ч.

    Атомарно на каждый счёт: счёт → EXPIRED, заказ → payment=EXPIRED +
    fulfillment=CANCELLED, резерв освобождается (идемпотентно — двойного
    возврата остатков не бывает, даже если release_expired_reservations
    успел отработать раньше).
    """
    from .invoice_lifecycle import expire_due_invoices

    return expire_due_invoices(limit=limit)
