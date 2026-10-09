"""Export a minimal restore manifest for already-anonymized accounts."""

from __future__ import annotations

import json
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Export minimal account identifiers required for post-restore privacy reconciliation."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Output manifest path outside the application database.")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if path.exists():
            raise CommandError(f"Refusing to overwrite existing manifest: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

        User = get_user_model()
        user_ids = list(
            User.objects.filter(is_active=False, phone__startswith="deleted-")
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        payload = {
            "version": 1,
            "generated_at": timezone.now().isoformat(),
            "anonymized_user_ids": user_ids,
        }

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(path, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
        except Exception:
            path.unlink(missing_ok=True)
            raise

        os.chmod(path, 0o600)
        self.stdout.write(
            self.style.SUCCESS(
                f"Privacy restore manifest written: path={path} accounts={len(user_ids)} mode=0600"
            )
        )
