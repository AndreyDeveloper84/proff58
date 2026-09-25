"""Celery-задачи оплаты (DRF-952)."""

from __future__ import annotations

from celery import shared_task


@shared_task(name="apps.payments.tasks.expire_unpaid_online_orders")
def expire_unpaid_online_orders(limit: int = 500) -> int:
    """Отменить онлайн-заказы с истёкшим резервом и неподтверждённой оплатой.

    Перед отменой каждый заказ сверяется с кассой — вебхук мог не дойти.
    Возвращает число отменённых.
    """
    from .expiry import expire_unpaid_online_orders as run

    return run(limit=limit)
