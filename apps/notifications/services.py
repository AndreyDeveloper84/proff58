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
from .models import (
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationLog,
    NotificationStatus,
    UserNotificationPreference,
)

logger = logging.getLogger(__name__)

EVENT_TEMPLATES: dict[str, str] = {
    "order_created": "Заказ #{order_id} оформлен. Ожидайте подтверждения.",
    "order_paid": "Заказ #{order_id} оплачен! Мы начали сборку.",
    "order_status_changed": "Статус заказа #{order_id}: {new_status}.",
    "order_shipped": "Заказ #{order_id} передан в доставку.",
    "order_delivered": "Заказ #{order_id} доставлен. Спасибо за покупку!",
}

# #515: versioned template registry для user-facing intent (заголовок/категория).
# Версия — снимок в Notification.template_version на момент создания; смена
# текста здесь не переписывает историю уже созданных intent'ов.
NOTIFICATION_META: dict[str, dict] = {
    "order_created": {
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Заказ оформлен",
        "version": 1,
    },
    "order_paid": {
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Заказ оплачен",
        "version": 1,
    },
    "order_status_changed": {
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Статус заказа изменён",
        "version": 1,
    },
    "order_shipped": {
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Заказ в доставке",
        "version": 1,
    },
    "order_delivered": {
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Заказ доставлен",
        "version": 1,
    },
    "max_connected": {
        "category": NotificationCategory.ACCOUNT,
        "title": "MAX подключён",
        "version": 1,
    },
}
_DEFAULT_NOTIFICATION_META = {
    "category": NotificationCategory.ACCOUNT,
    "title": "Уведомление",
    "version": 1,
}

# Категория → поле preferences, которое её гасит. У ACCOUNT нет отдельного
# тумблера — только мастер-переключатель max_enabled.
_CATEGORY_PREFERENCE_FIELD = {
    NotificationCategory.ORDER_UPDATES: "order_updates_enabled",
    NotificationCategory.PRODUCT_AVAILABILITY: "product_availability_enabled",
    NotificationCategory.MARKETING: "marketing_enabled",
}


def send(
    *,
    user=None,
    chat_id: int | None = None,
    event: str,
    payload: dict | None = None,
    idempotency_key: str = "",
) -> NotificationLog | None:
    """Отправить уведомление пользователю.

    Выбирает канал автоматически. Ошибка отправки логируется, но не
    пробрасывается — вызывающий код (checkout, status update) не блокируется.
    Возвращает созданную/найденную строку outbox (для #515 — связать с
    user-facing Notification.delivery); существующие вызыватели, которые
    возврат игнорируют, не затронуты.
    """
    payload = payload or {}
    resolved_chat_id = chat_id or _resolve_chat_id(user)

    if not (resolved_chat_id and is_enabled("max_chat") and max_channel.is_available()):
        return _log(
            user=user,
            channel=NotificationChannel.MAX,
            event=event,
            status=NotificationStatus.SKIPPED,
            error="MAX канал недоступен или отключён",
            idempotency_key=idempotency_key,
        )

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
        return log

    from .tasks import send_notification_task

    send_notification_task.delay(log.id)
    return log


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
    # #514: единственный источник истины — apps.integration_max.services (владеет
    # MaxAccount) — notifications не читает чужую таблицу напрямую.
    from apps.integration_max.services import resolve_active_chat_id

    return resolve_active_chat_id(user)


def _log(
    *,
    user,
    channel: str,
    event: str,
    status: str,
    error: str = "",
    idempotency_key: str = "",
) -> NotificationLog | None:
    try:
        return NotificationLog.objects.create(
            user=user,
            channel=channel,
            event=event,
            status=status,
            error_message=error,
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.exception("Failed to write NotificationLog")
        return None


# ═══════════════════════════════════════════════════════════════════════
# #515 — notification domain: preferences, intent/history, policy
# ═══════════════════════════════════════════════════════════════════════


def get_or_create_preference(user) -> UserNotificationPreference:
    pref, _created = UserNotificationPreference.objects.get_or_create(user=user)
    return pref


def _policy_skip_reason(pref: UserNotificationPreference, category: str) -> str:
    """Пусто — доставку можно ставить. Иначе — explain-причина пропуска (#515 AC)."""
    if not pref.max_enabled:
        return "max_disabled"
    field = _CATEGORY_PREFERENCE_FIELD.get(category)
    if field and not getattr(pref, field):
        return f"category_disabled:{category}"
    return ""


def _claim_notification(
    *,
    user,
    event: str,
    category: str,
    title: str,
    body: str,
    data: dict,
    version: int,
    idempotency_key: str,
):
    """Создать intent-строку. Дедуп по непустому idempotency_key (как в _claim_outbox —
    ключ глобально уникален, не в лукапе, а в defaults, чтобы не разойтись со
    схемой UniqueConstraint на одном только idempotency_key)."""
    defaults = {
        "user": user,
        "event": event,
        "category": category,
        "title": title,
        "body": body,
        "data": data,
        "template_version": version,
    }
    if idempotency_key:
        return Notification.objects.get_or_create(
            idempotency_key=idempotency_key, defaults=defaults
        )
    return Notification.objects.create(idempotency_key="", **defaults), True


def create_notification(
    *,
    user,
    event: str,
    payload: dict | None = None,
    idempotency_key: str = "",
) -> Notification | None:
    """Единая точка входа notification domain (#515): intent → preference → delivery.

    1. Пишет user-facing `Notification` (историю) — идемпотентно по ключу, как
       и outbox в `send()`: повтор одного idempotency_key не создаёт второй intent.
    2. Проверяет `UserNotificationPreference` пользователя: категория/канал
       выключены → skip без внешней отправки, но с explain-причиной
       (`policy_skip_reason`) — не молча.
    3. Иначе ставит доставку через существующий `send()` и связывает
       `Notification.delivery` с созданной строкой outbox.

    user обязателен (в отличие от send()) — у intent/preferences нет смысла без
    владельца.
    """
    if user is None:
        return None
    payload = payload or {}
    meta = NOTIFICATION_META.get(event, _DEFAULT_NOTIFICATION_META)
    title = meta["title"]
    body = _render_text(event, payload)

    intent, created = _claim_notification(
        user=user,
        event=event,
        category=meta["category"],
        title=title,
        body=body,
        data=payload,
        version=meta["version"],
        idempotency_key=idempotency_key,
    )
    if not created:
        return intent

    pref = get_or_create_preference(user)
    skip_reason = _policy_skip_reason(pref, meta["category"])
    if skip_reason:
        intent.policy_skip_reason = skip_reason
        intent.save(update_fields=["policy_skip_reason"])
        return intent

    log = send(user=user, event=event, payload=payload, idempotency_key=idempotency_key)
    if log is not None:
        intent.delivery = log
        intent.save(update_fields=["delivery"])
    return intent
