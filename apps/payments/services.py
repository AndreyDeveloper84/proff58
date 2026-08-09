"""Сервисный слой оплаты — создание платежа, обработка webhook (#8, #311).

Контракт из ARCHITECTURE.md:
    create_payment(order) -> Payment  (с confirmation_url для редиректа)
    handle_webhook(payload) -> None   (идемпотентно)
    refund(payment, amount=None) -> Refund  (частичные возвраты, ledger)

Безопасность (#311):
- Webhook верифицируется перезапросом GET /payments/{id} к API ЮKassa
- Сумма/валюта сверяются перед пометкой PAID
- Idempotence-Key детерминирован по order_number (без uuid-суффикса)
- Ошибка обработки → 5xx (ЮKassa сделает retry)
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.request
import uuid
from decimal import Decimal
from urllib.error import HTTPError

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core import events
from apps.orders.models import FulfillmentStatus, Order
from apps.orders.models import PaymentStatus as OrderPaymentStatus

from .models import Payment, PaymentMethod, PaymentStatus, Refund, RefundStatus

logger = logging.getLogger(__name__)

YOOKASSA_API = "https://api.yookassa.ru/v3"


def _yookassa_request(
    method: str, path: str, body: dict | None = None, idempotence_key: str = ""
) -> dict:
    shop_id = getattr(settings, "YOOKASSA_SHOP_ID", "")
    secret = getattr(settings, "YOOKASSA_SECRET_KEY", "")
    if not shop_id or not secret:
        raise RuntimeError("YOOKASSA_SHOP_ID/YOOKASSA_SECRET_KEY не настроены")

    auth = base64.b64encode(f"{shop_id}:{secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
    }
    if idempotence_key:
        headers["Idempotence-Key"] = idempotence_key

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{YOOKASSA_API}/{path}", data=data, headers=headers, method=method
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as exc:
        exc.read()
        logger.error("YooKassa API error: %s %s -> %s", method, path, exc.code)
        raise RuntimeError(f"YooKassa API error {exc.code}") from exc


def create_payment(order: Order, return_url: str = "") -> Payment:
    """Создать платёж в ЮKassa. Idempotence-Key детерминирован по order_number."""
    idempotency_key = f"order-{order.order_number}"

    existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing

    if not return_url:
        site_url = getattr(settings, "SITE_URL", _site_url())
        return_url = f"{site_url}/order/{order.order_number}/thanks"

    body = {
        "amount": {"value": str(order.total), "currency": order.currency},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": f"Заказ {order.order_number}",
        "metadata": {"order_number": order.order_number, "order_id": order.id},
    }

    result = _yookassa_request("POST", "payments", body, idempotence_key=idempotency_key)

    payment = Payment.objects.create(
        order=order,
        yookassa_id=result.get("id"),
        method=PaymentMethod.YOOKASSA,
        status=PaymentStatus.PENDING,
        amount=order.total,
        currency=order.currency,
        confirmation_url=result.get("confirmation", {}).get("confirmation_url", ""),
        idempotency_key=idempotency_key,
    )

    logger.info("Payment created: %s for order %s", payment.yookassa_id, order.order_number)
    return payment


def verify_webhook(payment_data: dict) -> dict | None:
    """Верифицировать webhook перезапросом к API ЮKassa.

    Возвращает данные платежа из API или None при ошибке.
    """
    yookassa_id = payment_data.get("id")
    if not yookassa_id:
        return None
    try:
        return _yookassa_request("GET", f"payments/{yookassa_id}")
    except Exception:
        logger.exception("Failed to verify payment %s via API", yookassa_id)
        return None


# #422 (B-02): статус ЮKassa (проверенный объект) → локальный статус платежа.
# Переход строится ТОЛЬКО по этому объекту, не по event из тела webhook.
_PROVIDER_STATUS_MAP = {
    "succeeded": PaymentStatus.SUCCEEDED,
    "canceled": PaymentStatus.CANCELED,
    "waiting_for_capture": PaymentStatus.WAITING_CAPTURE,
    "pending": PaymentStatus.PENDING,
}

# Допустимые переходы статуса по webhook. Терминальные succeeded/canceled/refunded
# не откатываются (защита от downgrade succeeded->canceled и повторов).
_WEBHOOK_TRANSITIONS = {
    PaymentStatus.PENDING: {
        PaymentStatus.WAITING_CAPTURE,
        PaymentStatus.SUCCEEDED,
        PaymentStatus.CANCELED,
    },
    PaymentStatus.WAITING_CAPTURE: {
        PaymentStatus.SUCCEEDED,
        PaymentStatus.CANCELED,
    },
    PaymentStatus.SUCCEEDED: set(),  # терминальный (refund — отдельный путь)
    PaymentStatus.CANCELED: set(),  # терминальный
    PaymentStatus.REFUNDED: set(),
}


@transaction.atomic
def handle_webhook(payload: dict, *, verify: bool = True) -> None:
    """Обработать webhook от ЮKassa.

    #422 (B-02): переход состояния строится ИСКЛЮЧИТЕЛЬНО по проверенному объекту
    провайдера (``status``/``paid``/``amount``/``metadata``), а не по ``event`` из
    тела webhook — иначе поддельный ``payment.succeeded`` мог бы пометить заказ
    оплаченным. Входящий ``event`` используется только для аудита. Дополнительно
    проверяются принадлежность платежа заказу (metadata.order_id) и допустимость
    перехода. При verify=True (default) объект перезапрашивается из API ЮKassa.
    Ошибка обработки пробрасывается (→ 5xx, ЮKassa сделает retry).
    """
    event_type = payload.get("event")
    payment_data = payload.get("object", {})
    yookassa_id = payment_data.get("id")

    if not yookassa_id:
        logger.warning("YooKassa webhook: no payment id in payload")
        return

    try:
        payment = Payment.objects.select_for_update().get(yookassa_id=yookassa_id)
    except Payment.DoesNotExist:
        logger.warning("YooKassa webhook: unknown payment %s", yookassa_id)
        return

    if verify:
        verified = verify_webhook(payment_data)
        if verified:
            payment_data = verified
        else:
            raise RuntimeError(f"Cannot verify payment {yookassa_id} via API")

    payment.webhook_payload = payment_data

    # Переход определяется проверенным статусом провайдера, event — только аудит.
    verified_status = payment_data.get("status", "")
    target = _PROVIDER_STATUS_MAP.get(verified_status)
    if target is None:
        logger.info(
            "YooKassa webhook: unhandled status %r (event=%r) for %s",
            verified_status,
            event_type,
            yookassa_id,
        )
        payment.save(update_fields=["webhook_payload", "updated_at"])
        return

    # Идемпотентность: целевой статус уже установлен.
    if payment.status == target:
        payment.save(update_fields=["webhook_payload", "updated_at"])
        return

    # Принадлежность: metadata.order_id проверенного объекта должен совпадать с заказом.
    meta_order_id = (payment_data.get("metadata") or {}).get("order_id")
    if meta_order_id is not None and str(meta_order_id) != str(payment.order_id):
        logger.error(
            "YooKassa webhook: metadata order_id %s != payment.order_id %s for %s",
            meta_order_id,
            payment.order_id,
            yookassa_id,
        )
        raise ValueError("Payment metadata order mismatch")

    # Допустимость перехода (никакого downgrade терминальных статусов).
    if target not in _WEBHOOK_TRANSITIONS.get(payment.status, set()):
        logger.warning(
            "YooKassa webhook: forbidden transition %s -> %s for %s (ignored)",
            payment.status,
            target,
            yookassa_id,
        )
        payment.save(update_fields=["webhook_payload", "updated_at"])
        return

    if target == PaymentStatus.SUCCEEDED:
        # Проверенный объект действительно оплачен.
        if not payment_data.get("paid", False):
            logger.error(
                "YooKassa webhook: status succeeded but paid is not true for %s", yookassa_id
            )
            raise ValueError("Payment not paid")

        webhook_amount = Decimal(str(payment_data.get("amount", {}).get("value", "0")))
        webhook_currency = payment_data.get("amount", {}).get("currency", "")
        if webhook_amount != payment.amount or webhook_currency != payment.currency:
            logger.error(
                "YooKassa amount mismatch: expected %s %s, got %s %s for %s",
                payment.amount,
                payment.currency,
                webhook_amount,
                webhook_currency,
                yookassa_id,
            )
            raise ValueError("Payment amount/currency mismatch")

        payment.status = PaymentStatus.SUCCEEDED
        payment.paid_at = timezone.now()
        payment.save(update_fields=["status", "paid_at", "webhook_payload", "updated_at"])

        # DRF-952: строку заказа берём под блокировку. Раньше здесь был слепой
        # UPDATE, и janitor истечения мог в тот же момент отменять этот заказ —
        # получалось «деньги получены, заказ отменён, товар снят с резерва».
        # Теперь одна из сторон ждёт другую, и решение принимает та, что успела.
        order = Order.objects.select_for_update().get(pk=payment.order_id)

        if order.fulfillment_status == FulfillmentStatus.CANCELLED:
            # Поздняя оплата: заказ уже отменён по таймауту, товар мог уйти
            # другому покупателю. Молча воскрешать нельзя — денег это не вернёт,
            # а обещание отгрузить создаст. Платёж помечен успешным (деньги
            # действительно пришли), заказ остаётся отменённым, случай уходит
            # в лог ошибкой для ручного разбора и возврата.
            logger.error(
                "Поздняя оплата: заказ %s уже отменён, платёж %s на %s %s требует "
                "ручного разбора (возврат или восстановление заказа)",
                order.order_number,
                yookassa_id,
                payment.amount,
                payment.currency,
            )
            return

        order.payment_status = OrderPaymentStatus.PAID
        order.save(update_fields=["payment_status", "updated_at"])

        order_id = payment.order_id
        payment_id = payment.id
        # #431 (M-07): публикуем ОБА события после commit.
        # payment_succeeded — платёжный слой (orders confirm резерва);
        # order_paid — доменное событие оплаты заказа, на которое подписаны
        # MAX/analytics/CRM. Раньше они слушали order_paid без издателя и не
        # срабатывали. Идемпотентность — гейт перехода: код доходит сюда только
        # на реальном переходе pending/waiting → succeeded (не на повторах).
        transaction.on_commit(
            lambda: events.payment_succeeded.send(
                sender=Payment, payment_id=payment_id, order_id=order_id
            )
        )
        transaction.on_commit(
            lambda: events.order_paid.send(sender=Payment, order_id=order_id, payment_id=payment_id)
        )
        logger.info("Payment %s succeeded for order #%s", yookassa_id, payment.order.order_number)

    elif target == PaymentStatus.CANCELED:
        payment.status = PaymentStatus.CANCELED
        payment.save(update_fields=["status", "webhook_payload", "updated_at"])

        reason = payment_data.get("cancellation_details", {}).get("reason", "unknown")
        order_id = payment.order_id
        payment_id = payment.id
        transaction.on_commit(
            lambda: events.payment_failed.send(
                sender=Payment, payment_id=payment_id, order_id=order_id, reason=reason
            )
        )
        logger.info("Payment %s canceled: %s", yookassa_id, reason)

    elif target == PaymentStatus.WAITING_CAPTURE:
        payment.status = PaymentStatus.WAITING_CAPTURE
        payment.save(update_fields=["status", "webhook_payload", "updated_at"])


def _refunded_total(payment_id: int) -> Decimal:
    """Сумма успешных возвратов по платежу."""
    agg = Refund.objects.filter(payment_id=payment_id, status=RefundStatus.SUCCEEDED).aggregate(
        s=Sum("amount")
    )
    return agg["s"] or Decimal("0")


def refund(payment: Payment, amount: Decimal | None = None) -> Refund:
    """Создать (частичный) возврат в ЮKassa. Возвращает строку ledger Refund.

    #437 (m-01/m-02):
    - поддержка нескольких частичных возвратов; статус платежа/заказа —
      производное от суммы успешных возвратов (partial vs full);
    - валидация ``0 < amount <= remaining`` (оплачено − уже возвращено);
    - сетевой вызов ЮKassa выполняется ВНЕ DB-транзакции (claim строки Refund в
      короткой транзакции, затем внешний вызов, затем финализация) — сеть не
      держит блокировку строки платежа.
    """
    if payment.status not in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED):
        raise ValueError("Возврат возможен только для оплаченного платежа")

    remaining = payment.amount - _refunded_total(payment.pk)
    refund_amount = payment.amount if amount is None else Decimal(amount)
    if refund_amount <= 0:
        raise ValueError("Сумма возврата должна быть положительной")
    if refund_amount > remaining:
        raise ValueError(f"Сумма возврата {refund_amount} превышает остаток {remaining}")

    # Claim: строка Refund (pending) в короткой транзакции; уникальный ключ на строку.
    with transaction.atomic():
        rec = Refund.objects.create(
            payment=payment,
            amount=refund_amount,
            currency=payment.currency,
            status=RefundStatus.PENDING,
            idempotency_key=f"refund-{payment.yookassa_id}-{uuid.uuid4().hex[:12]}",
        )

    body = {
        "amount": {"value": str(refund_amount), "currency": payment.currency},
        "payment_id": payment.yookassa_id,
    }
    # Внешний вызов — ВНЕ транзакции.
    try:
        result = _yookassa_request("POST", "refunds", body, idempotence_key=rec.idempotency_key)
    except Exception as exc:
        Refund.objects.filter(pk=rec.pk).update(
            status=RefundStatus.FAILED, error_message=str(exc)[:500]
        )
        logger.exception("Refund failed for payment %s", payment.yookassa_id)
        raise

    # Финализация: успех возврата + производный статус платежа/заказа.
    with transaction.atomic():
        Refund.objects.filter(pk=rec.pk).update(
            status=RefundStatus.SUCCEEDED, yookassa_refund_id=result.get("id", "")
        )
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        total_refunded = _refunded_total(locked.pk)
        is_full = total_refunded >= locked.amount
        if is_full:
            locked.status = PaymentStatus.REFUNDED
            order_status = OrderPaymentStatus.REFUNDED
        else:
            locked.status = PaymentStatus.PARTIALLY_REFUNDED
            order_status = OrderPaymentStatus.PARTIALLY_REFUNDED
        locked.save(update_fields=["status", "updated_at"])
        Order.objects.filter(pk=locked.order_id).update(payment_status=order_status)

        # ADR-0009 (#516): раньше refund() не публиковал ничего — MAX/аналитика
        # не могли узнать о возврате без прямой связки payments → notifications.
        refund_id = rec.pk
        order_id = locked.order_id
        payment_id = locked.pk
        transaction.on_commit(
            lambda: events.payment_refunded.send(
                sender=Refund,
                payment_id=payment_id,
                order_id=order_id,
                refund_id=refund_id,
                amount=str(refund_amount),
                is_full=is_full,
            )
        )

    rec.refresh_from_db()
    logger.info("Refund %s for payment %s, amount %s", rec.pk, payment.yookassa_id, refund_amount)
    return rec


def _site_url() -> str:
    allowed = getattr(settings, "ALLOWED_HOSTS", ["localhost"])
    host = next((h for h in allowed if h not in ("*", "localhost", "127.0.0.1")), "localhost")
    return f"https://{host}"
