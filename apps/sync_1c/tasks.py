"""Celery-задачи синхронизации с 1С.

Тяжёлые/регулярные операции выносятся в фон, чтобы сбои или медлительность
1С не влияли на витрину.
"""

import traceback

from celery import shared_task

from . import parsers, use_cases
from .models import SyncLog


@shared_task
def import_1c_file(path: str, sync_type: str = SyncLog.SyncType.FULL) -> dict:
    """Импортировать выгрузку 1С из файла в фоне."""
    items = parsers.load_items(path)
    sync_log, result = use_cases.import_products(items, source_file=path, sync_type=sync_type)
    return {"batch_uid": str(sync_log.batch_uid), **result.as_dict()}


@shared_task
def import_products_task(sync_log_id: int, raw_items: list[dict], create_missing: bool = True):
    """Фоновый импорт товаров в уже созданный прогон (для API /products/import|update)."""
    sync_log = SyncLog.objects.get(id=sync_log_id)
    try:
        use_cases.run_import_into(sync_log, raw_items, create_missing=create_missing)
    except Exception:
        # Жёсткий сбой задачи (не per-row) — не оставлять прогон в RUNNING.
        reason = traceback.format_exc().strip().splitlines()[-1][:500]
        use_cases.fail_import_job(sync_log, reason, rows_total=len(raw_items))
        raise
