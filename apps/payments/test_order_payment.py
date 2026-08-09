"""Запуск оплаты заказа с витрины: POST /api/payments/orders/{number}/.

Главное, что проверяем — оформленный заказ не теряется ни при каком исходе:
касса выключена, ключей нет, провайдер лёг, покупатель нажал дважды. Во всех
случаях заказ остаётся, а оплату можно повторить той же кнопкой.
"""

from decimal import Decimal
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.orders.models import FulfillmentStatus, Order
from apps.orders.models import PaymentStatus as OrderPaymentStatus

from .models import Payment, PaymentMethod, PaymentStatus

pytestmark = pytest.mark.django_db


def make_order(**kwargs) -> Order:
    defaults = {
        "order_number": "П-PAY-001",
        "total": Decimal("5000.00"),
        "currency": "RUB",
        "customer_phone": "+79001234567",
        "payment_method": "online",
        "access_token": "guest-token-123",
    }
    return Order.objects.create(**{**defaults, **kwargs})


def url(order: Order) -> str:
    return reverse("payments:order-payment", args=[order.order_number])


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def payments_on(settings):
    """Касса включена — состояние, в котором работают все сценарии оплаты."""
    settings.PAYMENTS_ENABLED = True


@pytest.fixture
def payments_off(settings):
    settings.PAYMENTS_ENABLED = False


YOOKASSA_REPLY = {
    "id": "yoo_new_1",
    "status": "pending",
    "confirmation": {"confirmation_url": "https://yoomoney.test/checkout/yoo_new_1"},
}


class TestДоступКОплате:
    @pytest.fixture(autouse=True)
    def _on(self, payments_on):
        pass

    @mock.patch("apps.payments.services._yookassa_request", return_value=YOOKASSA_REPLY)
    def test_гость_с_токеном_получает_ссылку(self, _api, client):
        order = make_order()

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 200
        assert resp.json()["confirmation_url"] == YOOKASSA_REPLY["confirmation"]["confirmation_url"]

    @mock.patch("apps.payments.services._yookassa_request", return_value=YOOKASSA_REPLY)
    def test_владелец_получает_ссылку_без_токена(self, _api, client):
        user = User.objects.create_user(phone="+79005553311", password="pass12345")
        order = make_order(user=user, access_token="")
        client.force_login(user)

        assert client.post(url(order)).status_code == 200

    # Номер заказа предсказуем, поэтому одного номера мало: без токена чужой
    # заказ оплатить (и узнать о его существовании) нельзя.
    def test_без_токена_чужой_заказ_не_найден(self, client):
        order = make_order()

        assert client.post(url(order)).status_code == 404
        assert client.post(f"{url(order)}?t=не-тот-токен").status_code == 404


class TestСостоянияЗаказа:
    @pytest.fixture(autouse=True)
    def _on(self, payments_on):
        pass

    @mock.patch("apps.payments.services._yookassa_request", return_value=YOOKASSA_REPLY)
    def test_повторный_вызов_возвращает_ту_же_ссылку(self, api, client):
        """Двойной клик и «Повторить оплату» не должны плодить платежи."""
        order = make_order()

        first = client.post(f"{url(order)}?t={order.access_token}")
        second = client.post(f"{url(order)}?t={order.access_token}")

        assert first.json()["confirmation_url"] == second.json()["confirmation_url"]
        assert Payment.objects.filter(order=order).count() == 1
        assert api.call_count == 1  # второй раз в кассу не ходим

    def test_оплаченный_заказ_не_ошибка(self, client):
        """Возврат по старой ссылке после оплаты — норма, а не сбой."""
        order = make_order(payment_status=OrderPaymentStatus.PAID)

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 200
        assert resp.json()["payment_status"] == OrderPaymentStatus.PAID
        assert resp.json()["confirmation_url"] == ""

    def test_счёт_для_организации_онлайн_не_оплачивают(self, client):
        order = make_order(payment_method="invoice")

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 409
        assert resp.json()["code"] == "not_online"

    def test_отменённый_заказ_оплатить_нельзя(self, client):
        order = make_order(fulfillment_status=FulfillmentStatus.CANCELLED)

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 409
        assert resp.json()["code"] == "canceled"


class TestКассаНедоступна:
    def test_выключенная_оплата_отвечает_понятно(self, payments_off, client):
        order = make_order()

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 503
        assert resp.json()["code"] == "payments_disabled"

    @mock.patch(
        "apps.payments.services._yookassa_request",
        side_effect=RuntimeError("YOOKASSA_SHOP_ID/YOOKASSA_SECRET_KEY не настроены"),
    )
    def test_сбой_провайдера_не_теряет_заказ(self, _api, payments_on, client):
        order = make_order()

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 503
        assert resp.json()["code"] == "provider_unavailable"
        order.refresh_from_db()
        assert order.payment_status != OrderPaymentStatus.PAID
        assert Order.objects.filter(pk=order.pk).exists()
        assert not Payment.objects.filter(order=order).exists()

    @mock.patch("apps.payments.services._yookassa_request", return_value=YOOKASSA_REPLY)
    def test_после_сбоя_оплата_повторяется(self, _api, payments_on, client):
        """Касса поднялась — та же кнопка доводит покупателя до оплаты."""
        order = make_order()

        resp = client.post(f"{url(order)}?t={order.access_token}")

        assert resp.status_code == 200
        payment = Payment.objects.get(order=order)
        assert payment.status == PaymentStatus.PENDING
        assert payment.method == PaymentMethod.YOOKASSA
