"""Privacy retention tests for payment callback snapshots (DRF-2925)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.orders.models import Order

from .atolpay.service import _sanitize_webhook_payload
from .models import Payment, PaymentProvider, PaymentStatus
from .tasks import cleanup_old_webhook_payloads


def _order() -> Order:
    return Order.objects.create(
        order_number="P-RETENTION-1",
        total=Decimal("100.00"),
        currency="RUB",
        customer_phone="+79001234567",
        customer_email="buyer@example.com",
        payment_method="online",
        access_token="retention-token",
    )


def _payment(*, payload: dict, payload_age_days: int) -> Payment:
    return Payment.objects.create(
        order=_order(),
        provider=PaymentProvider.ATOLPAY,
        provider_order_id=f"ret-{timezone.now().timestamp()}-{payload_age_days}",
        provider_payment_id=None,
        status=PaymentStatus.SUCCEEDED,
        amount=Decimal("100.00"),
        currency="RUB",
        idempotency_key=f"ret-key-{timezone.now().timestamp()}-{payload_age_days}",
        webhook_payload=payload,
        webhook_payload_at=timezone.now() - timedelta(days=payload_age_days),
        receipt_id="receipt-1",
        receipt_status="success",
    )


def test_sanitize_webhook_payload_drops_unexpected_fields():
    payload = {
        "orderId": "P-1",
        "amount": 10000,
        "status": "success",
        "email": "buyer@example.com",
        "phone": "+79001234567",
        "cardNumber": "4111111111111111",
        "nested": {"anything": "unexpected"},
    }

    assert _sanitize_webhook_payload(payload) == {
        "orderId": "P-1",
        "amount": 10000,
        "status": "success",
    }


@pytest.mark.django_db
def test_cleanup_clears_old_payload_but_keeps_payment_ledger(settings):
    settings.PAYMENT_WEBHOOK_RAW_RETENTION_DAYS = 30
    payment = _payment(
        payload={"orderId": "P-1", "status": "success", "amount": 10000},
        payload_age_days=31,
    )

    cleared = cleanup_old_webhook_payloads()

    payment.refresh_from_db()
    assert cleared == 1
    assert payment.webhook_payload == {}
    assert payment.webhook_payload_at is None
    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.amount == Decimal("100.00")
    assert payment.receipt_id == "receipt-1"
    assert payment.receipt_status == "success"


@pytest.mark.django_db
def test_cleanup_keeps_recent_payload(settings):
    settings.PAYMENT_WEBHOOK_RAW_RETENTION_DAYS = 30
    payment = _payment(
        payload={"orderId": "P-2", "status": "success"},
        payload_age_days=29,
    )

    assert cleanup_old_webhook_payloads() == 0

    payment.refresh_from_db()
    assert payment.webhook_payload["orderId"] == "P-2"
    assert payment.webhook_payload_at is not None


@pytest.mark.django_db
def test_cleanup_is_idempotent(settings):
    settings.PAYMENT_WEBHOOK_RAW_RETENTION_DAYS = 30
    payment = _payment(payload={"orderId": "P-3"}, payload_age_days=31)

    assert cleanup_old_webhook_payloads() == 1
    assert cleanup_old_webhook_payloads() == 0

    payment.refresh_from_db()
    assert payment.webhook_payload == {}
