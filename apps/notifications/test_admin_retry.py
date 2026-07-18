"""Тесты admin-действия ручного retry (#521 AC: "manual retry только retryable
failures") — permanent исключается, retryable и неклассифицированные (баг
channels/max.py, а не провайдерская ошибка) допускаются к ручному повтору."""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.admin.sites import AdminSite

from .admin import NotificationLogAdmin
from .models import NotificationChannel, NotificationErrorKind, NotificationLog, NotificationStatus


@pytest.fixture
def admin_instance():
    return NotificationLogAdmin(NotificationLog, AdminSite())


def _log(**kwargs):
    defaults = dict(channel=NotificationChannel.MAX, event="order_paid", chat_id=1, text="x")
    defaults.update(kwargs)
    return NotificationLog.objects.create(**defaults)


@pytest.mark.django_db
@mock.patch("apps.notifications.tasks.send_notification_task.delay")
def test_retry_action_requeues_only_retryable_failed(mock_delay, admin_instance, rf):
    retryable = _log(status=NotificationStatus.FAILED, error_kind=NotificationErrorKind.RETRYABLE)
    permanent = _log(status=NotificationStatus.FAILED, error_kind=NotificationErrorKind.PERMANENT)
    sent = _log(status=NotificationStatus.SENT)

    request = rf.post("/admin/notifications/notificationlog/")
    request._messages = mock.MagicMock()
    qs = NotificationLog.objects.filter(pk__in=[retryable.pk, permanent.pk, sent.pk])

    admin_instance.retry_failed(request, qs)

    retryable.refresh_from_db()
    permanent.refresh_from_db()
    sent.refresh_from_db()

    assert retryable.status == NotificationStatus.QUEUED
    assert retryable.error_kind == ""
    assert permanent.status == NotificationStatus.FAILED  # не тронут
    assert sent.status == NotificationStatus.SENT  # не тронут

    mock_delay.assert_called_once_with(retryable.pk)


@pytest.mark.django_db
@mock.patch("apps.notifications.tasks.send_notification_task.delay")
def test_retry_action_includes_unclassified_failed(mock_delay, admin_instance, rf):
    """Регрессия #521: generic except в tasks.py не проставляет error_kind —
    такие FAILED-строки не должны быть недостижимы для ручного retry."""
    unclassified = _log(status=NotificationStatus.FAILED, error_kind="")

    request = rf.post("/admin/notifications/notificationlog/")
    request._messages = mock.MagicMock()
    admin_instance.retry_failed(request, NotificationLog.objects.filter(pk=unclassified.pk))

    unclassified.refresh_from_db()
    assert unclassified.status == NotificationStatus.QUEUED
    mock_delay.assert_called_once_with(unclassified.pk)


@pytest.mark.django_db
@mock.patch("apps.notifications.tasks.send_notification_task.delay")
def test_retry_action_noop_when_nothing_retryable(mock_delay, admin_instance, rf):
    permanent = _log(status=NotificationStatus.FAILED, error_kind=NotificationErrorKind.PERMANENT)

    request = rf.post("/admin/notifications/notificationlog/")
    request._messages = mock.MagicMock()
    admin_instance.retry_failed(request, NotificationLog.objects.filter(pk=permanent.pk))

    mock_delay.assert_not_called()
    permanent.refresh_from_db()
    assert permanent.status == NotificationStatus.FAILED
