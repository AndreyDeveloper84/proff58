"""Management-команда: пометить зависшие RUNNING-прогоны импорта 1С как ERROR (#57).

Зависший прогон = result=RUNNING без финализации дольше SYNC_STALE_TIMEOUT (умер
воркер между стартом и финалом). То же делает beat-задача mark_stale_syncs; команда —
для ручного прогона/расследования. Идемпотентна.

Пример:
    python manage.py mark_stale_syncs
"""

from django.core.management.base import BaseCommand

from apps.sync_1c.use_cases import mark_stale_imports


class Command(BaseCommand):
    help = "Пометить зависшие RUNNING-прогоны импорта 1С как ERROR."

    def handle(self, *args, **options):
        count, uids = mark_stale_imports()
        self.stdout.write(self.style.SUCCESS(f"Помечено зависших: {count}"))
        for uid in uids:
            self.stdout.write(f"  - {uid}")
