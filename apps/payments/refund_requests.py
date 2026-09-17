"""Заявки покупателей на возврат денег.

Покупатель не возвращает деньги сам: он подаёт заявку, менеджер её рассматривает
и оформляет возврат через кассу (``services.refund``) или отклоняет с причиной.
Правила (решение владельца от 17.09.2026):

* заявка — только по заказу, оплаченному онлайн, пока деньги возвращены не
  полностью;
* принимается до получения заказа и 14 дней после него;
* одна открытая заявка на заказ;
* товар на склад возвращает 1С, сайт остатки не трогает.
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

    # Канала уведомлений менеджеров на сайте пока нет — заметная строка в логе,
    # сама заявка видна в админке «Платежи → Заявки на возврат».
    logger.warning("Заявка на возврат #%s по заказу %s: %s", request.pk, order.order_number, reason)
    return request


def approve(request_id: int, *, amount: Decimal | None, actor_id: int | None) -> RefundRequest:
    """Вернуть деньги по заявке. amount=None — весь остаток платежа.

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
