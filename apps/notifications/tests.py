"""Тесты notification service (#61)."""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.core.models import SiteSettings

from .models import NotificationChannel, NotificationLog, NotificationStatus
from .services import EVENT_TEMPLATES, _render_text, send

User = get_user_model()

MAX_SETTINGS = {
    "MAX_BOT_TOKEN": "test-token",
    "MAX_BOT_API_URL": "https://test.max.ru",
}


@pytest.fixture
def user(db):
    u = User.objects.create_user(phone="+79001234567", password="pass")
    u.max_chat_id = 12345
    u.save()
    return u


@pytest.fixture
def _enable_max(db):
    s = SiteSettings.get_solo()
    s.max_chat_enabled = True
    s.save()


# ═══════════════════════════════════════════════════════════════════════
# 1. МОДЕЛЬ NotificationLog
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_notification_log_creation(user):
    log = NotificationLog.objects.create(
        user=user,
        channel=NotificationChannel.MAX,
        event="order_paid",
        status=NotificationStatus.SENT,
    )
    assert log.created_at is not None
    assert str(log) == "order_paid → max [sent]"


@pytest.mark.django_db
def test_notification_log_without_user():
    log = NotificationLog.objects.create(
        channel=NotificationChannel.MAX,
        event="test_event",
        status=NotificationStatus.SKIPPED,
    )
    assert log.user is None


# ═══════════════════════════════════════════════════════════════════════
# 2. RENDER TEXT
# ═══════════════════════════════════════════════════════════════════════


def test_render_known_event():
    text = _render_text("order_paid", {"order_id": 42})
    assert "42" in text
    assert "оплачен" in text


def test_render_unknown_event():
    text = _render_text("custom_event", {"foo": "bar"})
    assert "custom_event" in text
    assert "bar" in text


def test_render_missing_payload_key():
    text = _render_text("order_paid", {})
    assert "order_paid" in text


# ═══════════════════════════════════════════════════════════════════════
# 3. SEND — успех
# ═══════════════════════════════════════════════════════════════════════


@override_settings(**MAX_SETTINGS)
@pytest.mark.django_db
@pytest.mark.usefixtures("_enable_max")
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_send_success(mock_max, user):
    send(user=user, event="order_paid", payload={"order_id": 1})
    mock_max.assert_called_once_with(12345, mock.ANY)
    log = NotificationLog.objects.latest("created_at")
    assert log.status == NotificationStatus.SENT
    assert log.event == "order_paid"
    assert log.channel == NotificationChannel.MAX
    assert log.user == user


# ═══════════════════════════════════════════════════════════════════════
# 4. SEND — канал выключен
# ═══════════════════════════════════════════════════════════════════════


@override_settings(**MAX_SETTINGS)
@pytest.mark.django_db
@mock.patch("apps.notifications.channels.max.send_message")
def test_send_channel_disabled(mock_max, user):
    """max_chat feature flag выключен → уведомление пропущено."""
    s = SiteSettings.get_solo()
    s.max_chat_enabled = False
    s.save()
    send(user=user, event="order_created", payload={"order_id": 2})
    mock_max.assert_not_called()
    log = NotificationLog.objects.latest("created_at")
    assert log.status == NotificationStatus.SKIPPED


# ═══════════════════════════════════════════════════════════════════════
# 5. SEND — ошибка канала не блокирует
# ═══════════════════════════════════════════════════════════════════════


@override_settings(**MAX_SETTINGS, CELERY_TASK_EAGER_PROPAGATES=False)
@pytest.mark.django_db
@pytest.mark.usefixtures("_enable_max")
@mock.patch(
    "apps.notifications.channels.max.send_message",
    side_effect=RuntimeError("MAX API down"),
)
def test_send_failure_does_not_raise(mock_max, user):
    send(user=user, event="order_shipped", payload={"order_id": 3})
    log = NotificationLog.objects.latest("created_at")
    assert log.status == NotificationStatus.FAILED
    assert "MAX API down" in log.error_message


# ═══════════════════════════════════════════════════════════════════════
# 6. SEND — идемпотентность
# ═══════════════════════════════════════════════════════════════════════


@override_settings(**MAX_SETTINGS)
@pytest.mark.django_db
@pytest.mark.usefixtures("_enable_max")
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_send_idempotent(mock_max, user):
    send(user=user, event="order_paid", payload={"order_id": 4}, idempotency_key="pay-4")
    send(user=user, event="order_paid", payload={"order_id": 4}, idempotency_key="pay-4")
    assert mock_max.call_count == 1
    assert NotificationLog.objects.filter(idempotency_key="pay-4").count() == 1


