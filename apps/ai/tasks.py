# apps/ai/tasks.py
"""Celery-runtime обогащения (ARCHITECTURE-AI §5, runtime-срез)."""
from __future__ import annotations

import datetime as _dt

from celery import shared_task
from django.utils import timezone

from apps.catalog.enrichment import pending_for_enrichment
from apps.core.features import is_enabled

from . import services
from .models import ExternalCall, SourcingRun
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


# --- sourcing tasks ---


def _sourcing_enabled() -> bool:
    return is_enabled("ai") and is_enabled("ai_sourcing") and is_enabled("external_integrations")


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def source_product_task(self, product_id, idempotency_key):
    if not _sourcing_enabled():
        return "disabled"
    try:
        services.source_content(product_id=product_id, idempotency_key=idempotency_key)
    except Exception as exc:  # noqa: BLE001
        # Прогон идемпотентен (get_or_create по idempotency_key, skip по ExternalCall(ok)),
        # поэтому повтор инфра-сбоя безопасен. Ошибки конкретных источников гасятся внутри
        # source_content (изоляция адаптера) и сюда не доходят — здесь только инфра/непредвиденное.
        raise self.retry(exc=exc) from exc
    return idempotency_key


@shared_task(name="apps.ai.tasks.batch_source_task")
def batch_source_task(category_slug=None, limit=100):
    if not _sourcing_enabled():
        return 0
    from apps.catalog.enrichment import pending_for_enrichment

    ids = pending_for_enrichment(category_slug=category_slug, limit=limit)
    for pid in ids:
        source_product_task.delay(pid, f"batch:{category_slug or 'all'}:{pid}")
    return len(ids)


@shared_task
def mark_stale_sourcing_runs(older_than_minutes=60):
    cutoff = timezone.now() - _dt.timedelta(minutes=older_than_minutes)
    stale = SourcingRun.objects.filter(status=SourcingRun.Status.RUNNING, created_at__lt=cutoff)
    n = 0
    for run in stale:
        ExternalCall.objects.filter(run=run, status=ExternalCall.Status.RUNNING).update(
            status=ExternalCall.Status.UNKNOWN
        )  # резерв НЕ снимаем — нужна сверка
        run.status = SourcingRun.Status.ERROR
        run.save()
        n += 1
    return n


@shared_task
def purge_sourcing_excerpts(older_than_days=30):
    cutoff = timezone.now() - _dt.timedelta(days=older_than_days)
    return (
        ExternalCall.objects.filter(created_at__lt=cutoff)
        .exclude(raw_excerpt="")
        .update(raw_excerpt="")
    )
