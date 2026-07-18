"""Смоук-тест Prometheus-экспортёра notification domain (#521)."""

from __future__ import annotations

import pytest
from django.test import Client

from .models import NotificationChannel, NotificationLog, NotificationStatus


@pytest.mark.django_db
def test_metrics_endpoint_returns_expected_series():
    NotificationLog.objects.create(
        channel=NotificationChannel.MAX, event="order_paid", status=NotificationStatus.SENT
    )
    NotificationLog.objects.create(
        channel=NotificationChannel.MAX,
        event="order_paid",
        status=NotificationStatus.QUEUED,
    )

    resp = Client().get("/metrics/notifications/")

    assert resp.status_code == 200
    body = resp.content.decode()
    assert "notification_delivery_total" in body
    assert "notification_delivery_failed_total" in body
    assert "notification_queue_size" in body
    assert "notification_queue_lag_seconds" in body
    assert "notification_intent_skipped_total" in body
    assert "notification_intent_to_sent_seconds_avg" in body


@pytest.mark.django_db
def test_metrics_endpoint_requires_token_when_configured(settings):
    settings.METRICS_TOKEN = "secret-token"
    resp = Client().get("/metrics/notifications/")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_metrics_endpoint_accepts_valid_token(settings):
    settings.METRICS_TOKEN = "secret-token"
    resp = Client().get("/metrics/notifications/", HTTP_AUTHORIZATION="Bearer secret-token")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_queue_size_reflects_queued_rows():
    from .metrics import NotificationCollector

    NotificationLog.objects.create(
        channel=NotificationChannel.MAX, event="e", status=NotificationStatus.QUEUED
    )
    NotificationLog.objects.create(
        channel=NotificationChannel.MAX, event="e", status=NotificationStatus.QUEUED
    )
    NotificationLog.objects.create(
        channel=NotificationChannel.MAX, event="e", status=NotificationStatus.SENT
    )

    metrics = {m.name: m for m in NotificationCollector().collect()}
    queue_size = metrics["notification_queue_size"].samples[0].value
    assert queue_size == 2
