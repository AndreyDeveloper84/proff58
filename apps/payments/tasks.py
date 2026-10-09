"""Celery-задачи оплаты (DRF-952)."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="apps.payments.tasks.expire_unpaid_online_orders")
def expire_unpaid_online_orders(limit: int = 500) -> int:
    """Отменить онлайн-заказы с истёкшим резервом и неподтверждённой оплатой.

    Перед отменой каждый заказ сверяется с кассой — вебхук мог не дойти.
    Возвращает число отменённых.

    Тем же прогоном — заказы «отменён, оплата получена» без заявки на возврат
    (DRF-2736): заявка заводится автоматически одной попыткой, и если та сорвалась,
    о деньгах покупателя иначе не узнал бы никто.
    """
    from .expiry import expire_unpaid_online_orders as run
    from .refund_requests import heal_missing_requests

    expired = run(limit=limit)
    try:
        heal_missing_requests()
    except Exception:  # noqa: BLE001 — отмены уже сделаны, их счёт терять нельзя
        logger.exception("heal_missing_requests: проход не выполнен")
    return expired


@shared_task(name="apps.payments.tasks.cleanup_old_webhook_payloads")
def cleanup_old_webhook_payloads() -> int:
    """Clear retained callback snapshots after the configured privacy window.

    Payment ledger and structured provider/receipt fields remain untouched.
    """
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from .models import Payment

    days = getattr(settings, "PAYMENT_WEBHOOK_RAW_RETENTION_DAYS", 30)
    cutoff = timezone.now() - timedelta(days=days)
    qs = Payment.objects.exclude(webhook_payload={}).filter(webhook_payload_at__lt=cutoff)
    count = qs.count()
    if count:
        qs.update(webhook_payload={}, webhook_payload_at=None)
    logger.info("cleanup_old_webhook_payloads: cleared=%d", count)
    return count
