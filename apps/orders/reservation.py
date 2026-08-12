"""Идемпотентный сервис резерва склада (#423, B-03).

Единая точка reserve/confirm/release. Инварианты остатка ``Product``:

- ``available_quantity`` — свободный остаток (можно заказать);
- ``reserved_quantity`` — удержано под неисполненные заказы.

Переходы (все под ``select_for_update`` на заказе, идемпотентны по
``Order.reservation_status``):

- **reserve** (при оформлении): ``available -= qty``, ``reserved += qty`` → HELD;
- **release** (отмена/просрочка): ``available += qty``, ``reserved -= qty`` → RELEASED;
- **confirm** (оплата/подтверждение 1С): ``reserved -= qty`` → CONFIRMED
  (``available`` уже уменьшен при резерве — товар физически уходит).

Мастер ``available``/``reserved`` на сайте — сайт. Обмен 1С присылает абсолютный
свободный остаток (``stocks/update``), перезаписывая ``available``; ``reserved``
остаётся сайтовым счётчиком. Полная сверка reserved с 1С — вне объёма B-03.

Удаление заказа мимо ``release_reservation`` (админка, shell, каскад) закрыто
сигналом ``pre_delete`` в ``receivers.py`` (DRF-1002). Удаление самого товара
резерв не «подвешивает»: ``OrderItem.product`` — SET_NULL, возвращать остаток
некуда, и ``_adjust_stock`` такие строки пропускает.
"""

from __future__ import annotations

import logging

from django.db import models, transaction

from apps.catalog.models import Product

from .models import Order, OrderItem, ReservationStatus

logger = logging.getLogger(__name__)


def _adjust_stock(order: Order, *, available_delta_sign: int) -> None:
    """Применить дельту остатка по всем строкам заказа.

    ``available_delta_sign``: +1 (release, возврат в свободный остаток) или
    0 (confirm, свободный остаток не меняется). ``reserved`` всегда уменьшается.
    """
    items = OrderItem.objects.filter(order=order).values("product_id", "quantity")
    for it in items:
        pid = it["product_id"]
        qty = it["quantity"]
        if pid is None or not qty:
            continue
        update = {"reserved_quantity": models.F("reserved_quantity") - qty}
        if available_delta_sign > 0:
            update["available_quantity"] = models.F("available_quantity") + qty
        Product.objects.filter(pk=pid).update(**update)


def release_reservation(order_id: int) -> bool:
    """Вернуть резерв в свободный остаток. Идемпотентно.

    Возвращает True, если резерв был удержан и освобождён; False, если освобождать
    нечего (резерв не в статусе HELD — например, уже released/confirmed/none).
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id).first()
        if order is None or order.reservation_status != ReservationStatus.HELD:
            return False
        _adjust_stock(order, available_delta_sign=+1)
        order.reservation_status = ReservationStatus.RELEASED
        order.save(update_fields=["reservation_status", "updated_at"])
    logger.info("Reservation released for order #%s", order.order_number)
    return True


def confirm_reservation(order_id: int) -> bool:
    """Списать резерв (товар ушёл). Идемпотентно.

    Возвращает True, если резерв был удержан и списан; False иначе.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id).first()
        if order is None or order.reservation_status != ReservationStatus.HELD:
            return False
        _adjust_stock(order, available_delta_sign=0)
        order.reservation_status = ReservationStatus.CONFIRMED
        order.save(update_fields=["reservation_status", "updated_at"])
    logger.info("Reservation confirmed for order #%s", order.order_number)
    return True
