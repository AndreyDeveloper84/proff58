"""Подписчики доменных событий платежей: письмо сотрудникам о заявке на возврат (T2).

Заявка уже закоммичена (издатель — refund_requests.create_request через
on_commit); сбой уведомления только логируется.
"""

from __future__ import annotations

import logging

from apps.core import events

logger = logging.getLogger(__name__)


def staff_refund_snapshot(request_id: int) -> dict | None:
    from django.utils import timezone

    from apps.notifications.services import admin_url

    from .models import RefundRequest

    req = RefundRequest.objects.select_related("order").filter(pk=request_id).first()
    if req is None:
        return None
    order = req.order
    return {
        "request_id": req.pk,
        "order_number": order.order_number,
        "created_at": timezone.localtime(req.created_at).strftime("%d.%m.%Y %H:%M"),
        "customer": order.customer_name or "—",
        "customer_phone": order.customer_phone or "—",
        "reason": req.get_reason_display(),
        "comment": req.comment or "—",
        "admin_url": admin_url(f"/admin/payments/refundrequest/{req.pk}/change/"),
    }


def _on_refund_requested(sender, *, request_id, order_id, **kwargs):
    try:
        payload = staff_refund_snapshot(request_id)
        if payload is None:
            return
        from apps.notifications.services import notify_staff

        notify_staff(
            event="staff_refund_requested",
            payload=payload,
            idempotency_key=f"staff-refund-requested-{request_id}",
        )
    except Exception:  # noqa: BLE001 — уведомление не критично
        logger.exception("Сбой уведомления сотрудников о заявке на возврат %s", request_id)


def connect() -> None:
    events.refund_requested.connect(
        _on_refund_requested, dispatch_uid="payments_notify_staff_refund_requested"
    )
