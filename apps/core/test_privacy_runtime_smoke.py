"""Tests for the aggregate privacy runtime smoke command."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.orders.models import Order


@pytest.mark.django_db
def test_privacy_runtime_smoke_passes_on_clean_database(settings, capsys):
    settings.GUEST_ORDER_TOKEN_TTL_DAYS = 90
    settings.PAYMENT_WEBHOOK_RAW_RETENTION_DAYS = 30
    settings.MAX_AUTH_ATTEMPT_RETENTION_HOURS = 24

    call_command("privacy_runtime_smoke")

    out = capsys.readouterr().out
    assert "expired_guest_tokens=0" in out
    assert "privacy_runtime_smoke=PASS" in out


@pytest.mark.django_db
def test_privacy_runtime_smoke_fails_on_expired_guest_token(settings):
    settings.GUEST_ORDER_TOKEN_TTL_DAYS = 90
    order = Order.objects.create(
        order_number="P-PRIV-SMOKE-OLD",
        access_token="must-not-print-this-token",
    )
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=91))

    with pytest.raises(CommandError, match="expired guest access tokens remain"):
        call_command("privacy_runtime_smoke")
