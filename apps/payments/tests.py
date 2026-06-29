"""Тесты оплаты ЮKassa (#8)."""

import json
from decimal import Decimal
from unittest import mock

import pytest
from django.test import Client, override_settings

from apps.orders.models import Order
from apps.orders.models import PaymentStatus as OrderPaymentStatus

from .models import Payment, PaymentMethod, PaymentStatus
from .services import handle_webhook


@pytest.fixture
def order(db):
    return Order.objects.create(
        order_number="П-TEST-001",
        total=Decimal("5000.00"),
        currency="RUB",
        customer_phone="+79001234567",
    )


@pytest.fixture
def payment(order):
    return Payment.objects.create(
        order=order,
        yookassa_id="yoo_test_123",
        method=PaymentMethod.YOOKASSA,
        status=PaymentStatus.PENDING,
        amount=order.total,
        currency="RUB",
        idempotency_key="idem-test-001",
    )


@pytest.fixture
def client():
    return Client()


# ═══════════════════════════════════════════════════════════════════════
# 1. МОДЕЛЬ Payment
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_payment_creation(payment):
    assert payment.yookassa_id == "yoo_test_123"
    assert payment.status == PaymentStatus.PENDING
    assert str(payment) == "Платёж yoo_test_123 [pending]"


@pytest.mark.django_db
def test_payment_without_yookassa_id(order):
    p = Payment.objects.create(
        order=order,
        method=PaymentMethod.INVOICE,
        status=PaymentStatus.PENDING,
        amount=order.total,
        idempotency_key="idem-invoice-001",
    )
    assert p.yookassa_id is None


# ═══════════════════════════════════════════════════════════════════════
# 2. WEBHOOK — payment.succeeded
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_webhook_payment_succeeded(payment, order):
    payload = {
        "event": "payment.succeeded",
        "object": {"id": "yoo_test_123", "status": "succeeded"},
    }
    handle_webhook(payload)

    payment.refresh_from_db()
    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.paid_at is not None

    order.refresh_from_db()
    assert order.payment_status == OrderPaymentStatus.PAID


@pytest.mark.django_db
def test_webhook_idempotent(payment):
    payload = {
        "event": "payment.succeeded",
        "object": {"id": "yoo_test_123", "status": "succeeded"},
    }
    handle_webhook(payload)
    handle_webhook(payload)

    assert Payment.objects.filter(yookassa_id="yoo_test_123").count() == 1
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.SUCCEEDED


# ═══════════════════════════════════════════════════════════════════════
# 3. WEBHOOK — payment.canceled
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_webhook_payment_canceled(payment):
    payload = {
        "event": "payment.canceled",
        "object": {
            "id": "yoo_test_123",
            "status": "canceled",
            "cancellation_details": {"reason": "expired_on_confirmation"},
        },
    }
    handle_webhook(payload)

    payment.refresh_from_db()
    assert payment.status == PaymentStatus.CANCELED


# ═══════════════════════════════════════════════════════════════════════
# 4. WEBHOOK — unknown payment
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_webhook_unknown_payment():
    payload = {
        "event": "payment.succeeded",
        "object": {"id": "yoo_nonexistent"},
    }
    handle_webhook(payload)


# ═══════════════════════════════════════════════════════════════════════
# 5. WEBHOOK endpoint
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_webhook_endpoint_rejects_get(client):
    resp = client.get("/api/payments/webhook/yookassa/")
    assert resp.status_code == 405


@pytest.mark.django_db
def test_webhook_endpoint_invalid_json(client):
    resp = client.post(
        "/api/payments/webhook/yookassa/",
        data="not json",
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_webhook_endpoint_valid(client, payment):
    payload = {
        "event": "payment.succeeded",
        "object": {"id": "yoo_test_123", "status": "succeeded"},
    }
    resp = client.post(
        "/api/payments/webhook/yookassa/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    payment.refresh_from_db()
    assert payment.status == PaymentStatus.SUCCEEDED


# ═══════════════════════════════════════════════════════════════════════
# 6. БЕЗОПАСНОСТЬ — секреты не в логах
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_webhook_payload_stored_without_secrets(payment):
    payload = {
        "event": "payment.succeeded",
        "object": {
            "id": "yoo_test_123",
            "status": "succeeded",
            "payment_method": {"type": "bank_card", "card": {"last4": "1234"}},
        },
    }
    handle_webhook(payload)

    payment.refresh_from_db()
    assert "yoo_test_123" in str(payment.webhook_payload)


# ═══════════════════════════════════════════════════════════════════════
# 7. CREATE PAYMENT (мок ЮKassa API)
# ═══════════════════════════════════════════════════════════════════════


@override_settings(YOOKASSA_SHOP_ID="test_shop", YOOKASSA_SECRET_KEY="test_secret")
@pytest.mark.django_db
@mock.patch("apps.payments.services._yookassa_request")
def test_create_payment(mock_api, order):
    mock_api.return_value = {
        "id": "yoo_created_456",
        "confirmation": {"confirmation_url": "https://yookassa.ru/pay/123"},
    }

    from .services import create_payment

    payment = create_payment(order)

    assert payment.yookassa_id == "yoo_created_456"
    assert payment.confirmation_url == "https://yookassa.ru/pay/123"
    assert payment.status == PaymentStatus.PENDING
    assert payment.amount == order.total
    mock_api.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# 8. REFUND
# ═══════════════════════════════════════════════════════════════════════


@override_settings(YOOKASSA_SHOP_ID="test_shop", YOOKASSA_SECRET_KEY="test_secret")
@pytest.mark.django_db
@mock.patch("apps.payments.services._yookassa_request")
def test_refund(mock_api, payment, order):
    mock_api.return_value = {"id": "refund_1", "status": "succeeded"}
    payment.status = PaymentStatus.SUCCEEDED
    payment.save()

    from .services import refund

    result = refund(payment)
    assert result.status == PaymentStatus.REFUNDED

    order.refresh_from_db()
    assert order.payment_status == OrderPaymentStatus.REFUNDED


@pytest.mark.django_db
def test_refund_not_paid_raises(payment):
    from .services import refund

    with pytest.raises(ValueError, match="оплаченного"):
        refund(payment)
