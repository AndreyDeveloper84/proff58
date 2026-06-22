"""Подписчики на доменные события заказов — отправка уведомлений в MAX (#48).

Подключаются в IntegrationMaxConfig.ready() под feature-флагом max_chat.
"""

from __future__ import annotations

import logging

from django.dispatch import receiver

from apps.core.events import order_created, order_paid, order_status_changed

from .handlers.orders import send_order_notification_task

logger = logging.getLogger(__name__)


def _get_order_and_chat_id(order_id: int):
    """Получить заказ и max_chat_id пользователя. Возвращает (order, chat_id) или (None, None)."""
    from apps.orders.models import Order

    try:
        order = Order.objects.select_related("user").get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning("MAX notify: заказ %s не найден", order_id)
        return None, None

    if not order.user:
        logger.debug("MAX notify: заказ %s без пользователя (гость)", order.order_number)
        return order, None

    chat_id = getattr(order.user, "max_chat_id", None)
    if not chat_id:
        logger.debug("MAX notify: пользователь %s без max_chat_id", order.user_id)
        return order, None

    return order, chat_id


@receiver(order_created)
def on_order_created(sender, order_id: int, **kwargs) -> None:
    """Новый заказ — уведомляем покупателя."""
    order, chat_id = _get_order_and_chat_id(order_id)
    if not chat_id:
        return
    send_order_notification_task.delay(chat_id, "order_created", order.order_number)


@receiver(order_paid)
def on_order_paid(sender, order_id: int, **kwargs) -> None:
    """Заказ оплачен — уведомляем покупателя."""
    order, chat_id = _get_order_and_chat_id(order_id)
    if not chat_id:
        return
    send_order_notification_task.delay(chat_id, "order_paid", order.order_number)


@receiver(order_status_changed)
def on_order_status_changed(sender, order_id: int, old_status: str, new_status: str, **kwargs):
    """Смена fulfillment_status — уведомляем при shipped/completed."""
    event_map = {
        "shipped": "order_shipped",
        "completed": "order_completed",
    }
    event = event_map.get(new_status)
    if not event:
        return

    order, chat_id = _get_order_and_chat_id(order_id)
    if not chat_id:
        return

    extra = ""
    if new_status == "shipped" and order.tracking_number:
        extra = f" Трек-номер: {order.tracking_number}"

    send_order_notification_task.delay(chat_id, event, order.order_number, extra)
