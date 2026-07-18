"""Celery tasks отправки уведомлений (transactional outbox, #431/M-08)."""

from __future__ import annotations

import logging
import random

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Строка, «зависшая» в SENDING дольше этого времени, считается отправленной с
# потерянным подтверждением (crash-after-send) → переводится в UNKNOWN (не resend).
_SENDING_STALE_SECONDS = 5 * 60

# #521: bounded backoff+jitter для retryable-ошибок без Retry-After от провайдера.
_BACKOFF_BASE_SECONDS = 30
_BACKOFF_MAX_SECONDS = 300
_BACKOFF_JITTER_SECONDS = 10


def _backoff_countdown(retries: int) -> int:
    """Экспоненциальный backoff с джиттером, ограниченный сверху (#521 AC:
    "429/5xx используют bounded backoff+jitter")."""
    base = min(_BACKOFF_BASE_SECONDS * (2**retries), _BACKOFF_MAX_SECONDS)
    return base + random.randint(0, _BACKOFF_JITTER_SECONDS)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_notification_task(self, log_id, **kwargs):
    """Отправить уведомление по строке outbox. Идемпотентно и crash-safe.

    Claim: QUEUED/FAILED → SENDING под select_for_update. Уже SENDING/SENT/UNKNOWN
    не переотправляем — защита от конкуренции и повторной отправки после падения
    воркера между отправкой и записью результата.

    #521: провайдерская ошибка классифицирована (channels/max.py) — permanent
    (4xx, кроме 429) не ретраится вообще (записывается FAILED сразу, retry
    осмыслен только вручную из админки после исправления причины); retryable
    (429/5xx/сеть) ретраится с Retry-After провайдера либо bounded backoff+jitter.
    """
    from .channels import max as max_channel
    from .channels.max import MaxPermanentError, MaxProviderError
    from .models import (
        NotificationChannel,
        NotificationErrorKind,
        NotificationLog,
        NotificationStatus,
    )

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
    except MaxProviderError as exc:
        is_permanent = isinstance(exc, MaxPermanentError)
        NotificationLog.objects.filter(pk=log_id).update(
            status=NotificationStatus.FAILED,
            error_message=str(exc)[:500],
            error_kind=(
                NotificationErrorKind.PERMANENT if is_permanent else NotificationErrorKind.RETRYABLE
            ),
            updated_at=timezone.now(),
        )
        # #521: без chat_id/текста сообщения в логе — только log_id (delivery)
        # и событие, этого достаточно, чтобы найти строку и провайдерскую причину.
        logger.error(
            "Notification %s failed: event=%s, kind=%s",
            log_id,
            log.event,
            "permanent" if is_permanent else "retryable",
        )
        if is_permanent:
            return  # AC #521: "permanent 4xx не ретраятся бесконечно" — вообще не ретраим
        countdown = (
            exc.retry_after
            if exc.retry_after is not None
            else _backoff_countdown(self.request.retries)
        )
        raise self.retry(exc=exc, countdown=countdown) from exc
    except Exception as exc:
        # Неклассифицированная ошибка (напр. MAX_BOT_TOKEN не задан на старте
        # — MaxPermanentError уже покрывает это; сюда попадают только баги
        # channels/max.py) — консервативно ретраим как раньше, bounded backoff.
        NotificationLog.objects.filter(pk=log_id).update(
            status=NotificationStatus.FAILED,
            error_message=str(exc)[:500],
            updated_at=timezone.now(),
        )
        logger.error("Notification %s failed: event=%s, kind=unclassified", log_id, log.event)
        raise self.retry(exc=exc, countdown=_backoff_countdown(self.request.retries)) from exc

    NotificationLog.objects.filter(pk=log_id).update(
        status=NotificationStatus.SENT, error_kind="", updated_at=timezone.now()
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


# #521: retention policy — outbox (NotificationLog: text/chat_id) хранится
# короче, чем user-facing история (Notification: без chat_id, только title/
# body snapshot). Дефолты — настройки, не хардкод, чтобы менять без деплоя кода.
_DEFAULT_LOG_RETENTION_DAYS = 90
_DEFAULT_HISTORY_RETENTION_DAYS = 365


@shared_task(name="apps.notifications.tasks.cleanup_old_notification_logs")
def cleanup_old_notification_logs() -> int:
    """Удалить строки outbox (NotificationLog) в терминальном статусе старше
    NOTIFICATION_LOG_RETENTION_DAYS (#521). QUEUED/SENDING не трогает — только
    завершённые (sent/failed/skipped/unknown); Notification.delivery — SET_NULL,
    удаление лога не рвёт историю пользователя."""
    import datetime as _dt

    from django.conf import settings

    from .models import NotificationLog, NotificationStatus

    days = getattr(settings, "NOTIFICATION_LOG_RETENTION_DAYS", _DEFAULT_LOG_RETENTION_DAYS)
    cutoff = timezone.now() - _dt.timedelta(days=days)
    qs = NotificationLog.objects.filter(
        status__in=(
            NotificationStatus.SENT,
            NotificationStatus.FAILED,
            NotificationStatus.SKIPPED,
            NotificationStatus.UNKNOWN,
        ),
        created_at__lt=cutoff,
    )
    count, _ = qs.delete()
    return count


@shared_task(name="apps.notifications.tasks.cleanup_old_notifications")
def cleanup_old_notifications() -> int:
    """Удалить user-facing историю (Notification) старше
    NOTIFICATION_RETENTION_DAYS (#521). Дольше живёт, чем outbox-лог, — это
    видимая пользователю история в ЛК, не техническая отправка."""
    import datetime as _dt

    from django.conf import settings

    from .models import Notification

    days = getattr(settings, "NOTIFICATION_RETENTION_DAYS", _DEFAULT_HISTORY_RETENTION_DAYS)
    cutoff = timezone.now() - _dt.timedelta(days=days)
    count, _ = Notification.objects.filter(created_at__lt=cutoff).delete()
    return count
