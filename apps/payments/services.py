"""Сервисный слой оплаты — создание платежа, обработка webhook (#8, #311).

Контракт из ARCHITECTURE.md:
    create_payment(order) -> Payment  (с confirmation_url для редиректа)
    handle_webhook(payload) -> None   (идемпотентно)
    refund(payment) -> Payment

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


@transaction.atomic
def handle_webhook(payload: dict, *, verify: bool = True) -> None:
    """Обработать webhook от ЮKassa.

    При verify=True (default) статус перезапрашивается из API ЮKassa.
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

    if event_type == "payment.succeeded":
        if payment.status == PaymentStatus.SUCCEEDED:
            return

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


@transaction.atomic
def refund(payment: Payment, amount: Decimal | None = None) -> Payment:
    """Создать возврат в ЮKassa."""
    if payment.status != PaymentStatus.SUCCEEDED:
        raise ValueError("Возврат возможен только для оплаченного платежа")

    refund_amount = amount or payment.amount
    idempotence_key = f"refund-{payment.yookassa_id}"

    body = {
        "amount": {"value": str(refund_amount), "currency": payment.currency},
        "payment_id": payment.yookassa_id,
    }

    _yookassa_request("POST", "refunds", body, idempotence_key=idempotence_key)

    payment.status = PaymentStatus.REFUNDED
    payment.save(update_fields=["status", "updated_at"])

    Order.objects.filter(pk=payment.order_id).update(payment_status=OrderPaymentStatus.REFUNDED)

    logger.info("Refund for payment %s, amount %s", payment.yookassa_id, refund_amount)
    return payment


def _site_url() -> str:
    allowed = getattr(settings, "ALLOWED_HOSTS", ["localhost"])
    host = next((h for h in allowed if h not in ("*", "localhost", "127.0.0.1")), "localhost")
    return f"https://{host}"
