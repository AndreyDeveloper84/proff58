"""Отправка уведомлений о заказах в MAX (#48).

Шаблоны сообщений по событиям жизненного цикла заказа.
Ретраи — через Celery shared_task.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Шаблоны сообщений
# ---------------------------------------------------------------------------
MESSAGE_TEMPLATES: dict[str, str] = {
    "order_created": "Ваш заказ {order_number} успешно оформлен. Мы начали его обработку.",
    "order_paid": "Оплата по заказу {order_number} подтверждена. Спасибо!",
    "order_shipped": "Заказ {order_number} передан в доставку.{extra}",
    "order_completed": "Заказ {order_number} выполнен. Благодарим за покупку!",
}


# ---------------------------------------------------------------------------
# Celery-задача с retry
# ---------------------------------------------------------------------------
@shared_task(
    bind=True,
    autoretry_for=(urllib.error.URLError, OSError),
    retry_backoff=30,
    retry_backoff_max=600,
    max_retries=5,
    acks_late=True,
)
def send_order_notification_task(
    self,
    chat_id: int,
    event: str,
    order_number: str,
    extra: str = "",
) -> dict:
    """Celery-обёртка для send_order_notification с авто-ретраем."""
    return send_order_notification(chat_id, event, order_number, extra)


# ---------------------------------------------------------------------------
# Основная функция отправки
# ---------------------------------------------------------------------------
def send_order_notification(
    chat_id: int,
    event: str,
    order_number: str,
    extra: str = "",
) -> dict:
    """Отправить уведомление о заказе в MAX-чат пользователя.

    Args:
        chat_id: MAX chat ID получателя.
        event: Тип события (order_created, order_paid, order_shipped, order_completed).
        order_number: Номер заказа.
        extra: Дополнительная информация (напр. трек-номер).

    Returns:
        Словарь с ответом API.

    Raises:
        urllib.error.URLError: при сетевых ошибках (Celery retry подхватит).
        ValueError: если шаблон для события не найден.
    """
    template = MESSAGE_TEMPLATES.get(event)
    if not template:
        raise ValueError(f"Неизвестное событие: {event}")

    text = template.format(order_number=order_number, extra=extra)

    token = settings.MAX_BOT_TOKEN
    api_url = settings.MAX_BOT_API_URL
    url = f"{api_url}/messages"

    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        logger.info(
            "MAX notification sent: event=%s order=%s chat_id=%s",
            event,
            order_number,
            chat_id,
        )
        return json.loads(body) if body else {}
