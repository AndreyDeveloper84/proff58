"""Retention tests for ProductAvailabilitySubscription (DRF-2926)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from .availability_subscriptions import (
    ProductAvailabilitySubscription,
    SubscriptionStatus,
    _months_ago,
    cleanup_availability_subscriptions,
)
from .models import Product, ProductStatus

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+79001234567", password="pass")


@pytest.fixture
def product(db):
    return Product.objects.create(
        name="Retention product",
        slug="availability-retention-product",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("0"),
    )


@pytest.mark.django_db
def test_cleanup_deletes_active_older_than_six_calendar_months(settings, user, product):
    settings.AVAILABILITY_ACTIVE_RETENTION_MONTHS = 6
    old = ProductAvailabilitySubscription.objects.create(user=user, product=product)
    cutoff = _months_ago(timezone.now(), 6)
    ProductAvailabilitySubscription.objects.filter(pk=old.pk).update(
        subscribed_at=cutoff - timedelta(days=1)
    )

    result = cleanup_availability_subscriptions()

    assert result["deleted_active"] == 1
    assert not ProductAvailabilitySubscription.objects.filter(pk=old.pk).exists()


@pytest.mark.django_db
def test_cleanup_keeps_active_inside_six_month_window(settings, user, product):
    settings.AVAILABILITY_ACTIVE_RETENTION_MONTHS = 6
    recent = ProductAvailabilitySubscription.objects.create(user=user, product=product)
    cutoff = _months_ago(timezone.now(), 6)
    ProductAvailabilitySubscription.objects.filter(pk=recent.pk).update(
        subscribed_at=cutoff + timedelta(days=1)
    )

    cleanup_availability_subscriptions()

    assert ProductAvailabilitySubscription.objects.filter(pk=recent.pk).exists()


@pytest.mark.django_db
def test_cleanup_deletes_notified_and_cancelled_after_30_days(settings, user, product):
    settings.AVAILABILITY_TERMINAL_RETENTION_DAYS = 30
    now = timezone.now()
    notified = ProductAvailabilitySubscription.objects.create(
        user=user,
        product=product,
        status=SubscriptionStatus.NOTIFIED,
        notified_at=now - timedelta(days=31),
    )
    cancelled = ProductAvailabilitySubscription.objects.create(
        user=user,
        product=product,
        status=SubscriptionStatus.CANCELLED,
        cancelled_at=now - timedelta(days=31),
    )

    result = cleanup_availability_subscriptions()

    assert result["deleted_notified"] == 1
    assert result["deleted_cancelled"] == 1
    assert not ProductAvailabilitySubscription.objects.filter(pk=notified.pk).exists()
    assert not ProductAvailabilitySubscription.objects.filter(pk=cancelled.pk).exists()


@pytest.mark.django_db
def test_cleanup_recovers_stale_queued_subscription(settings, user, product):
    settings.AVAILABILITY_QUEUED_STALE_MINUTES = 60
    queued = ProductAvailabilitySubscription.objects.create(
        user=user,
        product=product,
        status=SubscriptionStatus.QUEUED,
        queued_at=timezone.now() - timedelta(minutes=61),
    )

    result = cleanup_availability_subscriptions()

    queued.refresh_from_db()
    assert result["reverted_queued"] == 1
    assert queued.status == SubscriptionStatus.ACTIVE
    assert queued.queued_at is None


@pytest.mark.django_db
def test_cleanup_is_idempotent(settings, user, product):
    settings.AVAILABILITY_TERMINAL_RETENTION_DAYS = 30
    ProductAvailabilitySubscription.objects.create(
        user=user,
        product=product,
        status=SubscriptionStatus.NOTIFIED,
        notified_at=timezone.now() - timedelta(days=31),
    )

    first = cleanup_availability_subscriptions()
    second = cleanup_availability_subscriptions()

    assert first["deleted_notified"] == 1
    assert second["deleted_notified"] == 0
