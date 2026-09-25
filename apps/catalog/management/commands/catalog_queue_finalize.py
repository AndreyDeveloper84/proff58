"""Финализация CatalogProcessingRun: running -> completed.

Пример:

    python manage.py catalog_queue_finalize --run <uuid>

Запрещена при pending/processing items и proposed/approved changes.
Идемпотентна: повторный вызов по completed run завершается успехом
с ``already_finalized=true``. Product/PAV не изменяет.
"""

from __future__ import annotations

import json
import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.processing import finalize_catalog_processing_run


class Command(BaseCommand):
    help = "Финализировать CatalogProcessingRun (перевести в completed)."

    def add_arguments(self, parser):
        parser.add_argument("--run", type=str, required=True, help="UUID run.")

    def handle(self, *args, **options):
        try:
            run_id = uuid.UUID(options["run"])
        except ValueError as exc:
            raise CommandError(f"Некорректный UUID run: {options['run']}") from exc

        result = finalize_catalog_processing_run(run_id)
        report = {
            "run_id": str(result.run_id),
            "status": result.status,
            "reason": result.reason,
            "already_finalized": result.already_finalized,
            "outcome": result.outcome,
        }
        payload = json.dumps(report, ensure_ascii=False, indent=2)
        self.stdout.write(payload)
        if result.status != "completed":
            raise CommandError(f"Финализация невозможна: {result.reason}")
        return payload
