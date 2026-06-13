"""Celery-задачи синхронизации с 1С.

Тяжёлые/регулярные операции выносятся в фон, чтобы сбои или медлительность
1С не влияли на витрину.
"""

from celery import shared_task

from . import importer, parsers
from .models import SyncLog


@shared_task
def import_1c_file(path: str, sync_type: str = SyncLog.SyncType.FULL) -> dict:
    """Импортировать выгрузку 1С из файла в фоне."""
    items = parsers.load_items(path)
    sync_log, result = importer.run_import(items, sync_type=sync_type, source_file=path)
    return {"batch_uid": str(sync_log.batch_uid), **result.as_dict()}
