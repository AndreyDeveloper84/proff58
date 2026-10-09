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
    # chat_id=0 — валидный id (см. resolve_active_chat_id, #521): is not None,
    # не truthy-проверка — иначе такой грант молча никогда не уведомлялся бы.
    if chat_id is None:
        return

    from apps.notifications.services import send

    send(user=None, chat_id=chat_id, event=event, payload=payload, idempotency_key=idempotency_key)


def _notify(order, user, event: str, payload: dict, idempotency_key: str) -> None:
    """Маршрутизация уведомления по заказу: гость (OrderTrackingGrant, #520) vs
    зарегистрированный пользователь (create_notification, #514/#515). Общая
    точка для всех receiver'ов ниже — без копипасты этой развилки 4 раза."""
    if user is None:
        _notify_guest_tracking(order, event, payload, idempotency_key)
        return
    from apps.notifications.services import create_notification

    create_notification(user=user, event=event, payload=payload, idempotency_key=idempotency_key)


def _on_order_created(sender, order_id, **kwargs):
    order, user = _get_order_user(order_id)
    if not order:
        return
    _notify(
        order,
        user,
        "order_created",
        {"order_number": order.order_number},
        f"order-created-{order_id}",
    )


def _on_order_paid(sender, order_id, **kwargs):
    order, user = _get_order_user(order_id)
    if not order:
        return
    _notify(
        order, user, "order_paid", {"order_number": order.order_number}, f"order-paid-{order_id}"
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

    _notify(order, user, event, payload, f"order-status-{order_id}-{new_status}")


def _on_payment_refunded(sender, payment_id, order_id, refund_id, amount, is_full, **kwargs):
    order, user = _get_order_user(order_id)
    if not order:
        return
    event = "order_refunded" if is_full else "order_partially_refunded"
    # ADR-0009: refund_id — конкретная операция возврата, а не order_id — несколько
    # частичных возвратов по заказу это разные реальные события.
    _notify(
        order,
        user,
        event,
        {"order_number": order.order_number},
        f"order-refunded-{order_id}-{refund_id}",
    )


def _on_product_stock_became_available(
    sender, product_id, old_available, new_available, source, transition_id, **kwargs
):
    """#518 (ADR-0010): только ставит fan-out в очередь — сам обработчик
    выполняется синхронно после commit импорта/HTTP-запроса 1С, поэтому здесь
    нельзя итерировать подписчиков (AC: "не внутри HTTP request/sync transaction")."""
    from .tasks import notify_product_available

    try:
        notify_product_available.delay(
            product_id=product_id,
            transition_id=transition_id,
            old_available=old_available,
            new_available=new_available,
            source=source,
        )
    except Exception:  # noqa: BLE001 — путь stocks/update от 1С не должен падать 500
        logger.exception("Fan-out product_available не поставлен: очередь недоступна")


events.order_created.connect(_on_order_created, dispatch_uid="integration_max_order_created")
events.order_paid.connect(_on_order_paid, dispatch_uid="integration_max_order_paid")
events.order_status_changed.connect(
    _on_order_status_changed, dispatch_uid="integration_max_order_status_changed"
)
events.payment_refunded.connect(
    _on_payment_refunded, dispatch_uid="integration_max_payment_refunded"
)


def _on_user_deleted(sender, user_id=None, **kwargs):
    """Remove/anonymize MAX-owned identifiers after account anonymization."""
    if user_id is None:
        return

    import secrets

    from django.db import IntegrityError
    from django.db.models import Q

    from apps.catalog.availability_subscriptions import ProductAvailabilitySubscription

    from .models import MaxAccount, MaxAuthAttempt, OrderTrackingGrant

    acct = MaxAccount.objects.filter(user_id=user_id).first()
    old_max_user_id = acct.max_user_id if acct is not None else None

    # Auth attempts are short-lived operational metadata and have no reason to
    # survive deletion of the owning account/provider identity.
    attempts = MaxAuthAttempt.objects.filter(user_id=user_id)
    if old_max_user_id is not None:
        attempts = MaxAuthAttempt.objects.filter(
            Q(user_id=user_id) | Q(max_user_id=old_max_user_id)
        )
    attempts.delete()

    # Guest tracking grants can also carry the old MAX identity.
    if old_max_user_id is not None:
        OrderTrackingGrant.objects.filter(max_user_id=old_max_user_id).delete()

    ProductAvailabilitySubscription.objects.filter(user_id=user_id).delete()

    if acct is None:
        return

    # Keep a technical tombstone row, but replace the provider identity with a
    # random negative surrogate (MAX IDs are external positive identifiers).
    for _ in range(5):
        surrogate = -(secrets.randbelow(2**62 - 1) + 1)
        try:
            MaxAccount.objects.filter(pk=acct.pk).update(
                max_user_id=surrogate,
                chat_id=None,
                phone="",
                first_name="",
                last_name="",
                username="",
                phone_verified_at=None,
                last_login_at=None,
                is_active=False,
            )
            break
        except IntegrityError:
            continue
    else:
        # Fail closed: deleting the row is safer than retaining the provider ID.
        MaxAccount.objects.filter(pk=acct.pk).delete()


events.product_stock_became_available.connect(
    _on_product_stock_became_available, dispatch_uid="integration_max_product_stock_available"
)
events.user_deleted.connect(
    _on_user_deleted, dispatch_uid="integration_max_user_deleted"
)
