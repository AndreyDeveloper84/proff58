"""Aggregate, PII-free privacy closeout smoke for deployed runtime."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import get_commands
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.integration_max.models import MaxAuthAttempt
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.sync_1c.use_cases import _serialize_order_for_export


class Command(BaseCommand):
    help = "Run aggregate privacy retention/contract checks without printing PII."

    def handle(self, *args, **options):
        now = timezone.now()
        failures: list[str] = []

        guest_ttl = int(getattr(settings, "GUEST_ORDER_TOKEN_TTL_DAYS", 0) or 0)
        if guest_ttl > 0:
            guest_cutoff = now - timedelta(days=guest_ttl)
            expired_guest_tokens = (
                Order.objects.exclude(access_token="").filter(created_at__lt=guest_cutoff).count()
            )
        else:
            expired_guest_tokens = 0

        webhook_days = int(getattr(settings, "PAYMENT_WEBHOOK_RAW_RETENTION_DAYS", 30) or 30)
        webhook_cutoff = now - timedelta(days=webhook_days)
        expired_webhook_payloads = (
            Payment.objects.exclude(webhook_payload={})
            .filter(webhook_payload_at__lt=webhook_cutoff)
            .count()
        )

        stale_max_pending = MaxAuthAttempt.objects.filter(
            status__in=(
                MaxAuthAttempt.Status.PENDING,
                MaxAuthAttempt.Status.CONFIRMATION_REQUIRED,
            ),
            expires_at__lt=now,
        ).count()

        max_hours = int(getattr(settings, "MAX_AUTH_ATTEMPT_RETENTION_HOURS", 24) or 24)
        max_cutoff = now - timedelta(hours=max_hours)
        old_max_terminal = MaxAuthAttempt.objects.filter(
            status__in=(
                MaxAuthAttempt.Status.COMPLETED,
                MaxAuthAttempt.Status.CANCELLED,
                MaxAuthAttempt.Status.EXPIRED,
                MaxAuthAttempt.Status.FAILED,
            ),
            expires_at__lt=max_cutoff,
        ).count()

        active_tombstones = (
            get_user_model().objects.filter(phone__startswith="deleted-", is_active=True).count()
        )

        restore_commands = get_commands()
        restore_export_available = "export_privacy_restore_manifest" in restore_commands
        restore_reconcile_available = "reconcile_privacy_restore" in restore_commands

        sample_order = Order.objects.prefetch_related("items").order_by("pk").first()
        if sample_order is None:
            onec_shape_checked = False
            onec_minimized = True
        else:
            onec_shape_checked = True
            payload = _serialize_order_for_export(sample_order)
            customer_keys = set(payload.get("customer", {}))
            delivery_keys = set(payload.get("delivery", {}))
            onec_minimized = (
                "email" not in customer_keys
                and "address" not in delivery_keys
                and "comment" not in delivery_keys
            )

        checks = {
            "guest_token_ttl_days": guest_ttl,
            "payment_webhook_retention_days": webhook_days,
            "max_auth_retention_hours": max_hours,
            "expired_guest_tokens": expired_guest_tokens,
            "expired_webhook_payloads": expired_webhook_payloads,
            "stale_max_pending": stale_max_pending,
            "old_max_terminal": old_max_terminal,
            "active_deleted_tombstones": active_tombstones,
            "restore_export_available": int(restore_export_available),
            "restore_reconcile_available": int(restore_reconcile_available),
            "onec_shape_checked": int(onec_shape_checked),
            "onec_minimized": int(onec_minimized),
        }

        for key, value in checks.items():
            self.stdout.write(f"{key}={value}")

        if guest_ttl != 90:
            failures.append("guest access token TTL is not 90 days")
        if webhook_days != 30:
            failures.append("payment webhook retention is not 30 days")
        if max_hours != 24:
            failures.append("MAX auth retention is not 24 hours")
        if expired_guest_tokens:
            failures.append("expired guest access tokens remain")
        if expired_webhook_payloads:
            failures.append("expired payment webhook payloads remain")
        if stale_max_pending:
            failures.append("expired MAX attempts remain non-terminal")
        if old_max_terminal:
            failures.append("MAX terminal attempts exceed retention")
        if active_tombstones:
            failures.append("deleted tombstones are active")
        if not restore_export_available or not restore_reconcile_available:
            failures.append("privacy restore commands are unavailable")
        if not onec_minimized:
            failures.append("1C export contains prohibited excess fields")

        if failures:
            raise CommandError("privacy runtime smoke failed: " + "; ".join(failures))

        self.stdout.write(self.style.SUCCESS("privacy_runtime_smoke=PASS"))
