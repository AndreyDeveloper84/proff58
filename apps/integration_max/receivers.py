"""Подписчики доменных событий заказов → уведомления в MAX через
notifications.services.create_notification().

Тонкий адаптер (#514/#516): подключаются в AppConfig.ready() детерминированно,
без проверки бизнес-флага (та проверяется в notifications.send() при постановке
в outbox) и без проверки preferences (проверяется в create_notification() —
#515). Здесь только: (1) типизированный маппинг доменное событие → MAX-событие/
шаблон, (2) снимок безопасных данных заказа (публичный номер, способ получения,
трек-номер — НЕ id/токены), (3) idempotency_key на уровне order+ось+цель.

Для гостевых заказов (``order.user is None``) — параллельная ветка через
``OrderTrackingGrant`` (#520, см. _notify_guest_tracking): тот же outbox/Celery/
retry (notifications.services.send()), но без intent/preference/history-слоя
(create_notification()/Notification) — тому гостю без аккаунта нечего показать.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model

from apps.core import events

logger = logging.getLogger(__name__)
User = get_user_model()

# #516 (docs/order-lifecycle.md §8): переходы обработки, о которых уведомляем.
# `assembling` — намеренно отсутствует (MVP не уведомляет, см. Scope тикета);
# любой другой будущий статус, которого здесь нет, тоже молча не уведомляет —
# это осознанный whitelist, а не сокрытие бага (в отличие от #514, где отсутствие
# резолва получателя было багом).
_FULFILLMENT_EVENT_MAP = {
    "confirmed": "order_confirmed",
    "ready": "order_ready",
    "shipped": "order_shipped",
    "completed": "order_delivered",
    "cancelled": "order_cancelled",
}
# Статусы, для которых отсутствие в _FULFILLMENT_EVENT_MAP — осознанное решение
# (MVP scope), а не забытый случай. Всё остальное немаппленное — логируем: если
# apps/orders/models.py FulfillmentStatus обзаведётся новым значением, а сюда
# его забудут добавить, это не должно тихо теряться без единого сигнала (#521).
_KNOWN_NON_NOTIFYING_STATUSES = {"new", "assembling"}


def _get_order_user(order_id: int):
    from apps.orders.models import Order

    try:
        order = Order.objects.select_related("user").get(pk=order_id)
    except Order.DoesNotExist:
        return None, None
    return order, order.user


def _notify_guest_tracking(order, event: str, payload: dict, idempotency_key: str) -> None:
    """Уведомить гостя без аккаунта через OrderTrackingGrant (#520), если он
    подключил отслеживание.

    Через ``notifications.services.send()`` (не ``create_notification()`` — той
    нужен ``user`` для intent/preference-слоя): те же шаблоны NOTIFICATION_EVENTS,
    тот же outbox + Celery-доставка + retry/backoff/классификация ошибок (#521),
    без реализации этого заново здесь. Не создаётся только Notification
    (in-app история/read-state) — гостю без аккаунта нечего показывать в ЛК.
    """
    from .services import resolve_tracking_grant_chat_id

    chat_id = resolve_tracking_grant_chat_id(order)
    if not chat_id:
        return

    from apps.notifications.services import send

    send(user=None, chat_id=chat_id, event=event, payload=payload, idempotency_key=idempotency_key)


def _on_order_created(sender, order_id, **kwargs):
    order, user = _get_order_user(order_id)
    if not order:
        return
    payload = {"order_number": order.order_number}
    if user is None:
        _notify_guest_tracking(order, "order_created", payload, f"order-created-{order_id}")
        return
    from apps.notifications.services import create_notification

    create_notification(
        user=user,
        event="order_created",
        payload=payload,
        idempotency_key=f"order-created-{order_id}",
    )


def _on_order_paid(sender, order_id, **kwargs):
    order, user = _get_order_user(order_id)
    if not order:
        return
    payload = {"order_number": order.order_number}
    if user is None:
        _notify_guest_tracking(order, "order_paid", payload, f"order-paid-{order_id}")
        return
    from apps.notifications.services import create_notification

    create_notification(
        user=user,
        event="order_paid",
        payload=payload,
        idempotency_key=f"order-paid-{order_id}",
    )


def _on_order_status_changed(sender, order_id, old_status, new_status, **kwargs):
    event = _FULFILLMENT_EVENT_MAP.get(new_status)
    if event is None:
        if new_status not in _KNOWN_NON_NOTIFYING_STATUSES:
            logger.warning(
                "order_status_changed: new_status=%s has no MAX event mapping (order=%s) — "
                "проверить _FULFILLMENT_EVENT_MAP, если это реальный новый статус",
                new_status,
                order_id,
            )
        return
    order, user = _get_order_user(order_id)
    if not order:
        return

    payload = {"order_number": order.order_number}
    if event == "order_ready":
        # AC #516: ready учитывает способ получения в тексте.
        from apps.delivery.models import DeliveryType

        if order.delivery_method == DeliveryType.PICKUP:
            payload["ready_note"] = " Готов к выдаче в пункте самовывоза."
        else:
            payload["ready_note"] = " Скоро передадим в доставку."
    elif event == "order_shipped":
        # AC #516: трек-номер добавляется, только если есть.
        payload["tracking_note"] = (
            f" Трек-номер: {order.tracking_number}." if order.tracking_number else ""
        )

    if user is None:
        _notify_guest_tracking(order, event, payload, f"order-status-{order_id}-{new_status}")
        return
    from apps.notifications.services import create_notification

    create_notification(
        user=user,
        event=event,
        payload=payload,
        idempotency_key=f"order-status-{order_id}-{new_status}",
    )


def _on_payment_refunded(sender, payment_id, order_id, refund_id, amount, is_full, **kwargs):
    order, user = _get_order_user(order_id)
    if not order:
        return
    event = "order_refunded" if is_full else "order_partially_refunded"
    payload = {"order_number": order.order_number}
    # ADR-0009: refund_id — конкретная операция возврата, а не order_id — несколько
    # частичных возвратов по заказу это разные реальные события.
    idempotency_key = f"order-refunded-{order_id}-{refund_id}"
    if user is None:
        _notify_guest_tracking(order, event, payload, idempotency_key)
        return
    from apps.notifications.services import create_notification

    create_notification(
        user=user,
        event=event,
        payload=payload,
        idempotency_key=idempotency_key,
    )


def _on_product_stock_became_available(
    sender, product_id, old_available, new_available, source, transition_id, **kwargs
):
    """#518 (ADR-0010): только ставит fan-out в очередь — сам обработчик
    выполняется синхронно после commit импорта/HTTP-запроса 1С, поэтому здесь
    нельзя итерировать подписчиков (AC: "не внутри HTTP request/sync transaction")."""
    from .tasks import notify_product_available

    notify_product_available.delay(
        product_id=product_id,
        transition_id=transition_id,
        old_available=old_available,
        new_available=new_available,
        source=source,
    )


events.order_created.connect(_on_order_created, dispatch_uid="integration_max_order_created")
events.order_paid.connect(_on_order_paid, dispatch_uid="integration_max_order_paid")
events.order_status_changed.connect(
    _on_order_status_changed, dispatch_uid="integration_max_order_status_changed"
)
events.payment_refunded.connect(
    _on_payment_refunded, dispatch_uid="integration_max_payment_refunded"
)
events.product_stock_became_available.connect(
    _on_product_stock_became_available, dispatch_uid="integration_max_product_stock_available"
)
