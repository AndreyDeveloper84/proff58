"""Подписчики доменных событий заказов (#423, B-03).

При оплате резерв списывается (confirm), при отмене платежа — освобождается
(release). Читаем закоммиченные данные по order_id из payload.
"""

from __future__ import annotations

import logging

from apps.core import events

from .reservation import confirm_reservation, release_reservation

logger = logging.getLogger(__name__)


def _on_payment_succeeded(sender, *, order_id, payment_id=None, **kwargs):
    # Оплата подтверждена → резерв списываем (товар уходит). Идемпотентно.
    confirm_reservation(order_id)


def _on_payment_failed(sender, *, order_id, payment_id=None, reason="", **kwargs):
    # Платёж отменён/просрочен → возвращаем резерв в свободный остаток. Идемпотентно.
    release_reservation(order_id)


def connect() -> None:
    events.payment_succeeded.connect(
        _on_payment_succeeded, dispatch_uid="orders_confirm_reservation"
    )
    events.payment_failed.connect(_on_payment_failed, dispatch_uid="orders_release_reservation")
