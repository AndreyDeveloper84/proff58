"""PR #126: конкурентность 1С-импорта — очередь onec (сериализация) + ретрай.

Гонку «одна актуальная цена» закрывает выделенная очередь `onec` с concurrency=1
(worker -Q onec -c 1): задачи 1С идут строго последовательно. Здесь проверяем
маршрутизацию (сериализацию конфигом) и ограниченный ретрай на временную ошибку БД.
"""

from __future__ import annotations

import pytest
from celery.exceptions import Retry
from django.db import IntegrityError

from apps.sync_1c import tasks, use_cases
from apps.sync_1c.models import SyncLog
from config.celery import app


def test_onec_tasks_routed_to_onec_queue():
    """1С-задачи маршрутизируются в очередь onec (её worker -c 1 сериализует обмены)."""
    for name in (
        "apps.sync_1c.tasks.import_products_task",
        "apps.sync_1c.tasks.import_1c_file",
    ):
        route = app.amqp.router.route({}, name)
        queue = route["queue"]
        assert getattr(queue, "name", queue) == "onec", name


def test_import_task_has_acks_late_and_retries():
    """Задача импорта: acks_late (переисполнение при падении воркера) + bounded retries."""
    assert tasks.import_products_task.acks_late is True
    assert tasks.import_products_task.max_retries == 2


def _raise_integrity(*args, **kwargs):
    raise IntegrityError("transient race")


@pytest.mark.django_db
def test_transient_db_error_triggers_retry_not_fail(monkeypatch):
    """Временная ошибка БД (гонка) → задача уходит в RETRY, прогон НЕ помечается ошибкой."""
    monkeypatch.setattr(use_cases, "run_import_into", _raise_integrity)
    sync_log = use_cases.new_import_job(source_file="t")
    with pytest.raises(Retry):  # eager: self.retry пробрасывает Retry — значит ретраим
        tasks.import_products_task.apply(
            args=[sync_log.id, [{"external_id": "x1", "name": "Дрель", "price": "100"}]],
            throw=True,
        )
    sync_log.refresh_from_db()
    assert sync_log.result != SyncLog.SyncResult.ERROR  # при ретрае не помечаем ошибкой


@pytest.mark.django_db
def test_retries_exhausted_marks_error(monkeypatch):
    """После исчерпания ретраев прогон помечается ERROR (не виснет в RUNNING)."""
    monkeypatch.setattr(use_cases, "run_import_into", _raise_integrity)
    sync_log = use_cases.new_import_job(source_file="t")
    result = tasks.import_products_task.apply(
        args=[sync_log.id, [{"external_id": "x2", "name": "Дрель", "price": "100"}]],
        retries=2,  # имитируем 3-ю попытку: self.request.retries >= max_retries
        throw=False,
    )
    assert result.failed()
    sync_log.refresh_from_db()
    assert sync_log.result == SyncLog.SyncResult.ERROR
