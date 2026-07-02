"""Celery tasks отправки уведомлений (transactional outbox, #431/M-08)."""

from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Строка, «зависшая» в SENDING дольше этого времени, считается отправленной с
# потерянным подтверждением (crash-after-send) → переводится в UNKNOWN (не resend).
_SENDING_STALE_SECONDS = 5 * 60


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_notification_task(self, log_id, **kwargs):
    """Отправить уведомление по строке outbox. Идемпотентно и crash-safe.

    Claim: QUEUED/FAILED → SENDING под select_for_update. Уже SENDING/SENT/UNKNOWN
    не переотправляем — защита от конкуренции и повторной отправки после падения
    воркера между отправкой и записью результата.
    """
    from .channels import max as max_channel
    from .models import NotificationChannel, NotificationLog, NotificationStatus

    with transaction.atomic():
        log = NotificationLog.objects.select_for_update().filter(pk=log_id).first()
        if log is None:
            return
        if log.status not in (NotificationStatus.QUEUED, NotificationStatus.FAILED):
            # SENDING/SENT/UNKNOWN — уже обрабатывается/обработана, не дублируем.
            return
        log.status = NotificationStatus.SENDING
        log.save(update_fields=["status", "updated_at"])

    try:
        if log.channel == NotificationChannel.MAX:
            max_channel.send_message(log.chat_id, log.text)
    except Exception as exc:
        NotificationLog.objects.filter(pk=log_id).update(
            status=NotificationStatus.FAILED,
            error_message=str(exc)[:500],
            updated_at=timezone.now(),
        )
        logger.error("Notification %s failed: event=%s, error=%s", log_id, log.event, exc)
        raise self.retry(exc=exc) from exc

    NotificationLog.objects.filter(pk=log_id).update(
        status=NotificationStatus.SENT, updated_at=timezone.now()
    )


@shared_task(name="apps.notifications.tasks.reconcile_stuck_notifications")
def reconcile_stuck_notifications() -> int:
    """Пометить давно «зависшие» в SENDING как UNKNOWN (crash-after-send).

    Не переотправляет (во избежание дублей) — только фиксирует неопределённость
    для ручной сверки. Возвращает число помеченных.
    """
    import datetime as _dt

    from .models import NotificationLog, NotificationStatus

    cutoff = timezone.now() - _dt.timedelta(seconds=_SENDING_STALE_SECONDS)
    return NotificationLog.objects.filter(
        status=NotificationStatus.SENDING, updated_at__lt=cutoff
    ).update(status=NotificationStatus.UNKNOWN, updated_at=timezone.now())
