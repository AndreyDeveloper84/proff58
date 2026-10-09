"""Post-restore privacy reconciliation tests (DRF-2964)."""

from __future__ import annotations

import json
import os
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import AccountDeletionAudit
from apps.accounts.privacy import anonymize_account
from apps.orders.models import Order
from apps.payments.models import Payment

User = get_user_model()


@pytest.mark.django_db(transaction=True)
def test_restore_manifest_reapplies_anonymization_without_external_workers(
    tmp_path,
    django_capture_on_commit_callbacks,
    settings,
):
    settings.GUEST_ORDER_TOKEN_TTL_DAYS = 90
    settings.PAYMENT_WEBHOOK_RAW_RETENTION_DAYS = 30

    user = User.objects.create_user(
        phone="+79000000964",
        email="restore@example.com",
        full_name="Restore Person",
        password="pass",
    )
    user_id = user.pk

    with django_capture_on_commit_callbacks(execute=True):
        anonymize_account(user, reason=AccountDeletionAudit.Reason.USER_REQUEST)

    manifest = tmp_path / "privacy-restore.json"
    call_command("export_privacy_restore_manifest", str(manifest))
    assert (os.stat(manifest).st_mode & 0o777) == 0o600
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["anonymized_user_ids"] == [user_id]

    # Simulate restoring an older backup in which the account still contained PII.
    User.objects.filter(pk=user_id).update(
        phone="+79000000964",
        email="restore@example.com",
        full_name="Restore Person",
        is_active=True,
    )
    restored = User.objects.get(pk=user_id)
    assert restored.is_anonymized is False

    old_order = Order.objects.create(
        order_number="P-RESTORE-TOKEN",
        access_token="secret-token",
    )
    Order.objects.filter(pk=old_order.pk).update(
        created_at=timezone.now() - timedelta(days=91)
    )

    call_command("reconcile_privacy_restore", str(manifest))

    restored.refresh_from_db()
    old_order.refresh_from_db()
    assert restored.is_anonymized
    assert restored.email == ""
    assert restored.full_name == ""
    assert old_order.access_token == ""
    assert AccountDeletionAudit.objects.filter(
        reason=AccountDeletionAudit.Reason.RESTORE_RECONCILIATION
    ).exists()


@pytest.mark.django_db
def test_restore_reconciliation_rejects_world_readable_manifest(tmp_path):
    manifest = tmp_path / "privacy-restore.json"
    manifest.write_text(
        json.dumps({"version": 1, "generated_at": "x", "anonymized_user_ids": []}),
        encoding="utf-8",
    )
    os.chmod(manifest, 0o644)

    with pytest.raises(Exception, match="permissions are too broad"):
        call_command("reconcile_privacy_restore", str(manifest))
