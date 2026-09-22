"""Каналы доставки уведомлений и общая классификация их ошибок.

Задача отправки (``tasks.send_notification_task``) знает только базовые классы:
``RetryableChannelError`` — повтор осмыслен (сеть, таймаут, 429/5xx, временный
отказ SMTP), ``PermanentChannelError`` — запрос сам по себе некорректен, повтор
бессмыслен (4xx, отвергнутый получатель/отправитель, неверные учётные данные).
Конкретные каналы (``max``, ``email``) наследуют от них.
"""

from __future__ import annotations


class ChannelError(Exception):
    """Базовая ошибка канала. ``retry_after`` — секунды до повтора, если
    провайдер их прислал (Retry-After у 429)."""

    def __init__(self, message: str, *, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class RetryableChannelError(ChannelError):
    """Временная проблема — повтор осмыслен."""


class PermanentChannelError(ChannelError):
    """Постоянная проблема — повтор бессмыслен, нужен разбор человеком."""
