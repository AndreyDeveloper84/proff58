"""Идемпотентный сервис резерва склада (#423, B-03).

Единая точка reserve/confirm/release. Инварианты остатка ``Product``:

- ``available_quantity`` — свободный остаток (можно заказать);
- ``reserved_quantity`` — удержано под неисполненные заказы.

Переходы (все под ``select_for_update`` на заказе, идемпотентны по
``Order.reservation_status``):

- **reserve** (при оформлении): ``available -= qty``, ``reserved += qty`` → HELD;
- **release** (отмена/просрочка): ``available += qty``, ``reserved -= qty`` → RELEASED;
- **confirm** (оплата/подтверждение 1С): ``reserved -= qty`` → CONFIRMED
  (``available`` уже уменьшен при резерве — товар физически уходит);
- **rehold** (оплата позже срока, расчёт доставки): RELEASED → HELD заново, если
  товар ещё есть; для HELD — продление срока, только вперёд;
- **confirm_or_take** (оплата пришла): HELD → CONFIRMED; RELEASED у живого заказа →
  товар берётся заново и сразу списывается (``available -= qty``) → CONFIRMED.

Счётчик ``reserved`` ведёт только сайт (заказы) — обмен с 1С его не пишет никогда.
``available`` меняют обе стороны: сайт — удержанием и возвратом, обмен — пересчётом
от данных 1С: «свободно по данным 1С минус ``reserved``», под замком строки товара и
от свежего значения (``apps/sync_1c/stock.py``, DRF-2737). Резерв самой 1С сайт не
хранит. После ``confirm`` резерв сайта списан, и следующая строка остатка от 1С
(до отгрузки там) вернёт проданный товар в ``available`` — известный пробел, задача
в эпике DRF-2731.

Удаление заказа мимо ``release_reservation`` (админка, shell, каскад) закрыто
сигналом ``pre_delete`` в ``receivers.py`` (DRF-1002). Удаление самого товара
резерв не «подвешивает»: ``OrderItem.product`` — SET_NULL, возвращать остаток
некуда, и ``_adjust_stock`` такие строки пропускает.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from apps.catalog.models import Product

from .models import FulfillmentStatus, Order, OrderItem, PaymentStatus, ReservationStatus

logger = logging.getLogger(__name__)

#: Причина отказа rehold: резерв удержан, но срок вышел и продлить его нельзя.
PAY_WINDOW_CLOSED = "Срок оплаты заказа истёк"


def _adjust_stock(order: Order, *, available_delta_sign: int) -> None:
    """Применить дельту остатка по всем строкам заказа.

    ``available_delta_sign``: +1 (release, возврат в свободный остаток) или
    0 (confirm, свободный остаток не меняется). ``reserved`` всегда уменьшается.
    """
    # По product_id — в том же порядке, что берут замки товаров place_order, rehold и
    # обмен с 1С (sync_1c.stock.locked, пакетный импорт, update_stocks_bulk).
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
        if only_if_expired and order.payment_status == PaymentStatus.PAID:
            # Оплата уже зафиксирована, а резерв ещё HELD: списание идёт подписчиком
            # payment_succeeded после коммита. Janitor в этом окне вернул бы в
            # продажу оплаченный товар (DRF-2736).
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


def rehold_reservation(
    order_id: int, *, ttl: timedelta, not_after: datetime | None = None
) -> tuple[bool, str]:
    """Удержать товар заново под неоплаченный заказ, чей резерв уже снят.

    Нужен там, где оплата возможна позже 30-минутного окна: ручной расчёт доставки
    занимает часы, и к письму «можно оплатить» janitor уже вернул товар в остаток
    (DRF-2299). Без повторного удержания оплата прошла бы за товар, который мог
    уйти другому покупателю.

    Порядок блокировок: заказ, затем товары строк по id — как place_order держит
    товары под select_for_update. Всё или ничего: если хотя бы одной позиции не
    хватает, остаток не трогаем. Уже HELD — срок только продлевается, никогда не
    укорачивается: после ручного расчёта доставки удержание 24 часа, и «Оплатить»
    не должно сжимать его до получаса. Возвращает (успех, причина отказа).

    Вердикт выносится под замком заказа — вызывающему не нужно (и нельзя) решать
    по своему снимку, отменён ли заказ и жив ли резерв: между чтением и вызовом
    janitor мог изменить и то и другое.

    ``not_after`` — потолок ПРОДЛЕНИЯ уже удержанного резерва: дальше этого момента
    срок не сдвигается (кнопка «Оплатить» не должна позволять держать товар без
    оплаты бесконечно). На повторное удержание снятого резерва потолок не влияет —
    иначе оплатить заказ, к которому вернулись позже, было бы нельзя вовсе.
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

        now = timezone.now()
        until = now + ttl
        if order.reservation_status == ReservationStatus.HELD:
            if not_after is not None:
                until = min(until, not_after)
            if order.reserved_until is None or order.reserved_until < until:
                order.reserved_until = until
                order.save(update_fields=["reserved_until", "updated_at"])
            if order.reserved_until <= now:
                # Срок вышел, а продлить его уже нельзя (потолок): заказ вот-вот
                # отменит автоматика — отправлять покупателя в кассу нечестно.
                return False, PAY_WINDOW_CLOSED
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
        # Срок — только вперёд: уже назначенный более поздний (сутки на разбор после
        # расчёта доставки) первым же «Оплатить» не сжимается до получаса.
        if order.reserved_until is None or order.reserved_until < until:
            order.reserved_until = until
        order.save(update_fields=["reservation_status", "reserved_until", "updated_at"])
    logger.info("Reservation re-held for order #%s", order.order_number)
    return True, ""


