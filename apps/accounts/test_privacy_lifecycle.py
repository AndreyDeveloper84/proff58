"""Privacy lifecycle tests for account anonymization and inactivity (DRF-2929)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.integration_max.models import MaxAccount, MaxAuthAttempt, OrderTrackingGrant
from apps.notifications.models import Notification, NotificationLog
from apps.orders.models import FulfillmentStatus, Order

from .models import AccountDeletionAudit
from .privacy import anonymize_account, process_inactive_accounts

User = get_user_model()


def _old_user(*, phone: str, staff: bool = False):
    user = User.objects.create_user(phone=phone, password="pass")
    User.objects.filter(pk=user.pk).update(
        date_joined=timezone.now() - timedelta(days=3 * 365 + 40),
        is_staff=staff,
    )
    user.refresh_from_db()
    return user


@pytest.mark.django_db(transaction=True)
def test_anonymize_account_scrubs_terminal_order_but_preserves_active_fulfillment_data(
):
    user = User.objects.create_user(
        phone="+79000000001",
        email="person@example.com",
        full_name="Person",
        password="pass",
    )
    terminal = Order.objects.create(
        order_number="P-PRIV-TERM",
        user=user,
        fulfillment_status=FulfillmentStatus.COMPLETED,
        customer_name="Person",
        customer_phone="+79000000001",
        customer_email="person@example.com",
        delivery_address="Private address",
        comment="Call at the gate",
    )
    active = Order.objects.create(
        order_number="P-PRIV-ACTIVE",
        user=user,
        fulfillment_status=FulfillmentStatus.CONFIRMED,
        customer_name="Person",
        customer_phone="+79000000001",
        customer_email="person@example.com",
        delivery_address="Needed for delivery",
        comment="Operational note",
    )

    assert (
        anonymize_account(user, reason=AccountDeletionAudit.Reason.USER_REQUEST) is True
    )

    terminal.refresh_from_db()
    active.refresh_from_db()
    user.refresh_from_db()

    assert terminal.user_id is None
    assert terminal.customer_phone == ""
    assert terminal.customer_email == ""
    assert terminal.delivery_address == ""
    assert terminal.comment == ""

    assert active.user_id is None
    assert active.customer_phone == "+79000000001"
    assert active.delivery_address == "Needed for delivery"

    assert user.is_anonymized
    assert user.email == ""
    assert user.full_name == ""
    assert user.phone_verified is False
    assert not user.has_usable_password()
    assert AccountDeletionAudit.objects.count() == 1

    result = anonymize_account(
        user, reason=AccountDeletionAudit.Reason.USER_REQUEST
    )
    assert result is False
    assert AccountDeletionAudit.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_user_deleted_event_scrubs_max_and_notification_state(
    django_capture_on_commit_callbacks,
):
    user = User.objects.create_user(phone="+79000000002", password="pass")
    order = Order.objects.create(order_number="P-PRIV-MAX", user=user)
    max_account = MaxAccount.objects.create(
        user=user,
        max_user_id=777001,
        chat_id=888001,
        phone="+79000000002",
        first_name="Name",
        last_name="Surname",
        username="person",
        phone_verified_at=timezone.now(),
        is_active=True,
    )
    MaxAuthAttempt.objects.create(
        secret_hash="hash",
        browser_session_key="session",
        user=user,
        max_user_id=777001,
        chat_id=888001,
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    OrderTrackingGrant.objects.create(order=order, max_user_id=777001, chat_id=888001)
    Notification.objects.create(
        user=user,
        event="test",
        category="account",
        title="Private notification",
        body="body",
    )
    NotificationLog.objects.create(
        user=user,
        channel="max",
        event="test",
        status="sent",
        chat_id=888001,
        text="private",
    )

    with django_capture_on_commit_callbacks(execute=True):
        anonymize_account(user, reason=AccountDeletionAudit.Reason.USER_REQUEST)

    max_account.refresh_from_db()
    assert max_account.is_active is False
    assert max_account.max_user_id < 0
    assert max_account.chat_id is None
    assert max_account.phone == ""
    assert max_account.first_name == ""
    assert max_account.last_name == ""
    assert max_account.username == ""
    assert max_account.phone_verified_at is None
    assert not MaxAuthAttempt.objects.filter(user_id=user.pk).exists()
    assert not OrderTrackingGrant.objects.filter(max_user_id=777001).exists()
    assert not Notification.objects.filter(user_id=user.pk).exists()
    assert not NotificationLog.objects.filter(user_id=user.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_inactivity_lifecycle_warns_then_anonymizes(django_capture_on_commit_callbacks):
    user = _old_user(phone="+79000000003")

    first = process_inactive_accounts()
    user.refresh_from_db()

    assert first["warnings_created"] == 1
    assert user.inactivity_warning_at is not None
    assert Notification.objects.filter(
        user=user, event="account_inactivity_warning"
    ).exists()

    User.objects.filter(pk=user.pk).update(
        inactivity_warning_at=timezone.now() - timedelta(days=31)
    )
    user.refresh_from_db()

    with django_capture_on_commit_callbacks(execute=True):
        second = process_inactive_accounts()

    user.refresh_from_db()
    assert second["anonymized"] == 1
    assert user.is_anonymized
    assert AccountDeletionAudit.objects.filter(
        reason=AccountDeletionAudit.Reason.INACTIVITY
    ).count() == 1


@pytest.mark.django_db
def test_activity_after_warning_resets_lifecycle():
    user = _old_user(phone="+79000000004")
    old_warning = timezone.now() - timedelta(days=31)
    recent_login = timezone.now() - timedelta(days=1)
    User.objects.filter(pk=user.pk).update(
        inactivity_warning_at=old_warning,
        last_login=recent_login,
    )

    result = process_inactive_accounts()

    user.refresh_from_db()
    assert result["warnings_reset"] == 1
    assert result["anonymized"] == 0
    assert user.inactivity_warning_at is None
    assert user.is_active is True


@pytest.mark.django_db
def test_staff_accounts_are_excluded_from_inactivity_lifecycle():
    user = _old_user(phone="+79000000005", staff=True)

    result = process_inactive_accounts()

    user.refresh_from_db()
    assert result["skipped_staff"] >= 1
    assert user.inactivity_warning_at is None
    assert user.is_active is True


@pytest.mark.django_db
def test_authenticated_order_counts_as_recent_activity():
    user = _old_user(phone="+79000000006")
    Order.objects.create(
        order_number="P-PRIV-RECENT",
        user=user,
        total=Decimal("100.00"),
    )

    result = process_inactive_accounts()

    user.refresh_from_db()
    assert result["warnings_created"] == 0
    assert user.inactivity_warning_at is None
