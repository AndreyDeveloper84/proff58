"""Re-apply privacy deletion state after restoring an older database backup."""

from __future__ import annotations

import json
import stat
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import AccountDeletionAudit
from apps.accounts.privacy import anonymize_account
from apps.integration_max.tasks import cleanup_max_auth_attempts
from apps.orders.tasks import cleanup_expired_guest_access_tokens
from apps.payments.tasks import cleanup_old_webhook_payloads


class Command(BaseCommand):
    help = "Re-apply account anonymization and retention janitors from a restore manifest."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Manifest produced before restoring the database.")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"Manifest not found: {path}")

        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise CommandError(
                f"Manifest permissions are too broad ({mode:04o}); require owner-only mode 0600"
            )

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Cannot read restore manifest: {exc}") from exc

        if payload.get("version") != 1:
            raise CommandError("Unsupported privacy restore manifest version")

        raw_ids = payload.get("anonymized_user_ids")
        if not isinstance(raw_ids, list) or any(not isinstance(value, int) for value in raw_ids):
            raise CommandError("Manifest anonymized_user_ids must be a list of integer ids")

        User = get_user_model()
        reapplied = already_anonymized = missing = 0
        for user_id in sorted(set(raw_ids)):
            user = User.objects.filter(pk=user_id).first()
            if user is None:
                missing += 1
                continue
            if user.is_anonymized:
                already_anonymized += 1
                continue
            if anonymize_account(user, reason=AccountDeletionAudit.Reason.RESTORE_RECONCILIATION):
                reapplied += 1

        guest_tokens = cleanup_expired_guest_access_tokens.run()
        webhook_payloads = cleanup_old_webhook_payloads.run()
        max_auth = cleanup_max_auth_attempts.run()

        self.stdout.write(
            self.style.SUCCESS(
                "Privacy restore reconciliation complete: "
                f"reapplied={reapplied} already_anonymized={already_anonymized} "
                f"missing={missing} guest_tokens={guest_tokens} "
                f"webhook_payloads={webhook_payloads} max_auth={max_auth}"
            )
        )
