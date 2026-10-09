"""Privacy lifecycle for customer accounts.

One shared anonymization path is used by both the user-requested delete endpoint
and the inactivity janitor. Integration-specific cleanup is triggered through the
existing user_deleted domain event so accounts does not own MAX/OAuth schemas.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.accounts.models import AccountDeletionAudit, Profile
from apps.accounts.wishlist import WishlistItem

User = get_user_model()

INACTIVITY_YEARS = 3
INACTIVITY_WARNING_DAYS = 30


def account_activity_at(user) -> object:
    """Return the latest durable account activity known to the backend.

    Login is the strongest direct activity signal. An authenticated order is also
    activity even when last_login was not updated by a non-standard auth flow.
    """
    from apps.orders.models import Order

    latest_order = (
        Order.objects.filter(user=user).aggregate(value=Max("created_at")).get("value")
    )
    candidates = [user.date_joined, user.last_login, latest_order]
    return max(value for value in candidates if value is not None)


@transaction.atomic
def anonymize_account(user, *, reason: str) -> bool:
    """Irreversibly anonymize one customer account.

    Returns False when the row is already an anonymized tombstone. This makes
    repeated manual/janitor calls safe and prevents duplicate audit records.
    """
    from apps.core.events import user_deleted
    from apps.orders.models import FulfillmentStatus, Order

    locked = User.objects.select_for_update().get(pk=user.pk)
    if locked.is_anonymized:
        return False

    terminal = (FulfillmentStatus.COMPLETED, FulfillmentStatus.CANCELLED)

    # Completed/cancelled orders no longer need fulfillment contact details.
    # Keep the financial/order ledger, but clear excess contact/free-text PII.
    Order.objects.filter(user=locked, fulfillment_status__in=terminal).update(
        user=None,
        customer_name="[удалён]",
        customer_phone="",
        customer_email="",
        company_name="",
        inn="",
        kpp="",
        legal_address="",
        delivery_address="",
        comment="",
    )

    # Active orders may still need phone/address to complete fulfillment.
    # Detach them from the account but preserve the operational order snapshot.
    Order.objects.filter(user=locked).update(user=None)

    Profile.objects.filter(user=locked).update(
        company_name="",
        inn="",
        kpp="",
        legal_address="",
        is_b2b_verified=False,
        pd_consent_at=None,
        pd_consent_version="",
    )
    WishlistItem.objects.filter(user=locked).delete()

    locked.phone = f"deleted-{locked.pk}"
    locked.email = ""
    locked.full_name = ""
    locked.max_chat_id = None
    locked.phone_verified = False
    locked.last_login = None
    locked.inactivity_warning_at = None
    locked.is_active = False
    locked.set_unusable_password()
    locked.save(
        update_fields=[
            "phone",
            "email",
            "full_name",
            "max_chat_id",
            "phone_verified",
            "last_login",
            "inactivity_warning_at",
            "is_active",
            "password",
        ]
    )

    AccountDeletionAudit.objects.create(reason=reason)

    # Higher-layer integrations remove their own identifiers only after the DB
    # transaction commits successfully.
    transaction.on_commit(lambda uid=locked.pk: user_deleted.send(sender=User, user_id=uid))
    return True


def _three_year_cutoff(now):
    """Calendar-aware three-year cutoff, including leap-day accounts."""
    try:
        return now.replace(year=now.year - INACTIVITY_YEARS)
    except ValueError:
        # 29 February -> 28 February in a non-leap target year.
        return now.replace(year=now.year - INACTIVITY_YEARS, day=28)


def process_inactive_accounts(*, now=None) -> dict[str, int]:
    """Issue warnings and anonymize accounts that remain inactive after 30 days."""
    now = now or timezone.now()
    inactivity_cutoff = _three_year_cutoff(now)
    warning_cutoff = now - timedelta(days=INACTIVITY_WARNING_DAYS)

    stats = {
        "warnings_created": 0,
        "warnings_reset": 0,
        "anonymized": 0,
        "skipped_staff": 0,
    }

    qs = User.objects.filter(is_active=True).order_by("pk")
    for user in qs.iterator():
        if user.is_staff or user.is_superuser:
            stats["skipped_staff"] += 1
            continue

        activity_at = account_activity_at(user)

        if (
            user.inactivity_warning_at is not None
            and activity_at > user.inactivity_warning_at
        ):
            User.objects.filter(pk=user.pk).update(inactivity_warning_at=None)
            stats["warnings_reset"] += 1
            user.inactivity_warning_at = None

        if activity_at > inactivity_cutoff:
            continue

        if user.inactivity_warning_at is None:
            _issue_inactivity_warning(user, now=now)
            User.objects.filter(pk=user.pk).update(inactivity_warning_at=now)
            stats["warnings_created"] += 1
            continue

        if user.inactivity_warning_at > warning_cutoff:
            continue

        # Re-read under the shared anonymization service. Any activity after the
        # warning is detected above and resets the lifecycle instead of deleting.
        if anonymize_account(user, reason=AccountDeletionAudit.Reason.INACTIVITY):
            stats["anonymized"] += 1

    return stats


def _service_email_available() -> bool:
    from django.conf import settings

    backend = getattr(settings, "EMAIL_BACKEND", "") or ""
    if backend.endswith("smtp.EmailBackend"):
        return bool((getattr(settings, "EMAIL_HOST", "") or "").strip())
    # Non-SMTP backends are useful in dev/tests and are explicitly configured.
    return bool(backend)


def _issue_inactivity_warning(user, *, now) -> None:
    """Create the in-app intent, then attempt available service transports."""
    from apps.notifications.services import create_notification, notify_customer

    deadline = now + timedelta(days=INACTIVITY_WARNING_DAYS)
    payload = {"deadline": deadline.date().isoformat()}
    key = f"account-inactivity-warning-{user.pk}-{now.date().isoformat()}"

    # Always creates an in-app Notification intent. MAX delivery is attempted by
    # the notification domain when an active channel is available.
    create_notification(
        user=user,
        event="account_inactivity_warning",
        payload=payload,
        idempotency_key=key,
    )

    if user.email and _service_email_available():
        notify_customer(
            email=user.email,
            event="account_inactivity_warning",
            payload=payload,
            idempotency_key=f"{key}-email",
        )
