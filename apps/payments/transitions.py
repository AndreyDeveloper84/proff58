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


def order_status_after_refund(order_id: int, *, payment_id: int, full: bool) -> str:
    """Статус оплаты заказа после возврата по одному платежу — с оглядкой на остальные.

    Обычно оплаченный платёж у заказа один, и «платёж возвращён полностью» значит
    «по заказу возвращено всё». Но оплатить могут и два платежа одного заказа
    (двойное нажатие дало второй ``orderId``, обе страницы оплатили). Тогда полный
    возврат одного — ещё не «возвращено»: раньше заказ становился ``refunded``, и
    деньги второго платежа пропадали из виду (DRF-2736).
    """
    if not full:
        return OrderPaymentStatus.PARTIALLY_REFUNDED
    money_left = (
        Payment.objects.filter(
            order_id=order_id,
            status__in=(PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED),
        )
        .exclude(pk=payment_id)
        .exists()
    )
    return OrderPaymentStatus.PARTIALLY_REFUNDED if money_left else OrderPaymentStatus.REFUNDED


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
        _apply_late_payment(order, payment, reference=reference)
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


def _apply_late_payment(order: Order, payment: Payment, *, reference: str) -> None:
    """Деньги пришли за уже отменённый заказ (DRF-2736).

    Отменить неоплаченный платёж у кассы нельзя: страница оплаты живёт и после
    того, как заказ отменён — автоматикой по таймауту, покупателем или менеджером.
    Оплатил — деньги у магазина, а заказа нет.

    Воскрешать заказ нельзя: товар мог уйти другому покупателю, а «отменён» —
    терминальный статус. Молчать тоже нельзя: раньше заказ оставался «отменён, не
    оплачен», покупатель видел это в кабинете, а о деньгах знала одна строка лога.
    Поэтому заказ честно становится «отменён, оплачен» и сразу получает заявку на
    возврат — дальше работает обычный путь: очередь «Просят вернуть деньги» в
    админке, письмо сотрудникам, кнопка «Вернуть деньги», заявка в кабинете
    покупателя. У гостя своего способа подать заявку нет вовсе — за него её
    подаёт этот код.

    ``payment_succeeded`` / ``order_paid`` не издаём: списывать резерв не за что,
    а «заказ оплачен, собираем» покупателю отменённого заказа — неправда.
    """
    # Локальный импорт: refund_requests → services → transitions.
    from . import refund_requests

    order.payment_status = OrderPaymentStatus.PAID
    order.save(update_fields=["payment_status", "updated_at"])

    request = None
    try:
        # Свой savepoint: ошибка БД внутри не должна «отравить» внешнюю транзакцию.
        with transaction.atomic():
            request = refund_requests.ensure_request_for_cancelled(
                order.pk, comment=refund_requests.LATE_PAYMENT_COMMENT
            )
    except Exception:  # noqa: BLE001
        # Факт оплаты важнее заявки: её сбой не должен откатить «платёж получен» —
        # касса повторит уведомление несколько раз и бросит, а заказ отменён и в
        # janitor не попадёт: «деньги списаны, следа нет». Заявку позже заведёт
        # ``refund_requests.heal_missing_requests`` (janitor, каждые 5 минут).
        logger.exception(
            "Поздняя оплата заказа %s: заявку на возврат создать не удалось",
            order.order_number,
        )

    # error, а не info: это деньги покупателя за заказ, которого не будет.
    logger.error(
        "Поздняя оплата: заказ %s уже отменён, платёж %s на %s %s — %s. "
        "Верните деньги покупателю",
        order.order_number,
        reference,
        payment.amount,
        payment.currency,
        (
            f"заведена заявка на возврат #{request.pk}"
            if request is not None
            else "новая заявка на возврат не заведена (уже есть открытая или сбой)"
        ),
    )


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

    order_status = order_status_after_refund(payment.order_id, payment_id=payment.pk, full=full)
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
