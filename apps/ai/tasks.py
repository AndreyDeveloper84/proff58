# apps/ai/tasks.py
"""Celery-runtime обогащения (ARCHITECTURE-AI §5, runtime-срез)."""
from __future__ import annotations

from celery import shared_task

from apps.catalog.enrichment import pending_for_enrichment

from .services import enrich


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def enrich_product_task(self, product_id: int, force: bool = False):
    enrich(product_id=product_id, force=force)


@shared_task
def batch_enrich_task(
    category_slug: str | None = None, limit: int = 100, only_empty: bool = True
) -> int:
    ids = pending_for_enrichment(category_slug=category_slug, limit=limit, only_empty=only_empty)
    for pid in ids:
        enrich_product_task.delay(pid)
    return len(ids)
