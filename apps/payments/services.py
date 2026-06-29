"""Сервисный слой оплаты — создание платежа, обработка webhook (#8).

Контракт из ARCHITECTURE.md:
    create_payment(order) -> Payment  (с confirmation_url для редиректа)
    handle_webhook(payload) -> None   (идемпотентно)
    refund(payment) -> Payment

Секреты не логируются. Повтор webhook не ломает состояние.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.request
import uuid
from decimal import Decimal
from urllib.error import HTTPError

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core import events
from apps.orders.models import Order
from apps.orders.models import PaymentStatus as OrderPaymentStatus

from .models import Payment, PaymentMethod, PaymentStatus

logger = logging.getLogger(__name__)

YOOKASSA_API = "https://api.yookassa.ru/v3"


def _yookassa_request(method: str, path: str, body: dict | None = None) -> dict:
    shop_id = getattr(settings, "YOOKASSA_SHOP_ID", "")
    secret = getattr(settings, "YOOKASSA_SECRET_KEY", "")
    if not shop_id or not secret:
        raise RuntimeError("YOOKASSA_SHOP_ID/YOOKASSA_SECRET_KEY не настроены")

    import base64

    auth = base64.b64encode(f"{shop_id}:{secret}".encode()).decode()

    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
    }

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{YOOKASSA_API}/{path}", data=data, headers=headers, method=method
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as exc:
        exc.read().decode("utf-8", errors="replace")
        logger.error("YooKassa API error: %s %s -> %s", method, path, exc.code)
        raise RuntimeError(f"YooKassa API error {exc.code}") from exc


def create_payment(order: Order, return_url: str = "") -> Payment:
    """Создать платёж в ЮKassa и вернуть Payment с confirmation_url."""
    idempotency_key = f"order-{order.order_number}-{uuid.uuid4().hex[:8]}"

    if not return_url:
        return_url = f"{_site_url()}/order/{order.order_number}/thanks"

    body = {
        "amount": {"value": str(order.total), "currency": order.currency},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": f"Заказ {order.order_number}",
        "metadata": {"order_number": order.order_number, "order_id": order.id},
    }

    result = _yookassa_request("POST", "payments", body)

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


@transaction.atomic
def handle_webhook(payload: dict) -> None:
    """Обработать webhook от ЮKassa. Идемпотентно."""
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

    payment.webhook_payload = payment_data

    if event_type == "payment.succeeded":
        if payment.status == PaymentStatus.SUCCEEDED:
            return
        payment.status = PaymentStatus.SUCCEEDED
        payment.paid_at = timezone.now()
        payment.save(update_fields=["status", "paid_at", "webhook_payload", "updated_at"])

        Order.objects.filter(pk=payment.order_id).update(payment_status=OrderPaymentStatus.PAID)

        order_id = payment.order_id
        payment_id = payment.id
        transaction.on_commit(
            lambda: events.payment_succeeded.send(
                sender=Payment, payment_id=payment_id, order_id=order_id
            )
        )
        logger.info("Payment %s succeeded for order #%s", yookassa_id, payment.order.order_number)

    elif event_type == "payment.canceled":
        if payment.status == PaymentStatus.CANCELED:
            return
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

    elif event_type == "payment.waiting_for_capture":
        payment.status = PaymentStatus.WAITING_CAPTURE
        payment.save(update_fields=["status", "webhook_payload", "updated_at"])

    else:
        payment.save(update_fields=["webhook_payload", "updated_at"])
        logger.info("YooKassa webhook: unhandled event %s for %s", event_type, yookassa_id)


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """Проверить подпись webhook от ЮKassa (если настроен секрет)."""
    secret = getattr(settings, "YOOKASSA_WEBHOOK_SECRET", "")
    if not secret:
        return True
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@transaction.atomic
def refund(payment: Payment, amount: Decimal | None = None) -> Payment:
    """Создать возврат в ЮKassa."""
    if payment.status != PaymentStatus.SUCCEEDED:
        raise ValueError("Возврат возможен только для оплаченного платежа")

    refund_amount = amount or payment.amount
    body = {
        "amount": {"value": str(refund_amount), "currency": payment.currency},
        "payment_id": payment.yookassa_id,
    }

    _yookassa_request("POST", "refunds", body)

    payment.status = PaymentStatus.REFUNDED
    payment.save(update_fields=["status", "updated_at"])

    Order.objects.filter(pk=payment.order_id).update(payment_status=OrderPaymentStatus.REFUNDED)

    logger.info("Refund for payment %s, amount %s", payment.yookassa_id, refund_amount)
    return payment


def _site_url() -> str:
    allowed = getattr(settings, "ALLOWED_HOSTS", ["localhost"])
    host = next((h for h in allowed if h not in ("*", "localhost", "127.0.0.1")), "localhost")
    return f"https://{host}"
