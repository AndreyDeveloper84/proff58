"""Отчёт по CatalogProcessingRun.

Пример:

    python manage.py catalog_queue_status --run <uuid>
"""

from __future__ import annotations

import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import CatalogChange, CatalogProcessingItem, CatalogProcessingRun


class Command(BaseCommand):
    help = "Отчёт по CatalogProcessingRun."

    def add_arguments(self, parser):
        parser.add_argument("--run", type=str, required=True, help="UUID run.")

    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.FEATURES.get("catalog_processing", False):
            raise CommandError("Feature catalog_processing выключен.")

        run_id = options["run"]
        run = CatalogProcessingRun.objects.filter(pk=run_id).first()
        if run is None:
            raise CommandError(f"Run {run_id} не найден")

        items = CatalogProcessingItem.objects.filter(run=run)
        item_statuses = Counter(items.values_list("status", flat=True))
        changes = CatalogChange.objects.filter(item__run=run)
        change_statuses = Counter(changes.values_list("status", flat=True))

        pending_review = changes.filter(status="proposed").count()
        errors = list(
            items.exclude(error_code="").values_list("product_ref", "error_code", "error_detail")
        )

        report = {
            "run_id": str(run.pk),
            "kind": run.kind,
            "mode": run.mode,
            "status": run.status,
            "created_at": run.created_at.isoformat(),
            "items": {
                "total": items.count(),
                "by_status": dict(item_statuses),
            },
            "changes": {
                "total": changes.count(),
                "by_status": dict(change_statuses),
                "pending_review": pending_review,
            },
            "errors": [
                {"product_ref": ref, "code": code, "detail": detail}
                for ref, code, detail in errors[:50]
            ],
        }

        payload = json.dumps(report, ensure_ascii=False, indent=2)
        self.stdout.write(payload)
        return payload
