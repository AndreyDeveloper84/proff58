"""Подписчики событий заявок. Сбой канала уведомления не валит создание заявки."""

from __future__ import annotations

import logging

logger = logging.getLogger("apps.leads")


def notify_new_inquiry(sender, inquiry_id, kind, product_id, **kwargs):
    """Реакция на product_inquiry_created: уведомить менеджеров.

    Пока — лог (канал email/Telegram подключим отдельной задачей). Исключения
    глушим: заявка уже сохранена, потеря уведомления не должна ломать ответ API.
    """
    try:
        logger.info(
            "Новая заявка #%s (%s) по товару %s", inquiry_id, kind, product_id
        )
    except Exception:  # noqa: BLE001 — уведомление не критично
        logger.exception("Сбой обработки product_inquiry_created")