def confirm_or_take(order_id: int) -> bool:
    """Списать товар под оплаченный заказ; если резерв уже снят — взять заново.

    Обычный путь — резерв удержан (HELD): списываем, как ``confirm_reservation``.
    Но оплата может прийти и после снятия резерва, пока заказ ещё жив: покупатель
    проходил 3-D Secure, когда истёк срок, а общий janitor успел вернуть товар в
    остаток; либо резерв сняла отмена прошлой попытки оплаты. Раньше ``confirm`` в
    таком случае молча ничего не делал — получался оплаченный заказ, товар которого
    продаётся дальше (DRF-2736). Теперь товар берётся заново и сразу списывается:
    ``available -= qty`` (``reserved`` не меняется — удержания не было).

    Возвращает False, только когда резерв был снят, а товара уже не хватает:
    остаток не тронут, заказ оплачен без товара — это случай для человека.
    Порядок блокировок тот же, что в ``rehold_reservation``: заказ, затем товары по id.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id).first()
        if order is None:
            return True
        if order.fulfillment_status == FulfillmentStatus.CANCELLED:
            # Отменённый заказ товар не занимает (поздняя оплата — в payments). Если
            # резерв ещё HELD — отмена только что прошла, и его вернёт в остаток она:
            # списать его здесь значило бы потерять товар под заказ, которого нет.
            return True
        if order.reservation_status == ReservationStatus.HELD:
            _adjust_stock(order, available_delta_sign=0)
            order.reservation_status = ReservationStatus.CONFIRMED
            order.save(update_fields=["reservation_status", "updated_at"])
            logger.info("Reservation confirmed for order #%s", order.order_number)
            return True
        if order.reservation_status != ReservationStatus.RELEASED:
            return True  # CONFIRMED или NONE — списывать нечего

        items = list(
            OrderItem.objects.filter(order=order, product_id__isnull=False)
            .exclude(quantity=0)
            .values("product_id", "quantity")
        )
        need: dict[int, Decimal] = {}
        for it in items:
            need[it["product_id"]] = need.get(it["product_id"], Decimal("0")) + Decimal(
                it["quantity"]
            )
        locked = {
            p.pk: p
            for p in Product.objects.select_for_update().filter(pk__in=sorted(need)).order_by("pk")
        }
        for pid, qty in need.items():
            product = locked.get(pid)
            if product is None or (product.available_quantity or Decimal("0")) < qty:
                logger.error(
                    "Order #%s paid after reservation release: stock is gone (product %s)",
                    order.order_number,
                    pid,
                )
                return False
        for pid, qty in need.items():
            Product.objects.filter(pk=pid).update(
                available_quantity=models.F("available_quantity") - qty
            )
        order.reservation_status = ReservationStatus.CONFIRMED
        order.save(update_fields=["reservation_status", "updated_at"])
    logger.info("Reservation re-taken and confirmed for order #%s", order.order_number)
    return True
