"""Единая точка отправки уведомлений.

Остальные модули (orders, payments и т.д.) НЕ зовут MAX или email напрямую —
только эту функцию. Ошибка отправки не блокирует вызывающий код.

    from apps.notifications.services import send
    send(user=user, event="order_paid", payload={"order_number": "П-42"})
"""

from __future__ import annotations

import logging

from apps.core.features import is_enabled

from .channels import max as max_channel
from .models import (
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationErrorKind,
    NotificationLog,
    NotificationStatus,
    UserNotificationPreference,
)

logger = logging.getLogger(__name__)

# Единый реестр событий: template (MAX-текст) + category/title/version (intent,
# #515) — одной записью на event, а не двумя параллельными словарями. Раньше
# EVENT_TEMPLATES/NOTIFICATION_META велись раздельно и уже успели разойтись
# (max_connected был в одном, но не в другом — реальные уведомления уходили
# как debug-фолбэк "Событие: max_connected"); один реестр делает такое
# расхождение невозможным в принципе, а не только по соглашению.
#
# version — снимок в Notification.template_version на момент создания; смена
# текста здесь не переписывает историю уже созданных intent'ов.
# ready_note/tracking_note/price_note — receiver/task обязаны передавать их
# всегда (пустой строкой, если нечего добавить) — иначе .format() упадёт на
# KeyError-фолбэк.
NOTIFICATION_EVENTS: dict[str, dict] = {
    "order_created": {
        "template": "Заказ №{order_number} оформлен. Ожидайте подтверждения.",
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Заказ оформлен",
        "version": 1,
    },
    "order_confirmed": {
        "template": "Заказ №{order_number} подтверждён.",
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Заказ подтверждён",
        "version": 1,
    },
    "order_ready": {
        "template": "Заказ №{order_number} собран.{ready_note}",
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Заказ готов",
        "version": 1,
    },
    "order_shipped": {
        "template": "Заказ №{order_number} передан в доставку.{tracking_note}",
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Заказ в доставке",
        "version": 1,
    },
    "order_delivered": {
        "template": "Заказ №{order_number} доставлен. Спасибо за покупку!",
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Заказ доставлен",
        "version": 1,
    },
    "order_cancelled": {
        "template": "Заказ №{order_number} отменён.",
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Заказ отменён",
        "version": 1,
    },
    "order_paid": {
        "template": "Оплата заказа №{order_number} получена. Мы начали сборку.",
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Заказ оплачен",
        "version": 1,
    },
    "order_refunded": {
        "template": "Возврат по заказу №{order_number} выполнен.",
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Возврат выполнен",
        "version": 1,
    },
    "order_partially_refunded": {
        "template": "Оформлен частичный возврат по заказу №{order_number}.",
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Частичный возврат",
        "version": 1,
    },
    "order_tracking_connected": {
        # #520: разовое сообщение гостю сразу после выдачи OrderTrackingGrant —
        # текущий статус, без preferences/Notification-истории (гость без аккаунта).
        "template": "Отслеживание заказа №{order_number} подключено. Текущий статус: {status_note}.",
        "category": NotificationCategory.ORDER_UPDATES,
        "title": "Отслеживание подключено",
        "version": 1,
    },
    "max_connected": {
        "template": "Вы будете получать уведомления о заказах и поступлении товара в этом чате.",
        "category": NotificationCategory.ACCOUNT,
        "title": "MAX подключён",
        "version": 1,
    },
    "product_available": {
        "template": "«{product_name}» снова в наличии!{price_note}",
        "category": NotificationCategory.PRODUCT_AVAILABILITY,
        "title": "Товар в наличии",
        "version": 1,
    },
}
_DEFAULT_NOTIFICATION_EVENT = {
    "template": "",
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
    # chat_id=0 — валидный MAX id (см. resolve_active_chat_id в integration_max,
    # #521): is not None, не truthy-проверка, иначе такой чат никогда не получал
    # бы уведомлений ни явным chat_id, ни через резолв по user.
    resolved_chat_id = chat_id if chat_id is not None else _resolve_chat_id(user)

    if not (resolved_chat_id is not None and is_enabled("max_chat") and max_channel.is_available()):
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
    return enqueue(log)


# Ошибки транспорта очереди (брокер недоступен, обрыв соединения). Только они:
# в eager-режиме (dev/тесты) .delay() выполняет задачу синхронно, и её собственные
# исключения (Retry, ошибка провайдера) сюда попадать не должны — задача уже
# записала честный FAILED сама.
def _queue_transport_errors() -> tuple[type[BaseException], ...]:
    from kombu.exceptions import OperationalError

    return (OperationalError, ConnectionError, OSError)


def enqueue(log: NotificationLog) -> NotificationLog:
    """Поставить строку outbox в очередь. Недоступная очередь — не сбой заказа.

    Вызов идёт из on_commit-колбэков оформления заказа: исключение отсюда дало бы
    покупателю 500 при уже созданном заказе (DRF-2293). Поэтому сбой брокера
    превращается в строку `failed/retryable`, видимую в админке и метриках,
    с ручным повтором после восстановления.
    """
    from celery.exceptions import Retry

    from .tasks import send_notification_task

    try:
        send_notification_task.delay(log.id)
    except Retry:
        raise
    except _queue_transport_errors() as exc:
        NotificationLog.objects.filter(pk=log.pk).update(
            status=NotificationStatus.FAILED,
            error_kind=NotificationErrorKind.RETRYABLE,
            error_message=f"Очередь недоступна: {type(exc).__name__}"[:500],
        )
        log.refresh_from_db()
        logger.error("Notification %s not enqueued: event=%s, queue unavailable", log.pk, log.event)
    return log


def _claim_outbox(
    *,
    user_id,
    chat_id,
    event,
    text,
    idempotency_key,
    channel=NotificationChannel.MAX,
    subject="",
    recipients="",
):
    """Создать строку outbox в статусе QUEUED. Дедуп по непустому ключу.

    Возвращает (log, created). created=False → такой ключ уже поставлен/отправлен.
    """
    defaults = {
        "channel": channel,
        "event": event,
        "status": NotificationStatus.QUEUED,
        "chat_id": chat_id,
        "text": text,
        "user_id": user_id,
        "subject": subject,
        "recipients": recipients,
    }
    if idempotency_key:
        return NotificationLog.objects.get_or_create(
            idempotency_key=idempotency_key, defaults=defaults
        )
    return NotificationLog.objects.create(idempotency_key="", **defaults), True


def _render_text(event: str, payload: dict) -> str:
    template = NOTIFICATION_EVENTS.get(event, {}).get("template")
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
# DRF-2296 — письма сотрудникам о новых заказах и заявках
# ═══════════════════════════════════════════════════════════════════════

# Служебные события: тема + текст письма. Получатели — settings.STAFF_NOTIFICATION_EMAILS,
# снимок адресов пишется в строку outbox. Никаких токенов и секретов в payload:
# только то, что сотрудник и так видит в админке; ссылка ведёт на страницу,
# требующую входа.
STAFF_EVENTS: dict[str, dict] = {
    "staff_order_created": {
        "subject": "Новый заказ №{order_number} — {total} {currency}",
        "template": (
            "Новый заказ №{order_number}\n"
            "Оформлен: {created_at}\n"
            "Покупатель: {customer}\n"
            "Телефон: {customer_phone}\n"
            "Сумма: {total} {currency}, позиций: {items_count}\n"
            "Получение: {delivery}\n"
            "Оплата: {payment}\n"
            "\n"
            "Открыть в админке (нужен вход сотрудника):\n"
            "{admin_url}\n"
        ),
        "version": 1,
    },
    "staff_inquiry_created": {
        "subject": "Новая заявка: {kind} — {product}",
        "template": (
            "Новая заявка #{inquiry_id}: {kind}\n"
            "Оставлена: {created_at}\n"
            "Товар: {product}\n"
            "Имя: {name}\n"
            "Телефон: {phone}\n"
            "Сообщение: {message}\n"
            "\n"
            "Открыть в админке (нужен вход сотрудника):\n"
            "{admin_url}\n"
        ),
        "version": 1,
    },
}


def staff_recipients() -> list[str]:
    from django.conf import settings

    return list(getattr(settings, "STAFF_NOTIFICATION_EMAILS", []) or [])


def admin_url(path: str) -> str:
    """Абсолютная ссылка в админку по SITE_URL; без SITE_URL — относительный путь
    (в проде SITE_URL обязателен при заданных получателях, см. prod.py)."""
    from django.conf import settings

    base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    if not base:
        logger.warning("SITE_URL пуст — ссылка в письме сотрудникам будет относительной")
    return f"{base}{path}"


def notify_staff(*, event: str, payload: dict, idempotency_key: str) -> NotificationLog | None:
    """Поставить письмо сотрудникам в outbox. Не бросает исключений наружу.

    Получатели не настроены → строка SKIPPED с причиной (так на staging: письма
    реальным людям не уходят, но факт в журнале есть). Повтор того же
    idempotency_key не создаёт второй строки и второго письма. Доставка — та же
    Celery-задача, ретраи и ручной повтор из админки, что у MAX.
    """
    meta = STAFF_EVENTS[event]
    recipients = staff_recipients()
    if not recipients:
        return _log(
            user=None,
            channel=NotificationChannel.EMAIL,
            event=event,
            status=NotificationStatus.SKIPPED,
            error="Получатели не настроены (STAFF_NOTIFICATION_EMAILS)",
            idempotency_key=idempotency_key,
        )
    try:
        subject = meta["subject"].format(**payload)
        text = meta["template"].format(**payload)
    except KeyError:
        logger.exception("Неполный payload для %s", event)
        subject, text = f"[{event}]", _render_text(event, payload)

    log, created = _claim_outbox(
        user_id=None,
        chat_id=None,
        event=event,
        text=text,
        idempotency_key=idempotency_key,
        channel=NotificationChannel.EMAIL,
        subject=subject[:255],
        recipients=", ".join(recipients),
    )
    if not created:
        return log
    return enqueue(log)


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
    meta = NOTIFICATION_EVENTS.get(event, _DEFAULT_NOTIFICATION_EVENT)
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
