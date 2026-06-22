"""Celery-задачи синхронизации с 1С.

Тяжёлые/регулярные операции выносятся в фон, чтобы сбои или медлительность
1С не влияли на витрину. Все задачи маршрутизируются в очередь `onec`
(settings.CELERY_TASK_ROUTES), worker которой запускается с concurrency=1 — обмены идут
строго последовательно (#126), что снимает гонку «одна актуальная цена».
"""

import logging
import traceback

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import IntegrityError, OperationalError

from . import parsers, use_cases
from .models import SyncLog

logger = logging.getLogger(__name__)

# acks_late: при падении/таймауте воркера задача переисполнится (импорт идемпотентен,
# особенно после skip-unchanged-price #111). Ретрай — ТОЛЬКО на временные ошибки БД
# (гонка/блокировка); реальный data-bug не зацикливаем.
_MAX_RETRIES = 2


@shared_task(acks_late=True)
def import_1c_file(path: str, sync_type: str = SyncLog.SyncType.FULL) -> dict:
    """Импортировать выгрузку 1С из файла в фоне."""
    items = parsers.load_items(path)
    sync_log, result = use_cases.import_products(items, source_file=path, sync_type=sync_type)
    return {"batch_uid": str(sync_log.batch_uid), **result.as_dict()}


@shared_task(
    bind=True,
    acks_late=True,
    max_retries=_MAX_RETRIES,
    default_retry_delay=2,
    time_limit=settings.SYNC_IMPORT_TIME_LIMIT,
    soft_time_limit=settings.SYNC_IMPORT_TIME_LIMIT - 60,
)
def import_products_task(
    self, sync_log_id: int, raw_items: list[dict], create_missing: bool = True
):
    """Фоновый импорт товаров в уже созданный прогон (для API /products/import|update)."""
    sync_log = SyncLog.objects.get(id=sync_log_id)
    # Идемпотентность (#57): прогон уже финализирован janitor-ом/soft-timeout-ом — не
    # запускаем импорт повторно. Защита от redelivery при acks_late + hard-kill воркера.
    if sync_log.result != SyncLog.SyncResult.RUNNING:
        logger.info(
            "import_products_task: прогон %s уже финализирован (%s) — пропуск.",
            sync_log_id,
            sync_log.result,
        )
        return
    try:
        use_cases.run_import_into(sync_log, raw_items, create_missing=create_missing)
    except (IntegrityError, OperationalError) as exc:
        # Возможна временная гонка (две выгрузки одного code_1c) — импорт идемпотентен,
        # пробуем ещё раз. Очередь onec (-c 1) такие гонки и так исключает; это защита
        # на случай запуска импорта вне очереди.
        if self.request.retries >= _MAX_RETRIES:
            logger.error("import_products_task: исчерпаны ретраи: %s", exc)
            use_cases.fail_import_job(
                sync_log, f"После ретраев: {exc}"[:500], rows_total=len(raw_items)
            )
            raise
        logger.warning("import_products_task: временная ошибка БД, ретрай: %s", exc)
        raise self.retry(exc=exc, countdown=2)  # noqa: B904 — celery.retry поднимает Retry
    except SoftTimeLimitExceeded:
        # Мягкий таймаут (#57): финализируем прогон в ERROR до жёсткого SIGKILL, чтобы
        # он не завис в RUNNING. Пробрасываем — Celery отметит задачу упавшей.
        use_cases.fail_import_job(
            sync_log, "Мягкий таймаут Celery (задача слишком долгая)", rows_total=len(raw_items)
        )
        raise
    except Exception:
        # Жёсткий сбой задачи (не per-row) — не оставлять прогон в RUNNING.
        reason = traceback.format_exc().strip().splitlines()[-1][:500]
        use_cases.fail_import_job(sync_log, reason, rows_total=len(raw_items))
        raise


@shared_task(name="apps.sync_1c.tasks.mark_stale_syncs")
def mark_stale_syncs() -> dict:
    """Janitor (#57): пометить зависшие RUNNING-прогоны импорта как ERROR.

    Уходит в очередь onec по роуту apps.sync_1c.tasks.* (-c 1). Идемпотентна.
    """
    count, uids = use_cases.mark_stale_imports()
    if count:
        logger.warning("mark_stale_syncs: помечено зависших прогонов: %s (%s)", count, uids)
    return {"marked": count, "batch_uids": uids}
