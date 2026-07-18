"""Тесты retention/cleanup задач (#521)."""

from __future__ import annotations

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import (
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationLog,
    NotificationStatus,
)
from .tasks import cleanup_old_notification_logs, cleanup_old_notifications

User = get_user_model()


def _age(obj, days: int, field: str = "created_at") -> None:
    obj.__class__.objects.filter(pk=obj.pk).update(
        **{field: timezone.now() - datetime.timedelta(days=days)}
    )


@pytest.mark.django_db
def test_cleanup_logs_removes_only_old_terminal_rows(settings):
    settings.NOTIFICATION_LOG_RETENTION_DAYS = 90

    old_sent = NotificationLog.objects.create(
        channel=NotificationChannel.MAX, event="e", status=NotificationStatus.SENT
    )
    _age(old_sent, 91)
    recent_sent = NotificationLog.objects.create(
        channel=NotificationChannel.MAX, event="e", status=NotificationStatus.SENT
    )
    old_queued = NotificationLog.objects.create(
        channel=NotificationChannel.MAX, event="e", status=NotificationStatus.QUEUED
    )
    _age(old_queued, 91)  # старая, но не terminal — не трогаем

    deleted = cleanup_old_notification_logs()

    assert deleted == 1
    assert not NotificationLog.objects.filter(pk=old_sent.pk).exists()
    assert NotificationLog.objects.filter(pk=recent_sent.pk).exists()
    assert NotificationLog.objects.filter(pk=old_queued.pk).exists()


@pytest.mark.django_db
def test_cleanup_logs_respects_custom_retention_setting(settings):
    settings.NOTIFICATION_LOG_RETENTION_DAYS = 10

    log = NotificationLog.objects.create(
        channel=NotificationChannel.MAX, event="e", status=NotificationStatus.FAILED
    )
    _age(log, 11)

    deleted = cleanup_old_notification_logs()
    assert deleted == 1


@pytest.mark.django_db
def test_cleanup_notifications_removes_only_old_rows(settings):
    settings.NOTIFICATION_RETENTION_DAYS = 365
    user = User.objects.create_user(phone="+79001234567", password="pass")

    old = Notification.objects.create(
        user=user, event="order_created", category=NotificationCategory.ORDER_UPDATES, title="t"
    )
    _age(old, 366)
    recent = Notification.objects.create(
        user=user, event="order_created", category=NotificationCategory.ORDER_UPDATES, title="t"
    )

    deleted = cleanup_old_notifications()

    assert deleted == 1
    assert not Notification.objects.filter(pk=old.pk).exists()
    assert Notification.objects.filter(pk=recent.pk).exists()


@pytest.mark.django_db
def test_cleanup_log_deletion_does_not_cascade_delete_notification(settings):
    """AC #521: удаление NotificationLog не должно рвать историю Notification
    раньше её собственного retention (delivery — SET_NULL, не CASCADE)."""
    settings.NOTIFICATION_LOG_RETENTION_DAYS = 90
    user = User.objects.create_user(phone="+79007654321", password="pass")

    log = NotificationLog.objects.create(
        channel=NotificationChannel.MAX, event="e", status=NotificationStatus.SENT
    )
    _age(log, 91)
    notif = Notification.objects.create(
        user=user,
        event="order_created",
        category=NotificationCategory.ORDER_UPDATES,
        title="t",
        delivery=log,
    )

    cleanup_old_notification_logs()

    notif.refresh_from_db()
    assert notif.delivery_id is None
    assert Notification.objects.filter(pk=notif.pk).exists()
