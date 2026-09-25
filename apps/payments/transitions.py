"""Переходы состояния платежа — общие для всех касс.

Логика «что происходит с заказом, когда касса сказала X» не должна зависеть от
того, какая касса это сказала: событие ``order_paid``, блокировка строки заказа
против janitor-а истечения (DRF-952) и разбор поздней оплаты одинаковы для ЮKassa
и АТОЛ Pay. Провайдерные модули отвечают только за перевод своего ответа в
целевой статус, дальше — сюда.

Терминальные статусы не откатываются: подделанный «отменён» после успешной оплаты
не должен ни снимать деньги со счёта заказа, ни размораживать резерв. Возврат —
отдельный путь (``services.refund`` / callback возврата), не «переход назад».
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.core import events
from apps.orders.models import FulfillmentStatus, Order
from apps.orders.models import PaymentStatus as OrderPaymentStatus

from .models import Payment, PaymentStatus

logger = logging.getLogger(__name__)

#: Допустимые переходы по уведомлению кассы.
WEBHOOK_TRANSITIONS: dict[str, set[str]] = {
    PaymentStatus.PENDING: {
        PaymentStatus.WAITING_CAPTURE,
        PaymentStatus.SUCCEEDED,
        PaymentStatus.CANCELED,
    },
    PaymentStatus.WAITING_CAPTURE: {
        PaymentStatus.SUCCEEDED,
        PaymentStatus.CANCELED,
    },
    # Деньги получены: назад пути нет, вперёд — только возврат.
    PaymentStatus.SUCCEEDED: {
        PaymentStatus.PARTIALLY_REFUNDED,
        PaymentStatus.REFUNDED,
    },
    PaymentStatus.PARTIALLY_REFUNDED: {
        PaymentStatus.PARTIALLY_REFUNDED,
        PaymentStatus.REFUNDED,
    },
    PaymentStatus.CANCELED: set(),
    PaymentStatus.REFUNDED: set(),
}


def is_allowed(current: str, target: str) -> bool:
    return target in WEBHOOK_TRANSITIONS.get(current, set())


def apply_succeeded(payment: Payment, *, reference: str, extra_fields: list[str] | None = None):
    """Платёж оплачен: пометить платёж и заказ, издать события после commit.

    Вызывается внутри транзакции, строка платежа уже под ``select_for_update``.
    """
    payment.status = PaymentStatus.SUCCEEDED
    payment.paid_at = timezone.now()
    payment.save(update_fields=["status", "paid_at", *(extra_fields or []), "updated_at"])

    # DRF-952: строку заказа берём под блокировку. Без неё janitor истечения мог
    # в тот же момент отменять этот заказ — получалось «деньги получены, заказ
    # отменён, товар снят с резерва». Теперь одна сторона ждёт другую.
    order = Order.objects.select_for_update().get(pk=payment.order_id)

    if order.fulfillment_status == FulfillmentStatus.CANCELLED:
        # Поздняя оплата: заказ уже отменён по таймауту, товар мог уйти другому
        # покупателю. Молча воскрешать нельзя — денег это не вернёт, а обещание
        # отгрузить создаст. Платёж помечен успешным, случай уходит в лог для
        # ручного разбора (возврат или восстановление заказа).
        logger.error(
            "Поздняя оплата: заказ %s уже отменён, платёж %s на %s %s требует "
            "ручного разбора (возврат или восстановление заказа)",
            order.order_number,
            reference,
            payment.amount,
            payment.currency,
        )
        return

    order.payment_status = OrderPaymentStatus.PAID
    order.save(update_fields=["payment_status", "updated_at"])

    order_id = payment.order_id
    payment_id = payment.id
    # #431 (M-07): публикуем ОБА события после commit. payment_succeeded —
    # платёжный слой (orders confirm резерва); order_paid — доменное событие
    # оплаты, на которое подписаны MAX/analytics/CRM. Идемпотентность — гейт
    # перехода: сюда доходят только реальные переходы, не повторы.
    transaction.on_commit(
        lambda: events.payment_succeeded.send(
            sender=Payment, payment_id=payment_id, order_id=order_id
        )
    )
    transaction.on_commit(
        lambda: events.order_paid.send(sender=Payment, order_id=order_id, payment_id=payment_id)
    )
    logger.info("Платёж %s оплачен, заказ %s", reference, order.order_number)


def apply_canceled(payment: Payment, *, reason: str, reference: str, extra_fields=None):
    """Оплата не состоялась: платёж отменён кассой или банком."""
    payment.status = PaymentStatus.CANCELED
    payment.save(update_fields=["status", *(extra_fields or []), "updated_at"])

    order_id = payment.order_id
    payment_id = payment.id
    transaction.on_commit(
        lambda: events.payment_failed.send(
            sender=Payment, payment_id=payment_id, order_id=order_id, reason=reason
        )
    )
    logger.info("Платёж %s отменён: %s", reference, reason)


def apply_waiting_capture(payment: Payment, *, extra_fields=None):
    payment.status = PaymentStatus.WAITING_CAPTURE
    payment.save(update_fields=["status", *(extra_fields or []), "updated_at"])


def apply_refunded(
    payment: Payment, *, refund_amount, full: bool, reference: str, extra_fields=None
):
    """Деньги вернулись покупателю — по нашей команде или из ЛК кассы.

    Ledger-строку возврата пишем в обоих случаях: возврат, сделанный менеджером
    в личном кабинете кассы, — такое же движение денег, и без строки суммы по
    заказу перестают сходиться, а уведомление покупателю теряет ключ
    идемпотентности (ADR-0009: ключ — конкретная операция, а не заказ).

    Идентификатора операции возврата касса не присылает, поэтому ключ строки
    собирается из платежа, суммы и полноты возврата: повторная доставка того же
    уведомления не создаёт вторую строку и не шлёт второе уведомление. Плата за
    это — два одинаковых по сумме частичных возврата по одному платежу сольются
    в один; в ЛК кассы они видны раздельно.
    """
    from decimal import Decimal

    from .models import Refund, RefundStatus

    amount = Decimal(str(refund_amount or "0"))
    key = f"callback-{reference}-{'full' if full else 'part'}-{amount}"
    rec, created = Refund.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "payment": payment,
            "amount": amount,
            "currency": payment.currency,
            "status": RefundStatus.SUCCEEDED,
        },
    )

    payment.status = PaymentStatus.REFUNDED if full else PaymentStatus.PARTIALLY_REFUNDED
    payment.save(update_fields=["status", *(extra_fields or []), "updated_at"])

    order_status = OrderPaymentStatus.REFUNDED if full else OrderPaymentStatus.PARTIALLY_REFUNDED
    Order.objects.filter(pk=payment.order_id).update(payment_status=order_status)

    if not created:
        # Повтор уведомления: статусы уже такие, второй раз покупателя не тревожим.
        return rec

    order_id = payment.order_id
    payment_id = payment.id
    refund_id = rec.pk
    transaction.on_commit(
        lambda: events.payment_refunded.send(
            sender=Payment,
            payment_id=payment_id,
            order_id=order_id,
            refund_id=refund_id,
            amount=str(amount),
            is_full=full,
        )
    )
    logger.info(
        "Возврат по платежу %s: %s %s (полный: %s)", reference, amount, payment.currency, full
    )
    return rec
