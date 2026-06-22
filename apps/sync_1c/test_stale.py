"""#57: надёжность фон-импорта 1С — janitor зависших RUNNING + идемпотентный task-guard.

Дыра: воркер умер между стартом прогона и его финализацией → SyncLog навсегда RUNNING.
Закрываем двумя страховками:
  * janitor mark_stale_imports() — помечает «провисевшие» RUNNING как ERROR;
  * task-guard в import_products_task — не запускает импорт повторно для уже
    финализированного прогона (redelivery при acks_late + hard-kill).
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.test import override_settings
from django.utils import timezone

from apps.catalog.models import Product
from apps.sync_1c import tasks, use_cases
from apps.sync_1c.models import SyncLog


def _running_job(started_offset_seconds: int = 0) -> SyncLog:
    """RUNNING-прогон с started_at, сдвинутым в прошлое (auto_now_add обходим update)."""
    sync_log = SyncLog.objects.create(
        sync_type=SyncLog.SyncType.FULL,
        source_file="t",
        result=SyncLog.SyncResult.RUNNING,
    )
    if started_offset_seconds:
        SyncLog.objects.filter(pk=sync_log.pk).update(
            started_at=timezone.now() - timedelta(seconds=started_offset_seconds)
        )
        sync_log.refresh_from_db()
    return sync_log


@pytest.mark.django_db
def test_janitor_marks_stale_running_as_error():
    """RUNNING старше SYNC_STALE_TIMEOUT → ERROR, finished_at задан, пометка в error_details."""
    sync_log = _running_job(started_offset_seconds=31 * 60)  # > дефолтных 30 минут

    count, uids = use_cases.mark_stale_imports()

    assert count == 1
    assert uids == [str(sync_log.batch_uid)]
    sync_log.refresh_from_db()
    assert sync_log.result == SyncLog.SyncResult.ERROR
    assert sync_log.finished_at is not None
    assert "зависшим" in sync_log.error_details


@pytest.mark.django_db
def test_janitor_ignores_fresh_running():
    """Свежий RUNNING (только что стартовал) janitor не трогает."""
    sync_log = _running_job(started_offset_seconds=0)

    count, _ = use_cases.mark_stale_imports()

    assert count == 0
    sync_log.refresh_from_db()
    assert sync_log.result == SyncLog.SyncResult.RUNNING
    assert sync_log.finished_at is None


@pytest.mark.django_db
def test_janitor_ignores_finished_jobs():
    """Уже завершённые (OK/ERROR), даже старые, не трогаются — фильтр по RUNNING."""
    ok = SyncLog.objects.create(
        sync_type=SyncLog.SyncType.FULL, result=SyncLog.SyncResult.OK, finished_at=timezone.now()
    )
    err = SyncLog.objects.create(
        sync_type=SyncLog.SyncType.FULL, result=SyncLog.SyncResult.ERROR, finished_at=timezone.now()
    )
    SyncLog.objects.filter(pk__in=[ok.pk, err.pk]).update(
        started_at=timezone.now() - timedelta(seconds=60 * 60)
    )

    count, _ = use_cases.mark_stale_imports()

    assert count == 0
    ok.refresh_from_db()
    err.refresh_from_db()
    assert ok.result == SyncLog.SyncResult.OK
    assert err.result == SyncLog.SyncResult.ERROR


@pytest.mark.django_db
def test_janitor_is_idempotent():
    """Повторный прогон на уже-помеченном (ERROR) ничего не делает (count=0)."""
    _running_job(started_offset_seconds=31 * 60)

    first, _ = use_cases.mark_stale_imports()
    second, uids = use_cases.mark_stale_imports()

    assert first == 1
    assert second == 0
    assert uids == []


@pytest.mark.django_db
def test_stale_job_reported_finished():
    """Помеченный зависшим прогон отдаётся как finished (is_finished → True)."""
    sync_log = _running_job(started_offset_seconds=31 * 60)
    assert use_cases.is_finished(sync_log) is False

    use_cases.mark_stale_imports()
    sync_log.refresh_from_db()

    assert use_cases.is_finished(sync_log) is True


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
@pytest.mark.django_db
def test_task_guard_skips_finalized_job():
    """Task-guard: для НЕ-RUNNING прогона задача не выполняет импорт (Product не создаётся)."""
    sync_log = SyncLog.objects.create(
        sync_type=SyncLog.SyncType.FULL,
        result=SyncLog.SyncResult.ERROR,  # уже финализирован janitor-ом
        finished_at=timezone.now(),
    )
    raw_items = [{"external_id": "guard-1", "name": "Дрель", "price": "100"}]

    tasks.import_products_task.apply(args=[sync_log.id, raw_items], throw=True)

    assert not Product.objects.filter(code_1c="guard-1").exists()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
@pytest.mark.django_db
def test_soft_timeout_finalizes_error():
    """SoftTimeLimitExceeded в импорте → прогон финализируется в ERROR (fail_import_job)."""
    sync_log = use_cases.new_import_job(source_file="t")
    raw_items = [{"external_id": "soft-1", "name": "Дрель", "price": "100"}]

    with mock.patch.object(use_cases, "run_import_into", side_effect=SoftTimeLimitExceeded()):
        result = tasks.import_products_task.apply(args=[sync_log.id, raw_items], throw=False)

    assert result.failed()
    sync_log.refresh_from_db()
    assert sync_log.result == SyncLog.SyncResult.ERROR
    assert "Мягкий таймаут" in sync_log.error_details
