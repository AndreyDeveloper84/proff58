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
