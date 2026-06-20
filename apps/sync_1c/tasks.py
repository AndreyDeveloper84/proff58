"""Celery-задачи синхронизации с 1С.

Тяжёлые/регулярные операции выносятся в фон, чтобы сбои или медлительность
1С не влияли на витрину. Все задачи маршрутизируются в очередь `onec`
(settings.CELERY_TASK_ROUTES), worker которой запускается с concurrency=1 — обмены идут
строго последовательно (#126), что снимает гонку «одна актуальная цена».
"""

import logging
import traceback

from celery import shared_task
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


@shared_task(bind=True, acks_late=True, max_retries=_MAX_RETRIES, default_retry_delay=2)
def import_products_task(
    self, sync_log_id: int, raw_items: list[dict], create_missing: bool = True
):
    """Фоновый импорт товаров в уже созданный прогон (для API /products/import|update)."""
    sync_log = SyncLog.objects.get(id=sync_log_id)
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
    except Exception:
        # Жёсткий сбой задачи (не per-row) — не оставлять прогон в RUNNING.
        reason = traceback.format_exc().strip().splitlines()[-1][:500]
        use_cases.fail_import_job(sync_log, reason, rows_total=len(raw_items))
        raise
