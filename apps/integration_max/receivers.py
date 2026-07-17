"""Подписчики доменных событий заказов → уведомления в MAX через notifications.send().

Тонкий адаптер (#514): подключаются в AppConfig.ready() детерминированно, без
проверки бизнес-флага (та проверяется в notifications.send() при постановке в
outbox — единственном месте, отвечающем за resolve получателя и флаг). Здесь
НЕ решаем, есть ли у пользователя MAX-получатель — это владение notifications/
integration_max.services.resolve_active_chat_id().
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model

from apps.core import events

logger = logging.getLogger(__name__)
User = get_user_model()


def _get_order_user(order_id: int):
    from apps.orders.models import Order

    try:
        order = Order.objects.select_related("user").get(pk=order_id)
    except Order.DoesNotExist:
        return None, None
    return order, order.user


def _on_order_created(sender, order_id, **kwargs):
    order, user = _get_order_user(order_id)
    if not order or not user:
        return
    from apps.notifications.services import send

    send(
        user=user,
        event="order_created",
        payload={"order_id": order.order_number},
        idempotency_key=f"order-created-{order_id}",
    )


def _on_order_paid(sender, order_id, **kwargs):
    order, user = _get_order_user(order_id)
    if not order or not user:
        return
    from apps.notifications.services import send

    send(
        user=user,
        event="order_paid",
        payload={"order_id": order.order_number},
        idempotency_key=f"order-paid-{order_id}",
    )


def _on_order_status_changed(sender, order_id, old_status, new_status, **kwargs):
    order, user = _get_order_user(order_id)
    if not order or not user:
        return
    from apps.notifications.services import send

    event_map = {
        "shipped": "order_shipped",
        "completed": "order_delivered",
    }
    event = event_map.get(new_status, "order_status_changed")
    send(
        user=user,
        event=event,
        payload={"order_id": order.order_number, "new_status": new_status},
        idempotency_key=f"order-status-{order_id}-{new_status}",
    )


events.order_created.connect(_on_order_created, dispatch_uid="integration_max_order_created")
events.order_paid.connect(_on_order_paid, dispatch_uid="integration_max_order_paid")
events.order_status_changed.connect(
    _on_order_status_changed, dispatch_uid="integration_max_order_status_changed"
)
