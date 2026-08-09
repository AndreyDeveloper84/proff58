"""Истечение неоплаченных онлайн-заказов (DRF-952).

Заказ с онлайн-оплатой держит товар 30 минут. Не оплатили — заказ отменяется,
резерв снимается, товар возвращается в продажу.

Почему это живёт в ``payments``, а не в ``orders``: перед отменой надо спросить
кассу, не прошла ли оплата на самом деле. Вебхук может не дойти — сеть, 5xx,
ретраи ЮKassa, — и тогда локальный ``payment_status`` врёт. Отменить оплаченный
заказ хуже, чем подержать резерв лишнюю минуту, поэтому последнее слово всегда
за провайдером. ``orders`` про кассу знать не должен (CLAUDE.md §4), а
``payments`` про заказы уже знает.

Существующий janitor ``orders.tasks.release_expired_reservations`` продолжает
работать и снимает резерв у любых просроченных заказов — включая те, что оплату
не предполагают. Здесь же именно онлайн-оплата: отмена заказа + возврат товара.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.orders.models import FulfillmentStatus, Order
from apps.orders.models import PaymentStatus as OrderPaymentStatus
from apps.orders.reservation import release_reservation

from .models import Payment, PaymentStatus
from .services import _yookassa_request

logger = logging.getLogger(__name__)

# Способ оплаты в заказе — снимок выбора на витрине (см. payments/api.py).
ONLINE_PAYMENT_METHOD = "online"

# Автоматика отменяет только то, за что ещё никто не взялся. Матрица переходов
# разрешает отмену и из «Собирается», и из «В доставке» — но это решение
# менеджера при возврате, а не повод роботу отменить заказ, который склад уже
# везёт. Просроченная оплата у такого заказа — случай для человека.
CANCELLABLE_BY_TIMEOUT = frozenset({FulfillmentStatus.NEW, FulfillmentStatus.CONFIRMED})


def _provider_says_paid(payment: Payment) -> bool:
    """Спросить кассу напрямую: деньги пришли?

    Любая ошибка запроса трактуется как «не знаем» → возвращаем False, но
    вызывающий на этом не отменяет заказ (см. expire_one): без ответа кассы
    отмену откладываем до следующего прогона. Молчание провайдера не повод
    отдавать чужой товар.
    """
    if not payment.yookassa_id:
        return False
    data = _yookassa_request("GET", f"payments/{payment.yookassa_id}")
    return bool(data.get("paid")) and data.get("status") == "succeeded"


def expire_one(order_id: int) -> bool:
    """Истечь один онлайн-заказ. Атомарно и идемпотентно.

    True — заказ отменён здесь. False — отменять нечего или нельзя (уже оплачен,
    уже отменён, касса не ответила).
    """
    now = timezone.now()

    # Касса — внешний вызов, его нельзя держать внутри транзакции с блокировкой
    # строки: ответ ЮKassa занимает сотни миллисекунд, а заказ всё это время был
    # бы заблокирован для вебхука. Спрашиваем до транзакции, состояние
    # перепроверяем внутри неё.
    payment = (
        Payment.objects.filter(order_id=order_id)
        .exclude(status__in=[PaymentStatus.CANCELED, PaymentStatus.REFUNDED])
        .order_by("-id")
        .first()
    )
    if payment is not None:
        try:
            if _provider_says_paid(payment):
                logger.warning(
                    "Заказ %s: касса подтвердила оплату, отмена отменяется — "
                    "вебхук, судя по всему, не дошёл",
                    order_id,
                )
                return False
        except Exception:
            logger.exception(
                "Заказ %s: касса не ответила, отмену откладываем до следующего прогона",
                order_id,
            )
            return False

    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .filter(
                pk=order_id,
                payment_method=ONLINE_PAYMENT_METHOD,
                payment_status=OrderPaymentStatus.PENDING,
                reserved_until__lt=now,
            )
            .first()
        )
        if order is None:
            # Оплатили, отменили или продлили резерв, пока мы ходили в кассу.
            return False

        if order.fulfillment_status not in CANCELLABLE_BY_TIMEOUT:
            # Заказ уже в работе у склада — робот его не отменяет. Резерв тоже
            # не трогаем: товар физически готовят к выдаче.
            logger.warning(
                "Заказ %s просрочен по оплате, но статус %s — отмену решает менеджер",
                order.order_number,
                order.fulfillment_status,
            )
            return False

        order.payment_status = OrderPaymentStatus.EXPIRED
        order.fulfillment_status = FulfillmentStatus.CANCELLED
        order.save(update_fields=["payment_status", "fulfillment_status", "updated_at"])

    # Резерв снимаем ПОСЛЕ фиксации отмены и своей транзакцией: release_reservation
    # берёт ту же строку под select_for_update и идемпотентен, так что двойного
    # возврата остатков не будет, даже если janitor заказов успел раньше.
    release_reservation(order_id)
    logger.info("Заказ %s отменён: оплата не поступила в срок", order.order_number)
    return True


def expire_unpaid_online_orders(limit: int = 500) -> int:
    """Отменить онлайн-заказы, у которых истёк резерв, а оплата не пришла."""
    now = timezone.now()
    ids = list(
        Order.objects.filter(
            payment_method=ONLINE_PAYMENT_METHOD,
            payment_status=OrderPaymentStatus.PENDING,
            reserved_until__lt=now,
        )
        .exclude(fulfillment_status=FulfillmentStatus.CANCELLED)
        .order_by("reserved_until")
        .values_list("pk", flat=True)[:limit]
    )
    expired = sum(1 for order_id in ids if expire_one(order_id))
    if expired:
        logger.info("expire_unpaid_online_orders: отменено заказов — %s", expired)
    return expired
