"""Письмо менеджерам о заявке на возврат (T2): после коммита, один раз, без секретов."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core import mail

from apps.core import events
from apps.notifications.models import NotificationLog, NotificationStatus
from apps.orders.models import FulfillmentStatus, Order
from apps.orders.models import PaymentStatus as OrderPaymentStatus
from apps.payments.models import Payment, PaymentProvider, PaymentStatus, RefundRequest
from apps.payments.refund_requests import create_request

User = get_user_model()


@pytest.fixture(autouse=True)
def _почта(settings):
    settings.STAFF_NOTIFICATION_EMAILS = ["manager@example.com"]
    settings.DEFAULT_FROM_EMAIL = "site@example.com"
    settings.SITE_URL = "https://proff58.ru"
    settings.ATOLPAY_TOKEN = "secret-atol-token-xyz"


@pytest.fixture
def paid_order(db):
    user = User.objects.create_user(phone="+79005550002", password="pass12345")
    order = Order.objects.create(
        order_number="П-RF-EM",
        user=user,
        customer_name="Пётр",
        customer_phone="+79005550002",
        total=Decimal("3000.00"),
        payment_method="online",
        payment_status=OrderPaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.CONFIRMED,
    )
    Payment.objects.create(
        order=order,
        provider=PaymentProvider.ATOLPAY,
        provider_order_id="RFEM",
        provider_payment_id="RFEM",
        status=PaymentStatus.SUCCEEDED,
        amount=order.total,
        idempotency_key="order-RFEM",
    )
    return order


@pytest.mark.django_db
def test_заявка_даёт_одно_письмо_менеджерам(paid_order, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        req = create_request(
            order_id=paid_order.pk, user_id=paid_order.user_id, reason="defect", comment="сломан"
        )
    assert len(mail.outbox) == 1
    m = mail.outbox[0]
    assert m.to == ["manager@example.com"]
    assert "П-RF-EM" in m.subject
    assert "Брак или неисправность" in m.body and "сломан" in m.body
    assert f"/admin/payments/refundrequest/{req.pk}/change/" in m.body
    assert "secret-atol-token-xyz" not in m.body
    log = NotificationLog.objects.get(idempotency_key=f"staff-refund-requested-{req.pk}")
    assert log.status == NotificationStatus.SENT
    # повтор события — без второго письма
    events.refund_requested.send(sender=RefundRequest, request_id=req.pk, order_id=paid_order.pk)
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_без_получателей_заявка_создаётся_а_письмо_skipped(
    paid_order, settings, django_capture_on_commit_callbacks
):
    settings.STAFF_NOTIFICATION_EMAILS = []
    with django_capture_on_commit_callbacks(execute=True):
        req = create_request(order_id=paid_order.pk, user_id=paid_order.user_id, reason="delay")
    assert RefundRequest.objects.filter(pk=req.pk).exists()
    assert mail.outbox == []
    log = NotificationLog.objects.get(idempotency_key=f"staff-refund-requested-{req.pk}")
    assert log.status == NotificationStatus.SKIPPED
