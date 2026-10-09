"""Deletion/re-registration identity contract (DRF-2962)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import AccountDeletionAudit
from apps.accounts.privacy import anonymize_account
from apps.integration_max.models import MaxAccount, MaxAuthAttempt
from apps.integration_max.services import decide

User = get_user_model()


@pytest.mark.django_db(transaction=True)
def test_deleted_account_cannot_login_and_new_registration_gets_new_identity(
    django_capture_on_commit_callbacks,
):
    old = User.objects.create_user(
        email="return@example.com",
        phone="+79000002962",
        password="StrongPass2026",
    )
    old_id = old.pk

    with django_capture_on_commit_callbacks(execute=True):
        anonymize_account(old, reason=AccountDeletionAudit.Reason.USER_REQUEST)

    old.refresh_from_db()
    assert old.is_anonymized
    assert old.email == ""
    assert old.phone == f"deleted-{old_id}"
    assert not old.has_usable_password()

    client = APIClient()
    login = client.post(
        "/api/account/login/",
        {"email": "return@example.com", "password": "StrongPass2026"},
        format="json",
    )
    assert login.status_code == 400

    register = client.post(
        "/api/account/register/",
        {
            "email": "return@example.com",
            "password": "AnotherStrongPass2026",
            "full_name": "Returning Customer",
        },
        format="json",
    )
    assert register.status_code == 201, register.json()

    new = User.objects.get(email="return@example.com")
    assert new.pk != old_id
    assert new.is_active is True
    assert old.is_active is False


@pytest.mark.django_db(transaction=True)
def test_deleted_max_identity_is_not_reactivated(
    django_capture_on_commit_callbacks,
):
    old = User.objects.create_user(phone="+79000002963", password=None)
    max_account = MaxAccount.objects.create(
        user=old,
        max_user_id=2963001,
        chat_id=2963002,
        phone="+79000002963",
        is_active=True,
    )

    with django_capture_on_commit_callbacks(execute=True):
        anonymize_account(old, reason=AccountDeletionAudit.Reason.USER_REQUEST)

    max_account.refresh_from_db()
    old.refresh_from_db()
    assert old.is_anonymized
    assert max_account.is_active is False
    assert max_account.max_user_id < 0

    attempt = MaxAuthAttempt.objects.create(
        secret_hash="hash",
        browser_session_key="session",
        expires_at=old.date_joined,
    )
    decision = decide(attempt, max_user_id=2963001, phone="+79000002963")

    assert decision.ok is True
    assert decision.action == "register"
    assert decision.user_id is None


@pytest.mark.django_db(transaction=True)
def test_repeat_deletion_keeps_tombstone_identity_stable(
    django_capture_on_commit_callbacks,
):
    user = User.objects.create_user(
        email="repeat@example.com",
        phone="+79000002964",
        password="StrongPass2026",
    )
    user_id = user.pk

    with django_capture_on_commit_callbacks(execute=True):
        first = anonymize_account(user, reason=AccountDeletionAudit.Reason.USER_REQUEST)
        second = anonymize_account(user, reason=AccountDeletionAudit.Reason.USER_REQUEST)

    user.refresh_from_db()
    assert first is True
    assert second is False
    assert user.pk == user_id
    assert user.is_anonymized
    assert AccountDeletionAudit.objects.filter(
        reason=AccountDeletionAudit.Reason.USER_REQUEST
    ).count() == 1
