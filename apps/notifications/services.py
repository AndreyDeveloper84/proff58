"""Единая точка отправки уведомлений.

Остальные модули (orders, payments и т.д.) НЕ зовут MAX или email напрямую —
только эту функцию. Ошибка отправки не блокирует вызывающий код.

    from apps.notifications.services import send
    send(user=user, event="order_paid", payload={"order_id": 42})
"""

from __future__ import annotations

import logging

from apps.core.features import is_enabled

from .channels import max as max_channel
from .models import NotificationChannel, NotificationLog, NotificationStatus

logger = logging.getLogger(__name__)

EVENT_TEMPLATES: dict[str, str] = {
    "order_created": "Заказ #{order_id} оформлен. Ожидайте подтверждения.",
    "order_paid": "Заказ #{order_id} оплачен! Мы начали сборку.",
    "order_status_changed": "Статус заказа #{order_id}: {new_status}.",
    "order_shipped": "Заказ #{order_id} передан в доставку.",
    "order_delivered": "Заказ #{order_id} доставлен. Спасибо за покупку!",
}


def send(
    *,
    user=None,
    chat_id: int | None = None,
    event: str,
    payload: dict | None = None,
    idempotency_key: str = "",
) -> None:
    """Отправить уведомление пользователю.

    Выбирает канал автоматически. Ошибка отправки логируется, но не
    пробрасывается — вызывающий код (checkout, status update) не блокируется.
    """
    payload = payload or {}
    resolved_chat_id = chat_id or _resolve_chat_id(user)

    if not (resolved_chat_id and is_enabled("max_chat") and max_channel.is_available()):
        _log(
            user=user,
            channel=NotificationChannel.MAX,
            event=event,
            status=NotificationStatus.SKIPPED,
            error="MAX канал недоступен или отключён",
            idempotency_key=idempotency_key,
        )
        return

    # #431 (M-08): claim строки outbox. Дедуп по непустому idempotency_key на уровне
    # БД (partial unique). Если строка уже есть — не ставим задачу повторно.
    text = _render_text(event, payload)
    user_id = getattr(user, "pk", None) if user else None
    log, created = _claim_outbox(
        user_id=user_id,
        chat_id=resolved_chat_id,
        event=event,
        text=text,
        idempotency_key=idempotency_key,
    )
    if not created:
        return

    from .tasks import send_notification_task

    send_notification_task.delay(log.id)


def _claim_outbox(*, user_id, chat_id, event, text, idempotency_key):
    """Создать строку outbox в статусе QUEUED. Дедуп по непустому ключу.

    Возвращает (log, created). created=False → такой ключ уже поставлен/отправлен.
    """
    defaults = {
        "channel": NotificationChannel.MAX,
        "event": event,
        "status": NotificationStatus.QUEUED,
        "chat_id": chat_id,
        "text": text,
        "user_id": user_id,
    }
    if idempotency_key:
        return NotificationLog.objects.get_or_create(
            idempotency_key=idempotency_key, defaults=defaults
        )
    return NotificationLog.objects.create(idempotency_key="", **defaults), True


def _render_text(event: str, payload: dict) -> str:
    template = EVENT_TEMPLATES.get(event)
    if template:
        try:
            return template.format(**payload)
        except KeyError:
            pass
    parts = [f"Событие: {event}"]
    for k, v in payload.items():
        parts.append(f"{k}: {v}")
    return "\n".join(parts)


def _resolve_chat_id(user) -> int | None:
    if user is None:
        return None
    return getattr(user, "max_chat_id", None)


def _log(
    *,
    user,
    channel: str,
    event: str,
    status: str,
    error: str = "",
    idempotency_key: str = "",
) -> None:
    try:
        NotificationLog.objects.create(
            user=user,
            channel=channel,
            event=event,
            status=status,
            error_message=error,
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.exception("Failed to write NotificationLog")