# ═══════════════════════════════════════════════════════════════════════
# 7. SEND — chat_id напрямую
# ═══════════════════════════════════════════════════════════════════════


@override_settings(**MAX_SETTINGS)
@pytest.mark.django_db
@pytest.mark.usefixtures("_enable_max")
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_send_with_direct_chat_id(mock_max):
    send(chat_id=99999, event="test_event", payload={"x": 1})
    mock_max.assert_called_once_with(99999, mock.ANY)
    log = NotificationLog.objects.latest("created_at")
    assert log.status == NotificationStatus.SENT
    assert log.user is None


# ═══════════════════════════════════════════════════════════════════════
# 8. SEND — нет chat_id
# ═══════════════════════════════════════════════════════════════════════


@override_settings(**MAX_SETTINGS)
@pytest.mark.django_db
@pytest.mark.usefixtures("_enable_max")
@mock.patch("apps.notifications.channels.max.send_message")
def test_send_no_chat_id_skips(mock_max):
    user_no_max = User.objects.create_user(phone="+79009999999", password="pass")
    send(user=user_no_max, event="order_paid", payload={"order_id": 5})
    mock_max.assert_not_called()
    log = NotificationLog.objects.latest("created_at")
    assert log.status == NotificationStatus.SKIPPED


# ═══════════════════════════════════════════════════════════════════════
# 9. SEND — нет секретов в логе
# ═══════════════════════════════════════════════════════════════════════


@override_settings(**MAX_SETTINGS, CELERY_TASK_EAGER_PROPAGATES=False)
@pytest.mark.django_db
@pytest.mark.usefixtures("_enable_max")
@mock.patch(
    "apps.notifications.channels.max.send_message",
    side_effect=RuntimeError("token: test-token leaked"),
)
def test_error_log_no_secrets(mock_max, user):
    send(user=user, event="test", payload={})
    log = NotificationLog.objects.latest("created_at")
    assert log.error_message
    assert log.user_id == user.pk
    assert "79001234567" not in log.error_message


# ═══════════════════════════════════════════════════════════════════════
# 10. TEMPLATES
# ═══════════════════════════════════════════════════════════════════════


def test_all_templates_have_placeholders():
    for event, tmpl in EVENT_TEMPLATES.items():
        assert "{" in tmpl, f"Template for {event} has no placeholders"


# ═══════════════════════════════════════════════════════════════════════
# 11. M-08 — outbox идемпотентность / crash-safety
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_partial_unique_constraint_on_idempotency_key():
    """Непустой ключ уникален; пустой — можно много раз."""
    from django.db import IntegrityError, transaction

    NotificationLog.objects.create(
        channel=NotificationChannel.MAX,
        event="e",
        status=NotificationStatus.QUEUED,
        idempotency_key="k1",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        NotificationLog.objects.create(
            channel=NotificationChannel.MAX,
            event="e",
            status=NotificationStatus.QUEUED,
            idempotency_key="k1",
        )
    # Пустые ключи не конфликтуют.
    NotificationLog.objects.create(
        channel=NotificationChannel.MAX, event="e", status=NotificationStatus.SKIPPED
    )
    NotificationLog.objects.create(
        channel=NotificationChannel.MAX, event="e", status=NotificationStatus.SKIPPED
    )


@pytest.mark.django_db
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_task_does_not_resend_when_already_sending(mock_max):
    """crash-after-send / конкуренция: строка в SENDING не переотправляется."""
    from .tasks import send_notification_task

    log = NotificationLog.objects.create(
        channel=NotificationChannel.MAX,
        event="order_paid",
        status=NotificationStatus.SENDING,
        chat_id=123,
        text="x",
    )
    send_notification_task(log.id)
    mock_max.assert_not_called()
    log.refresh_from_db()
    assert log.status == NotificationStatus.SENDING


@pytest.mark.django_db
def test_reconcile_marks_stale_sending_as_unknown():
    from datetime import timedelta

    from django.utils import timezone

    from .models import NotificationLog, NotificationStatus
    from .tasks import reconcile_stuck_notifications

    log = NotificationLog.objects.create(
        channel=NotificationChannel.MAX,
        event="order_paid",
        status=NotificationStatus.SENDING,
        chat_id=1,
        text="x",
    )
    # Состарить updated_at за порог.
    NotificationLog.objects.filter(pk=log.pk).update(updated_at=timezone.now() - timedelta(hours=1))
    assert reconcile_stuck_notifications() == 1
    log.refresh_from_db()
    assert log.status == NotificationStatus.UNKNOWN
