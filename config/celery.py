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
