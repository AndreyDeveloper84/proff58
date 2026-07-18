"""Тесты retry-политики send_notification_task (#521): permanent не ретраится,
retryable использует Retry-After провайдера либо bounded backoff+jitter."""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from .channels.max import MaxPermanentError, MaxRetryableError
from .models import NotificationChannel, NotificationErrorKind, NotificationLog, NotificationStatus
from .tasks import _backoff_countdown, send_notification_task

User = get_user_model()

MAX_SETTINGS = {"MAX_BOT_TOKEN": "test-token", "MAX_BOT_API_URL": "https://test.max.ru"}


@pytest.fixture
def log(db):
    return NotificationLog.objects.create(
        channel=NotificationChannel.MAX,
        event="order_paid",
        status=NotificationStatus.QUEUED,
        chat_id=123,
        text="x",
    )


@pytest.mark.django_db
@override_settings(**MAX_SETTINGS, CELERY_TASK_EAGER_PROPAGATES=False)
@mock.patch(
    "apps.notifications.channels.max.send_message", side_effect=MaxPermanentError("HTTP 400")
)
def test_permanent_error_does_not_retry(mock_send, log):
    send_notification_task(log.pk)

    mock_send.assert_called_once()  # ни одной повторной попытки
    log.refresh_from_db()
    assert log.status == NotificationStatus.FAILED
    assert log.error_kind == NotificationErrorKind.PERMANENT


@pytest.mark.django_db
@override_settings(**MAX_SETTINGS)
def test_retryable_error_sets_error_kind_and_uses_retry_after(log):
    err = MaxRetryableError("HTTP 429", retry_after=15)
    with mock.patch("apps.notifications.channels.max.send_message", side_effect=err):
        with mock.patch.object(
            send_notification_task, "retry", side_effect=Exception("stop-here")
        ) as mock_retry:
            with pytest.raises(Exception, match="stop-here"):
                send_notification_task(log.pk)

    assert mock_retry.call_args.kwargs["countdown"] == 15
    log.refresh_from_db()
    assert log.status == NotificationStatus.FAILED
    assert log.error_kind == NotificationErrorKind.RETRYABLE


@pytest.mark.django_db
@override_settings(**MAX_SETTINGS)
def test_retryable_error_without_retry_after_uses_bounded_backoff(log):
    err = MaxRetryableError("HTTP 503")  # без Retry-After
    with mock.patch("apps.notifications.channels.max.send_message", side_effect=err):
        with mock.patch.object(
            send_notification_task, "retry", side_effect=Exception("stop-here")
        ) as mock_retry:
            with pytest.raises(Exception, match="stop-here"):
                send_notification_task(log.pk)

    countdown = mock_retry.call_args.kwargs["countdown"]
    assert 30 <= countdown <= 40  # база 30 + джиттер до 10, retries=0


def test_backoff_countdown_is_bounded_and_grows_with_retries():
    assert 30 <= _backoff_countdown(0) <= 40
    assert 60 <= _backoff_countdown(1) <= 70
    assert _backoff_countdown(10) <= 310  # не улетает за _BACKOFF_MAX_SECONDS + джиттер


@pytest.mark.django_db
@override_settings(**MAX_SETTINGS)
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_success_clears_error_kind(mock_send, log):
    log.status = NotificationStatus.FAILED
    log.error_kind = NotificationErrorKind.RETRYABLE
    log.save(update_fields=["status", "error_kind"])
    log.status = NotificationStatus.QUEUED
    log.save(update_fields=["status"])

    send_notification_task(log.pk)

    log.refresh_from_db()
    assert log.status == NotificationStatus.SENT
    assert log.error_kind == ""


@pytest.mark.django_db
@override_settings(**MAX_SETTINGS, CELERY_TASK_EAGER_PROPAGATES=False)
def test_failure_log_does_not_contain_chat_id_or_text(caplog, log):
    """#521 AC: обычные логи — без chat_id/текста сообщения. log_id (delivery id)
    — не PII, допустим и достаточен, чтобы найти строку в БД."""
    distinctive_chat_id = 998877665
    log.chat_id = distinctive_chat_id
    log.text = "секретный текст сообщения"
    log.save(update_fields=["chat_id", "text"])

    with mock.patch(
        "apps.notifications.channels.max.send_message", side_effect=MaxPermanentError("HTTP 400")
    ):
        send_notification_task(log.pk)

    for record in caplog.records:
        message = record.getMessage()
        assert str(distinctive_chat_id) not in message
        assert "секретный текст" not in message
