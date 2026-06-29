"""Celery tasks для отправки уведомлений в фоне."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_notification_task(
    self, *, channel, chat_id, text, user_id=None, event="", idempotency_key="", **kwargs
):
    """Отправить уведомление в фоне. Ретраи при ошибке канала."""
    from .channels import max as max_channel
    from .models import NotificationChannel, NotificationLog, NotificationStatus

    try:
        if channel == NotificationChannel.MAX:
            max_channel.send_message(chat_id, text, **kwargs)

        NotificationLog.objects.create(
            user_id=user_id,
            channel=channel,
            event=event,
            status=NotificationStatus.SENT,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        logger.error("Notification task failed: event=%s, error=%s", event, exc)
        NotificationLog.objects.create(
            user_id=user_id,
            channel=channel,
            event=event,
            status=NotificationStatus.FAILED,
            error_message=str(exc)[:500],
            idempotency_key=idempotency_key,
        )
        raise self.retry(exc=exc) from exc
