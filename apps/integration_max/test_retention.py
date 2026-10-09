"""Retention tests for MAX auth attempts (DRF-2924)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from .models import MaxAuthAttempt
from .tasks import cleanup_max_auth_attempts


def _attempt(*, status: str, expires_delta: timedelta) -> MaxAuthAttempt:
    return MaxAuthAttempt.objects.create(
        secret_hash="x",
        browser_session_key="session",
        status=status,
        expires_at=timezone.now() + expires_delta,
    )


@pytest.mark.django_db
def test_cleanup_normalizes_stale_pending_and_confirmation_required(settings):
    settings.MAX_AUTH_ATTEMPT_RETENTION_HOURS = 24
    stale_pending = _attempt(
        status=MaxAuthAttempt.Status.PENDING,
        expires_delta=timedelta(minutes=-10),
    )
    stale_confirmation = _attempt(
        status=MaxAuthAttempt.Status.CONFIRMATION_REQUIRED,
        expires_delta=timedelta(minutes=-10),
    )
    fresh_pending = _attempt(
        status=MaxAuthAttempt.Status.PENDING,
        expires_delta=timedelta(minutes=2),
    )

    result = cleanup_max_auth_attempts()

    stale_pending.refresh_from_db()
    stale_confirmation.refresh_from_db()
    fresh_pending.refresh_from_db()
    assert stale_pending.status == MaxAuthAttempt.Status.EXPIRED
    assert stale_confirmation.status == MaxAuthAttempt.Status.EXPIRED
    assert fresh_pending.status == MaxAuthAttempt.Status.PENDING
    assert result["normalized"] == 2


@pytest.mark.django_db
def test_cleanup_purges_only_terminal_rows_beyond_retention(settings):
    settings.MAX_AUTH_ATTEMPT_RETENTION_HOURS = 24
    old_completed = _attempt(
        status=MaxAuthAttempt.Status.COMPLETED,
        expires_delta=timedelta(hours=-25),
    )
    old_failed = _attempt(
        status=MaxAuthAttempt.Status.FAILED,
        expires_delta=timedelta(hours=-25),
    )
    recent_cancelled = _attempt(
        status=MaxAuthAttempt.Status.CANCELLED,
        expires_delta=timedelta(hours=-23),
    )
    fresh_pending = _attempt(
        status=MaxAuthAttempt.Status.PENDING,
        expires_delta=timedelta(minutes=2),
    )

    result = cleanup_max_auth_attempts()

    assert not MaxAuthAttempt.objects.filter(pk=old_completed.pk).exists()
    assert not MaxAuthAttempt.objects.filter(pk=old_failed.pk).exists()
    assert MaxAuthAttempt.objects.filter(pk=recent_cancelled.pk).exists()
    assert MaxAuthAttempt.objects.filter(pk=fresh_pending.pk).exists()
    assert result["purged"] == 2


@pytest.mark.django_db
def test_cleanup_is_idempotent(settings):
    settings.MAX_AUTH_ATTEMPT_RETENTION_HOURS = 24
    stale = _attempt(
        status=MaxAuthAttempt.Status.PENDING,
        expires_delta=timedelta(hours=-25),
    )

    first = cleanup_max_auth_attempts()
    second = cleanup_max_auth_attempts()

    assert not MaxAuthAttempt.objects.filter(pk=stale.pk).exists()
    assert first == {"normalized": 1, "purged": 1}
    assert second == {"normalized": 0, "purged": 0}
