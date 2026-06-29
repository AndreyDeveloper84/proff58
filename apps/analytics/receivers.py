"""Обработчики доменных сигналов для записи аналитических событий.

Подключаются в ``AnalyticsConfig.ready()`` только при включённом флаге
``analytics``.
"""

from __future__ import annotations

from apps.core.events import order_created, order_paid

from .models import EventType
from .services import track


def _on_order_created(sender, *, order_id, **kwargs):
    track(
        EventType.ORDER_CREATED,
        payload={"order_id": order_id},
    )


def _on_order_paid(sender, *, order_id, payment_id, **kwargs):
    track(
        EventType.PAYMENT_SUCCESS,
        payload={"order_id": order_id, "payment_id": payment_id},
    )


order_created.connect(_on_order_created, dispatch_uid="analytics_order_created")
order_paid.connect(_on_order_paid, dispatch_uid="analytics_order_paid")
