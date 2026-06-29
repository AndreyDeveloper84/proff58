"""Подписчики доменных событий заказов → уведомления в MAX через notifications.send().

Подключаются в AppConfig.ready() только при is_enabled("max_chat").
Отправка идёт через единый сервис apps.notifications — не напрямую в MAX.
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
    if not order or not user or not getattr(user, "max_chat_id", None):
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
    if not order or not user or not getattr(user, "max_chat_id", None):
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
    if not order or not user or not getattr(user, "max_chat_id", None):
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


events.order_created.connect(_on_order_created)
events.order_paid.connect(_on_order_paid)
events.order_status_changed.connect(_on_order_status_changed)
