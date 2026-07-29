"""Celery-задачи каталога.

Рейтинг «хитов продаж»: факты продаж копятся из двух источников (заказы сайта и
выгрузка 1С), а витрине нужен готовый порядок — пересчёт вынесен в фон.
"""

from __future__ import annotations

import logging

from celery import shared_task

from .sales import purge_old_sales_facts, rebuild_sales_stats

logger = logging.getLogger(__name__)


@shared_task(name="apps.catalog.tasks.rebuild_sales_stats")
def rebuild_sales_stats_task() -> dict[str, int]:
    """Пересобрать рейтинг продаж по фактам за скользящее окно."""
    result = rebuild_sales_stats()
    logger.info("rebuild_sales_stats: %s", result)
    return result


@shared_task(name="apps.catalog.tasks.purge_old_sales_facts")
def purge_old_sales_facts_task() -> int:
    """Подчистить факты продаж, вышедшие далеко за окно рейтинга."""
    deleted = purge_old_sales_facts()
    logger.info("purge_old_sales_facts: удалено %s", deleted)
    return deleted
