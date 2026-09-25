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
from datetime import timedelta
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from apps.catalog.models import Product

from .models import FulfillmentStatus, Order, OrderItem, PaymentStatus, ReservationStatus

logger = logging.getLogger(__name__)


def _adjust_stock(order: Order, *, available_delta_sign: int) -> None:
    """Применить дельту остатка по всем строкам заказа.

    ``available_delta_sign``: +1 (release, возврат в свободный остаток) или
    0 (confirm, свободный остаток не меняется). ``reserved`` всегда уменьшается.
    """
    # По product_id — в том же порядке, что place_order/rehold берут замки товаров.
    items = (
        OrderItem.objects.filter(order=order)
        .order_by("product_id")
        .values("product_id", "quantity")
    )
    for it in items:
        pid = it["product_id"]
        qty = it["quantity"]
        if pid is None or not qty:
            continue
        update = {"reserved_quantity": models.F("reserved_quantity") - qty}
        if available_delta_sign > 0:
            update["available_quantity"] = models.F("available_quantity") + qty
        Product.objects.filter(pk=pid).update(**update)


def release_reservation(order_id: int, *, only_if_expired: bool = False) -> bool:
    """Вернуть резерв в свободный остаток. Идемпотентно.

    Возвращает True, если резерв был удержан и освобождён; False, если освобождать
    нечего (резерв не в статусе HELD — например, уже released/confirmed/none).

    ``only_if_expired`` — для janitor: срок перепроверяется под замком. Иначе
    между выборкой просроченных и обработкой конкретного заказа покупатель мог
    нажать «Оплатить», rehold продлил срок, а janitor снял бы свежий резерв.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id).first()
        if order is None or order.reservation_status != ReservationStatus.HELD:
            return False
        if only_if_expired and (
            order.reserved_until is None or order.reserved_until >= timezone.now()
        ):
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


def rehold_reservation(order_id: int, *, ttl: timedelta) -> tuple[bool, str]:
    """Удержать товар заново под неоплаченный заказ, чей резерв уже снят.

    Нужен там, где оплата возможна позже 30-минутного окна: ручной расчёт доставки
    занимает часы, и к письму «можно оплатить» janitor уже вернул товар в остаток
    (DRF-2299). Без повторного удержания оплата прошла бы за товар, который мог
    уйти другому покупателю.

    Порядок блокировок: заказ, затем товары строк по id — как place_order держит
    товары под select_for_update. Всё или ничего: если хотя бы одной позиции не
    хватает, остаток не трогаем. Уже HELD — только продлеваем срок (идемпотентно).
    Возвращает (успех, причина отказа).
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id).first()
        if order is None:
            return False, "Заказ не найден"
        if order.payment_status == PaymentStatus.PAID:
            return False, "Заказ уже оплачен"
        if order.fulfillment_status == FulfillmentStatus.CANCELLED:
            return False, "Заказ отменён"
        if order.reservation_status == ReservationStatus.CONFIRMED:
            return False, "Резерв уже списан"

        until = timezone.now() + ttl
        if order.reservation_status == ReservationStatus.HELD:
            order.reserved_until = until
            order.save(update_fields=["reserved_until", "updated_at"])
            return True, ""

        items = list(
            OrderItem.objects.filter(order=order, product_id__isnull=False)
            .exclude(quantity=0)
            .values("product_id", "quantity", "name")
        )
        product_ids = sorted({it["product_id"] for it in items})
        locked = {
            p.pk: p
            for p in Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")
        }
        need: dict[int, Decimal] = {}
        for it in items:
            need[it["product_id"]] = need.get(it["product_id"], Decimal("0")) + Decimal(
                it["quantity"]
            )
        for pid, qty in need.items():
            product = locked.get(pid)
            if product is None or (product.available_quantity or Decimal("0")) < qty:
                name = next(it["name"] for it in items if it["product_id"] == pid)
                return False, f"Товара нет в наличии: {name}"
        for pid, qty in need.items():
            Product.objects.filter(pk=pid).update(
                available_quantity=models.F("available_quantity") - qty,
                reserved_quantity=models.F("reserved_quantity") + qty,
            )
        order.reservation_status = ReservationStatus.HELD
        order.reserved_until = until
        order.save(update_fields=["reservation_status", "reserved_until", "updated_at"])
    logger.info("Reservation re-held for order #%s", order.order_number)
    return True, ""
