"""Тесты оплаты ЮKassa (#8, #311)."""

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
        idempotency_key="order-П-TEST-001",
    )


@pytest.fixture
def client():
    return Client()


# ═══════════════ МОДЕЛЬ ═══════════════


@pytest.mark.django_db
def test_payment_creation(payment):
    assert payment.yookassa_id == "yoo_test_123"
    assert payment.status == PaymentStatus.PENDING


# ═══════════════ WEBHOOK — succeeded с verify ═══════════════


@pytest.mark.django_db
@mock.patch("apps.payments.services.verify_webhook")
def test_webhook_succeeded(mock_verify, payment, order):
    mock_verify.return_value = {
        "id": "yoo_test_123",
        "status": "succeeded",
        "paid": True,
        "amount": {"value": "5000.00", "currency": "RUB"},
    }
    payload = {
        "event": "payment.succeeded",
        "object": {"id": "yoo_test_123", "amount": {"value": "5000.00", "currency": "RUB"}},
    }
    handle_webhook(payload)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.SUCCEEDED
    order.refresh_from_db()
    assert order.payment_status == OrderPaymentStatus.PAID


@pytest.mark.django_db
@mock.patch("apps.payments.services.verify_webhook")
def test_webhook_idempotent(mock_verify, payment):
    mock_verify.return_value = {
        "id": "yoo_test_123",
        "status": "succeeded",
        "paid": True,
        "amount": {"value": "5000.00", "currency": "RUB"},
    }
    payload = {
        "event": "payment.succeeded",
        "object": {"id": "yoo_test_123", "amount": {"value": "5000.00", "currency": "RUB"}},
    }
    handle_webhook(payload)
    handle_webhook(payload)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.SUCCEEDED


# ═══════════════ СВЕРКА СУММЫ ═══════════════


@pytest.mark.django_db
@mock.patch("apps.payments.services.verify_webhook")
def test_webhook_amount_mismatch_rejected(mock_verify, payment):
    mock_verify.return_value = {
        "id": "yoo_test_123",
        "status": "succeeded",
        "paid": True,
        "amount": {"value": "1.00", "currency": "RUB"},
    }
    payload = {
        "event": "payment.succeeded",
        "object": {"id": "yoo_test_123", "amount": {"value": "1.00", "currency": "RUB"}},
    }
    with pytest.raises(ValueError, match="mismatch"):
        handle_webhook(payload)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.PENDING


@pytest.mark.django_db
@mock.patch("apps.payments.services.verify_webhook")
def test_webhook_currency_mismatch_rejected(mock_verify, payment):
    mock_verify.return_value = {
        "id": "yoo_test_123",
        "status": "succeeded",
        "paid": True,
        "amount": {"value": "5000.00", "currency": "USD"},
    }
    payload = {
        "event": "payment.succeeded",
        "object": {"id": "yoo_test_123", "amount": {"value": "5000.00", "currency": "USD"}},
    }
    with pytest.raises(ValueError, match="mismatch"):
        handle_webhook(payload)


# ═══════════════ B-02: переход по проверенному объекту, не по event ═══════════════


@pytest.mark.django_db
@mock.patch("apps.payments.services.verify_webhook")
def test_webhook_fake_succeeded_event_but_verified_pending(mock_verify, payment, order):
    """event=succeeded, но проверенный объект ещё pending → заказ НЕ оплачен."""
    mock_verify.return_value = {
        "id": "yoo_test_123",
        "status": "pending",
        "paid": False,
        "amount": {"value": "5000.00", "currency": "RUB"},
    }
    payload = {
        "event": "payment.succeeded",
        "object": {"id": "yoo_test_123", "amount": {"value": "5000.00", "currency": "RUB"}},
    }
    handle_webhook(payload)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.PENDING
    order.refresh_from_db()
    assert order.payment_status != OrderPaymentStatus.PAID


@pytest.mark.django_db
@mock.patch("apps.payments.services.verify_webhook")
def test_webhook_succeeded_but_paid_false_rejected(mock_verify, payment):
    """status=succeeded, но paid=false → отвергаем (5xx, retry)."""
    mock_verify.return_value = {
        "id": "yoo_test_123",
        "status": "succeeded",
        "paid": False,
        "amount": {"value": "5000.00", "currency": "RUB"},
    }
    payload = {"event": "payment.succeeded", "object": {"id": "yoo_test_123"}}
    with pytest.raises(ValueError, match="not paid"):
        handle_webhook(payload)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.PENDING


@pytest.mark.django_db
@mock.patch("apps.payments.services.verify_webhook")
def test_webhook_no_downgrade_succeeded_to_canceled(mock_verify, payment, order):
    """Уже succeeded нельзя откатить в canceled поддельным webhook."""
    payment.status = PaymentStatus.SUCCEEDED
    payment.save(update_fields=["status"])
    Order.objects.filter(pk=order.pk).update(payment_status=OrderPaymentStatus.PAID)

    mock_verify.return_value = {
        "id": "yoo_test_123",
        "status": "canceled",
        "amount": {"value": "5000.00", "currency": "RUB"},
    }
    payload = {"event": "payment.canceled", "object": {"id": "yoo_test_123"}}
    handle_webhook(payload)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.SUCCEEDED
    order.refresh_from_db()
    assert order.payment_status == OrderPaymentStatus.PAID


