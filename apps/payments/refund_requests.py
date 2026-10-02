"""Заявки покупателей на возврат денег.

Покупатель не возвращает деньги сам: он подаёт заявку, менеджер её рассматривает
и оформляет возврат через кассу (``services.refund``) или отклоняет с причиной.
Правила (решение владельца от 17.09.2026):

* заявка — только по заказу, оплаченному онлайн, пока деньги возвращены не
  полностью;
* принимается до получения заказа и 14 дней после него;
* одна открытая заявка на заказ;
* товар на склад возвращает 1С, сайт остатки не трогает.

Отдельный случай — отменённый заказ, за который получены деньги (DRF-2736):
оплата пришла после отмены (страница оплаты у кассы живёт дольше резерва) либо
заказ отменили уже оплаченным. Товара покупатель не получит, поэтому заявку за
него подаёт сам сайт (``ensure_request_for_cancelled``). Решает её по-прежнему
менеджер; отказ и частичная сумма не запрещены (деньги могли вернуть в кабинете
кассы, доставку могли удержать по договорённости), но админка о них
предупреждает: у гостя нет способа подать заявку заново.

Заявки никто не удаляет (в админке удаление закрыто), а заказ «отменён, оплачен»
вовсе без заявки находит и чинит ``heal_missing_requests``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core import events
from apps.orders.models import FulfillmentStatus, Order
from apps.orders.models import PaymentStatus as OrderPaymentStatus

from . import services
from .models import (
    Payment,
    PaymentStatus,
    RefundReason,
    RefundRequest,
    RefundRequestStatus,
)

logger = logging.getLogger(__name__)

# Срок заявки после получения заказа — как срок возврата товара по закону.
REFUND_WINDOW = timedelta(days=14)

REFUNDABLE_ORDER = frozenset({OrderPaymentStatus.PAID, OrderPaymentStatus.PARTIALLY_REFUNDED})
_REFUNDABLE_PAYMENT = (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED)
_OPEN = (RefundRequestStatus.PENDING, RefundRequestStatus.PROCESSING)

#: Комментарии автоматических заявок — их видят и менеджер, и покупатель.
LATE_PAYMENT_COMMENT = "Оплата поступила после отмены заказа. Заявка создана автоматически."
CANCELLED_PAID_COMMENT = "Заказ отменён после оплаты. Заявка создана автоматически."
SECOND_PAYMENT_COMMENT = (
    "По отменённому заказу есть ещё один оплаченный платёж. Заявка создана автоматически."
)
HEALED_COMMENT = "Заказ отменён, оплата получена, заявки не было. Заявка создана автоматически."


def refundable_payment(order: Order) -> Payment | None:
    """Платёж, по которому ещё можно вернуть деньги (последний успешный)."""
    return (
        Payment.objects.filter(order=order, status__in=_REFUNDABLE_PAYMENT)
        .order_by("-created_at")
        .first()
    )


def remaining_amount(payment: Payment) -> Decimal:
    """Сколько ещё можно вернуть по платежу."""
    return payment.amount - services._refunded_total(payment.pk)


def request_deadline(order: Order) -> datetime | None:
    """До какого момента принимается заявка; None — пока заказ не получен."""
    if order.fulfillment_status != FulfillmentStatus.COMPLETED:
        return None
    # Заказы, выполненные до появления поля, считаем от последнего изменения.
    return (order.completed_at or order.updated_at) + REFUND_WINDOW


def block_reason(order: Order, *, now: datetime | None = None) -> str | None:
    """Почему заявку подать нельзя; None — можно.

    Текст показывается покупателю как есть.
    """
    if order.payment_status not in REFUNDABLE_ORDER:
        return "Вернуть деньги можно только за заказ, оплаченный онлайн."
    if refundable_payment(order) is None:
        return "Платёж по заказу не найден — позвоните нам, разберёмся."
    deadline = request_deadline(order)
    if deadline is not None and (now or timezone.now()) > deadline:
        return (
            "Прошло больше 14 дней после получения заказа — заявку на сайте подать "
            "нельзя. Позвоните нам, разберёмся."
        )
    if RefundRequest.objects.filter(order=order, status__in=_OPEN).exists():
        return "Заявка на возврат уже на рассмотрении."
    return None


def must_refund_in_full(order: Order) -> bool:
    """Заказ отменён, а деньги за него ещё у магазина — вернуть нужно всё."""
    return (
        order.fulfillment_status == FulfillmentStatus.CANCELLED
        and order.payment_status in REFUNDABLE_ORDER
    )


def ensure_request_for_cancelled(order_id: int, *, comment: str) -> RefundRequest | None:
    """Завести заявку на возврат по отменённому заказу с полученной онлайн-оплатой.

    Без заявки про такие деньги знала бы одна строка лога: в админке вернуть их
    можно только кнопкой заявки, а гость подать её не может вовсе. None — заявка
    не нужна (заказ не отменён, денег нет, оплата не через кассу) либо уже открыта.
    """
    order = Order.objects.filter(pk=order_id).first()
    if order is None or not must_refund_in_full(order):
        return None
    if refundable_payment(order) is None:
        # Оплата не через кассу (счёт организации): возвращать кнопкой нечего.
        return None
    try:
        return create_request(
            order_id, user_id=order.user_id, reason=RefundReason.OTHER, comment=comment
        )
    except ValidationError as exc:
        logger.info(
            "Заказ %s: автозаявка на возврат не создана — %s",
            order.order_number,
            "; ".join(exc.messages),
        )
        return None


def heal_missing_requests(limit: int = 100) -> int:
    """Завести заявку заказам «отменён, оплата получена», у которых её нет вовсе.

    Автозаявка создаётся одной попыткой — в момент поздней оплаты или отмены. Если
    попытка сорвалась (сбой БД, упавший подписчик) или заказ отменили оплаченным ещё
    до появления этой автоматики, деньги остаются без единой заявки, а гость подать
    её не может. Проход дешёвый, идёт вместе с janitor'ом истечения.

    Только заказы без ЕДИНОЙ заявки: отклонённая или закрытая частичным возвратом —
    решение менеджера, с ним не спорим.
    """
    ids = list(
        Order.objects.filter(
            fulfillment_status=FulfillmentStatus.CANCELLED,
            payment_status__in=REFUNDABLE_ORDER,
            payments__status__in=_REFUNDABLE_PAYMENT,
            refund_requests__isnull=True,
        )
        .order_by("id")
        .values_list("pk", flat=True)
        .distinct()[:limit]
    )
    healed = 0
    for order_id in ids:
        try:
            if ensure_request_for_cancelled(order_id, comment=HEALED_COMMENT) is not None:
                healed += 1
        except Exception:  # noqa: BLE001 — один заказ не должен остановить проход
            logger.exception("Заказ %s: не удалось завести заявку на возврат", order_id)
    if healed:
        logger.warning("heal_missing_requests: заведено заявок на возврат — %s", healed)
    return healed


def create_request(
    order_id: int, *, user_id: int | None, reason: str, comment: str = ""
) -> RefundRequest:
    """Принять заявку покупателя. ValidationError — с текстом для покупателя."""
    if reason not in RefundReason.values:
        raise ValidationError("Выберите причину возврата.")
    comment = (comment or "").strip()
    if reason == RefundReason.OTHER and not comment:
        raise ValidationError("Опишите, пожалуйста, причину возврата.")

    with transaction.atomic():
        # Блокировка заказа: две одновременные заявки не проскочат проверку.
        order = Order.objects.select_for_update().get(pk=order_id)
        blocked = block_reason(order)
        if blocked:
            raise ValidationError(blocked)
        request = RefundRequest.objects.create(
            order=order, user_id=user_id, reason=reason, comment=comment[:1000]
        )
        transaction.on_commit(
            lambda rid=request.pk, oid=order.pk: events.refund_requested.send(
                sender=RefundRequest, request_id=rid, order_id=oid
            )
        )

    # Письмо менеджерам уходит по событию refund_requested (receivers.py, T2);
    # строка в логе остаётся на случай ненастроенных получателей.
    logger.info("Заявка на возврат #%s по заказу %s: %s", request.pk, order.order_number, reason)
    return request


def approve(request_id: int, *, amount: Decimal | None, actor_id: int | None) -> RefundRequest:
    """Вернуть деньги по заявке. amount=None — весь остаток платежа (так его понимает
    и ``services.refund``).

    Вызов кассы идёт вне транзакции (как в ``services.refund``), поэтому заявка
    сначала переводится в «Оформляется возврат»: повторное нажатие менеджера
    второй возврат не создаст.
    """
    with transaction.atomic():
        request = RefundRequest.objects.select_for_update().get(pk=request_id)
        if request.status != RefundRequestStatus.PENDING:
            raise ValidationError(f"Заявка уже в статусе «{request.get_status_display()}».")
        payment = refundable_payment(request.order)
        if payment is None:
            raise ValidationError("У заказа нет платежа, по которому можно вернуть деньги.")
        request.status = RefundRequestStatus.PROCESSING
        request.save(update_fields=["status", "updated_at"])

    try:
        refund = services.refund(payment, amount)
    except Exception as exc:
        RefundRequest.objects.filter(pk=request_id).update(status=RefundRequestStatus.PENDING)
        if isinstance(exc, ValueError):
            raise ValidationError(str(exc)) from exc
        logger.exception("Возврат по заявке #%s не прошёл", request_id)
        raise ValidationError(
            "Касса не приняла возврат. Заявка осталась на рассмотрении — "
            "попробуйте позже или оформите возврат в личном кабинете кассы."
        ) from exc

    request.status = RefundRequestStatus.REFUNDED
    request.refund = refund
    request.decided_by_id = actor_id
    request.decided_at = timezone.now()
    request.save(update_fields=["status", "refund", "decided_by", "decided_at", "updated_at"])
    logger.info("Заявка на возврат #%s: возвращено %s", request.pk, refund.amount)

    # У отменённого заказа мог быть второй оплаченный платёж (обе страницы оплаты
    # сработали). Заявка закрыта возвратом одного — второй не должен пропасть из виду.
    other = refundable_payment(request.order)
    if other is not None and other.pk != payment.pk:
        ensure_request_for_cancelled(request.order_id, comment=SECOND_PAYMENT_COMMENT)
    return request


def reject(request_id: int, *, comment: str, actor_id: int | None) -> RefundRequest:
    """Отклонить заявку. Причина обязательна — её увидит покупатель."""
    comment = (comment or "").strip()
    if not comment:
        raise ValidationError("Напишите покупателю, почему заявка отклонена.")
    with transaction.atomic():
        request = RefundRequest.objects.select_for_update().get(pk=request_id)
        if request.status != RefundRequestStatus.PENDING:
            raise ValidationError(f"Заявка уже в статусе «{request.get_status_display()}».")
        request.status = RefundRequestStatus.REJECTED
        request.decision_comment = comment
        request.decided_by_id = actor_id
        request.decided_at = timezone.now()
        request.save(
            update_fields=["status", "decision_comment", "decided_by", "decided_at", "updated_at"]
        )
    logger.info("Заявка на возврат #%s отклонена (менеджер id=%s)", request.pk, actor_id)
    return request
