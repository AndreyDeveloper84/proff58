"""Конфигурация Celery.

Воркер и beat обслуживают фоновые задачи: обмен ценами/остатками с 1С,
конвейер обогащения каталога, отправку SMS и т.п.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("proff58")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Регулярные задачи (beat). Janitor зависших импортов 1С (#57): помечает прогоны,
# зависшие в RUNNING (умерший воркер), как ERROR — иначе они висят навсегда.
app.conf.beat_schedule = {
    "mark-stale-syncs": {
        "task": "apps.sync_1c.tasks.mark_stale_syncs",
        "schedule": 5 * 60,  # каждые 5 минут
    },
}
