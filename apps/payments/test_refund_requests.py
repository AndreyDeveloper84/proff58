"""Заявки покупателей на возврат денег.

Держим правила владельца (17.09.2026): заявка только по оплаченному онлайн
заказу, до получения и 14 дней после; одна открытая заявка на заказ; деньги
двигает только менеджер — возвратом через кассу или отказом с причиной.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.orders.models import FulfillmentStatus, Order
from apps.orders.models import PaymentStatus as OrderPaymentStatus

from . import refund_requests
from .models import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    RefundRequest,
    RefundRequestStatus,
)

User = get_user_model()
CANCEL_OR_REFUND = "apps.payments.atolpay.service.cancel_or_refund"


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+79005550001", password="pass12345")


@pytest.fixture
def paid_order(user):
    order = Order.objects.create(
        order_number="П-RF-001",
        user=user,
        total=Decimal("3000.00"),
        payment_method="online",
        payment_status=OrderPaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.CONFIRMED,
    )
    Payment.objects.create(
        order=order,
        provider=PaymentProvider.ATOLPAY,
        provider_order_id="RF001",
        provider_payment_id="RF001",
        status=PaymentStatus.SUCCEEDED,
        amount=order.total,
        idempotency_key="order-RF001",
    )
    return order


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def url(order):
    return f"/api/payments/orders/{order.order_number}/refund-request/"


# ─────────────────────────── правила ───────────────────────────


@pytest.mark.django_db
def test_заявка_по_оплаченному_заказу_принимается(paid_order, user):
    req = refund_requests.create_request(
        paid_order.pk, user_id=user.pk, reason="defect", comment="Не включается"
    )
    assert req.status == RefundRequestStatus.PENDING
    assert refund_requests.block_reason(paid_order) == "Заявка на возврат уже на рассмотрении."


@pytest.mark.django_db
def test_неоплаченный_заказ_вернуть_нельзя(paid_order, user):
    Order.objects.filter(pk=paid_order.pk).update(payment_status=OrderPaymentStatus.PENDING)
    with pytest.raises(ValidationError, match="оплаченный онлайн"):
        refund_requests.create_request(paid_order.pk, user_id=user.pk, reason="changed_mind")


@pytest.mark.django_db
def test_срок_14_дней_после_получения(paid_order, user):
    now = timezone.now()
    paid_order.fulfillment_status = FulfillmentStatus.COMPLETED
    paid_order.completed_at = now - timedelta(days=13)
    paid_order.save()
    assert refund_requests.block_reason(paid_order, now=now) is None
    assert "14 дней" in refund_requests.block_reason(paid_order, now=now + timedelta(days=2))


@pytest.mark.django_db
def test_выполнение_заказа_ставит_дату_получения(paid_order):
    from apps.orders.fulfillment import advance_fulfillment

    for target in ("assembling", "ready", "completed"):
        advance_fulfillment(paid_order.pk, target)
    paid_order.refresh_from_db()
    assert paid_order.completed_at is not None
    assert refund_requests.request_deadline(paid_order) == paid_order.completed_at + timedelta(
        days=14
    )


@pytest.mark.django_db
def test_другое_без_пояснения_не_принимается(paid_order, user):
    with pytest.raises(ValidationError):
        refund_requests.create_request(paid_order.pk, user_id=user.pk, reason="other")


# ─────────────────────────── решение менеджера ───────────────────────────


@pytest.mark.django_db
def test_одобрение_возвращает_деньги_через_кассу(paid_order, user):
    req = refund_requests.create_request(paid_order.pk, user_id=user.pk, reason="defect")
    with mock.patch(CANCEL_OR_REFUND, return_value={}) as kassa:
        done = refund_requests.approve(req.pk, amount=None, actor_id=None)

    kassa.assert_called_once()
    assert done.status == RefundRequestStatus.REFUNDED
    assert done.refund.amount == Decimal("3000.00")
    paid_order.refresh_from_db()
    assert paid_order.payment_status == OrderPaymentStatus.REFUNDED


@pytest.mark.django_db
def test_частичный_возврат(paid_order, user):
    req = refund_requests.create_request(paid_order.pk, user_id=user.pk, reason="incomplete")
    with mock.patch(CANCEL_OR_REFUND, return_value={}):
        refund_requests.approve(req.pk, amount=Decimal("500"), actor_id=None)
    paid_order.refresh_from_db()
    assert paid_order.payment_status == OrderPaymentStatus.PARTIALLY_REFUNDED
    # После частичного возврата можно подать ещё одну заявку.
    assert refund_requests.block_reason(paid_order) is None


@pytest.mark.django_db
def test_сбой_кассы_оставляет_заявку_на_рассмотрении(paid_order, user):
    req = refund_requests.create_request(paid_order.pk, user_id=user.pk, reason="defect")
    with mock.patch(CANCEL_OR_REFUND, side_effect=RuntimeError("касса лежит")):
        with pytest.raises(ValidationError, match="Касса не приняла"):
            refund_requests.approve(req.pk, amount=None, actor_id=None)
    req.refresh_from_db()
    assert req.status == RefundRequestStatus.PENDING


@pytest.mark.django_db
def test_сумма_больше_оплаченной_не_проходит(paid_order, user):
    req = refund_requests.create_request(paid_order.pk, user_id=user.pk, reason="defect")
    with mock.patch(CANCEL_OR_REFUND, return_value={}) as kassa:
        with pytest.raises(ValidationError, match="превышает"):
            refund_requests.approve(req.pk, amount=Decimal("9999"), actor_id=None)
    kassa.assert_not_called()
    req.refresh_from_db()
    assert req.status == RefundRequestStatus.PENDING


@pytest.mark.django_db
def test_повторное_одобрение_не_создаёт_второй_возврат(paid_order, user):
    req = refund_requests.create_request(paid_order.pk, user_id=user.pk, reason="defect")
    with mock.patch(CANCEL_OR_REFUND, return_value={}):
        refund_requests.approve(req.pk, amount=None, actor_id=None)
        with pytest.raises(ValidationError, match="Деньги возвращены"):
            refund_requests.approve(req.pk, amount=None, actor_id=None)


@pytest.mark.django_db
def test_отказ_требует_причину(paid_order, user):
    req = refund_requests.create_request(paid_order.pk, user_id=user.pk, reason="changed_mind")
    with pytest.raises(ValidationError):
        refund_requests.reject(req.pk, comment="  ", actor_id=None)
    done = refund_requests.reject(req.pk, comment="Товар был в употреблении", actor_id=None)
    assert done.status == RefundRequestStatus.REJECTED
    # После отказа можно подать новую заявку.
    assert refund_requests.block_reason(paid_order) is None


# ─────────────────────────── API покупателя ───────────────────────────


@pytest.mark.django_db
def test_api_показывает_и_принимает_заявку(api, paid_order):
    state = api.get(url(paid_order)).json()
    assert state["can_request"] is True
    assert {"value": "defect", "label": "Брак или неисправность"} in state["reasons"]

    resp = api.post(url(paid_order), {"reason": "defect", "comment": "Искрит"}, format="json")
    assert resp.status_code == 201
    body = resp.json()
    assert body["can_request"] is False
    assert body["requests"][0]["status_label"] == "На рассмотрении"

    again = api.post(url(paid_order), {"reason": "defect"}, format="json")
    assert again.status_code == 409
    assert RefundRequest.objects.count() == 1


@pytest.mark.django_db
def test_api_чужой_заказ_не_виден(paid_order):
    stranger = User.objects.create_user(phone="+79005550002", password="pass12345")
    client = APIClient()
    client.force_authenticate(user=stranger)
    assert client.get(url(paid_order)).status_code == 404
    assert client.post(url(paid_order), {"reason": "defect"}, format="json").status_code == 404


@pytest.mark.django_db
def test_api_гостю_недоступно(paid_order):
    assert APIClient().get(url(paid_order)).status_code in (401, 403)


@pytest.mark.django_db
def test_api_без_оплаты_блок_не_объясняет_отказ(api, paid_order):
    Order.objects.filter(pk=paid_order.pk).update(
        payment_method="cash", payment_status=OrderPaymentStatus.PENDING
    )
    state = api.get(url(paid_order)).json()
    assert state["can_request"] is False
    assert state["block_reason"] is None


@pytest.mark.django_db
def test_api_неверная_причина(api, paid_order):
    assert api.post(url(paid_order), {"reason": "xxx"}, format="json").status_code == 400
    assert api.post(url(paid_order), {"reason": "other"}, format="json").status_code == 400


# ─────────────────────────── админка ───────────────────────────


@pytest.mark.django_db
def test_админка_возврат_только_по_post(client, paid_order, user):
    admin_user = User.objects.create_superuser(phone="+79005550009", password="pass12345")
    client.force_login(admin_user)
    req = refund_requests.create_request(paid_order.pk, user_id=user.pk, reason="defect")
    decide = f"/admin/payments/refundrequest/{req.pk}/decide/approve/"

    with mock.patch(CANCEL_OR_REFUND, return_value={}) as kassa:
        page = client.get(decide)
        assert page.status_code == 200
        assert "Да, вернуть деньги" in page.content.decode()
        kassa.assert_not_called()

        assert client.get(f"/admin/payments/refundrequest/{req.pk}/change/").status_code == 200
        resp = client.post(decide, {"amount": "1000"})
        assert resp.status_code == 302
    req.refresh_from_db()
    assert req.status == RefundRequestStatus.REFUNDED
    assert req.refund.amount == Decimal("1000")


@pytest.mark.django_db
def test_админка_отказ(client, paid_order, user):
    admin_user = User.objects.create_superuser(phone="+79005550009", password="pass12345")
    client.force_login(admin_user)
    req = refund_requests.create_request(paid_order.pk, user_id=user.pk, reason="defect")
    decide = f"/admin/payments/refundrequest/{req.pk}/decide/reject/"
    assert "Напишите покупателю" in client.post(decide, {"comment": ""}).content.decode()
    assert client.post(decide, {"comment": "Нет чека"}).status_code == 302
    req.refresh_from_db()
    assert req.decision_comment == "Нет чека"