@pytest.mark.django_db
@mock.patch("apps.payments.services.verify_webhook")
def test_webhook_success_emits_order_paid(
    mock_verify, payment, order, django_capture_on_commit_callbacks
):
    """#431 (M-07): успешный webhook публикует order_paid для подписчиков заказа."""
    from apps.core import events

    mock_verify.return_value = {
        "id": "yoo_test_123",
        "status": "succeeded",
        "paid": True,
        "amount": {"value": "5000.00", "currency": "RUB"},
    }
    payload = {"event": "payment.succeeded", "object": {"id": "yoo_test_123"}}

    received = []
    events.order_paid.connect(
        lambda sender, **kw: received.append(kw), dispatch_uid="test_m07_probe"
    )
    try:
        with django_capture_on_commit_callbacks(execute=True):
            handle_webhook(payload)
    finally:
        events.order_paid.disconnect(dispatch_uid="test_m07_probe")

    assert len(received) == 1
    assert received[0]["order_id"] == order.pk
    assert received[0]["payment_id"] == payment.pk


@pytest.mark.django_db
@mock.patch("apps.payments.services.verify_webhook")
def test_webhook_metadata_order_mismatch_rejected(mock_verify, payment):
    """metadata.order_id проверенного объекта не совпадает с заказом → отказ."""
    mock_verify.return_value = {
        "id": "yoo_test_123",
        "status": "succeeded",
        "paid": True,
        "amount": {"value": "5000.00", "currency": "RUB"},
        "metadata": {"order_id": 999999},
    }
    payload = {"event": "payment.succeeded", "object": {"id": "yoo_test_123"}}
    with pytest.raises(ValueError, match="metadata order mismatch"):
        handle_webhook(payload)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.PENDING


# ═══════════════ ВЕРИФИКАЦИЯ ═══════════════


@pytest.mark.django_db
@mock.patch("apps.payments.services.verify_webhook", return_value=None)
def test_webhook_verify_fails_raises(mock_verify, payment):
    payload = {"event": "payment.succeeded", "object": {"id": "yoo_test_123"}}
    with pytest.raises(RuntimeError, match="Cannot verify"):
        handle_webhook(payload)


@pytest.mark.django_db
def test_webhook_no_verify(payment, order):
    """verify=False пропускает перезапрос (для тестов)."""
    payload = {
        "event": "payment.succeeded",
        "object": {
            "id": "yoo_test_123",
            "status": "succeeded",
            "paid": True,
            "amount": {"value": "5000.00", "currency": "RUB"},
        },
    }
    handle_webhook(payload, verify=False)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.SUCCEEDED


# ═══════════════ CANCELED ═══════════════


@pytest.mark.django_db
def test_webhook_canceled(payment):
    payload = {
        "event": "payment.canceled",
        "object": {
            "id": "yoo_test_123",
            "status": "canceled",
            "cancellation_details": {"reason": "expired"},
        },
    }
    handle_webhook(payload, verify=False)
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.CANCELED


# ═══════════════ ENDPOINT ═══════════════


@pytest.mark.django_db
def test_endpoint_rejects_get(client):
    assert client.get("/api/payments/webhook/yookassa/").status_code == 405


@pytest.mark.django_db
def test_endpoint_invalid_json(client):
    resp = client.post(
        "/api/payments/webhook/yookassa/", data="bad", content_type="application/json"
    )
    assert resp.status_code == 400


@pytest.mark.django_db
@mock.patch("apps.payments.views.handle_webhook", side_effect=RuntimeError("boom"))
def test_endpoint_error_returns_500(mock_hw, client):
    resp = client.post(
        "/api/payments/webhook/yookassa/",
        data=json.dumps({"event": "x", "object": {"id": "y"}}),
        content_type="application/json",
    )
    assert resp.status_code == 500


# ═══════════════ CREATE PAYMENT — идемпотентность ═══════════════


@override_settings(YOOKASSA_SHOP_ID="shop", YOOKASSA_SECRET_KEY="secret")
@pytest.mark.django_db
@mock.patch("apps.payments.services._yookassa_request")
def test_create_payment_idempotent(mock_api, order):
    mock_api.return_value = {"id": "yoo_new", "confirmation": {"confirmation_url": "https://pay"}}

    from .services import create_payment

    p1 = create_payment(order)
    p2 = create_payment(order)
    assert p1.pk == p2.pk
    assert mock_api.call_count == 1


# ═══════════════ REFUND ═══════════════


@override_settings(YOOKASSA_SHOP_ID="shop", YOOKASSA_SECRET_KEY="secret")
@pytest.mark.django_db
@mock.patch("apps.payments.services._yookassa_request")
def test_refund(mock_api, payment, order):
    mock_api.return_value = {"id": "refund_1"}
    payment.status = PaymentStatus.SUCCEEDED
    payment.save()

    from .services import refund

    result = refund(payment)
    assert result.status == PaymentStatus.REFUNDED
    order.refresh_from_db()
    assert order.payment_status == OrderPaymentStatus.REFUNDED
    assert mock_api.call_args[1].get("idempotence_key") or "refund" in str(mock_api.call_args)


@pytest.mark.django_db
def test_refund_not_paid_raises(payment):
    from .services import refund

    with pytest.raises(ValueError, match="оплаченного"):
        refund(payment)
