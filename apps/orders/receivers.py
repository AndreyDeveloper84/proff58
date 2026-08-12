"""Подписчики доменных событий заказов (#423, B-03).

При оплате резерв списывается (confirm), при отмене платежа — освобождается
(release). Читаем закоммиченные данные по order_id из payload.

Отдельно — `pre_delete` на самом заказе (DRF-1002): резерв обязан сниматься на
уровне модели, а не конкретного вызова, иначе удаление мимо `release_reservation`
оставляет остаток занятым навсегда.
"""

from __future__ import annotations

import logging

from django.db.models.signals import pre_delete

from apps.core import events

from .models import Order
from .reservation import confirm_reservation, release_reservation

logger = logging.getLogger(__name__)


def _on_payment_succeeded(sender, *, order_id, payment_id=None, **kwargs):
    # Оплата подтверждена → резерв списываем (товар уходит). Идемпотентно.
    confirm_reservation(order_id)


def _on_payment_failed(sender, *, order_id, payment_id=None, reason="", **kwargs):
    # Платёж отменён/просрочен → возвращаем резерв в свободный остаток. Идемпотентно.
    release_reservation(order_id)


def _on_order_pre_delete(sender, instance, **kwargs):
    """Удаляют заказ — возвращаем удержанный остаток (DRF-1002).

    Ловит любой путь удаления: админка, shell, каскад. Сигнал сам отключает
    fast-delete (Django загрузит объекты и разошлёт сигналы вместо одного DELETE),
    а строки заказа на момент pre_delete ещё в базе — резерв есть что вернуть.
    Идемпотентно: для RELEASED/CONFIRMED вызов ничего не делает.
    """
    release_reservation(instance.pk)


def connect() -> None:
    events.payment_succeeded.connect(
        _on_payment_succeeded, dispatch_uid="orders_confirm_reservation"
    )
    events.payment_failed.connect(_on_payment_failed, dispatch_uid="orders_release_reservation")
    pre_delete.connect(
        _on_order_pre_delete, sender=Order, dispatch_uid="orders_release_reservation_on_delete"
    )
