"""Оплата через АТОЛ Pay: чек, регистрация платежа, callback.

Смысловой центр этих тестов — две вещи, которых нет у ЮKassa:

1. **Чек**. Касса не примет платёж, если сумма позиций не сойдётся с суммой
   заказа до копейки, а между ними стоят промо-скидки и неделимые цены.
2. **Callback без подписи**. Единственная защита — секрет в query и перезапрос
   статуса; тело уведомления доверия не заслуживает, и подделанный «оплачено»
   не должен помечать заказ оплаченным.
"""

from decimal import Decimal
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse

from apps.orders.models import FulfillmentStatus, Order, OrderItem
from apps.orders.models import PaymentStatus as OrderPaymentStatus

from .atolpay import service as atolpay
from .atolpay.client import AtolPayError, to_kopecks
from .atolpay.receipt import ReceiptError, build_positions, build_receipt
from .models import Payment, PaymentProvider, PaymentStatus, Refund

pytestmark = pytest.mark.django_db

CALLBACK_SECRET = "secret-callback-token"


@pytest.fixture(autouse=True)
def atolpay_settings(settings):
    settings.PAYMENTS_ENABLED = True
    settings.PAYMENT_PROVIDER = "atolpay"
    settings.ATOLPAY_BASE_URL = "https://sandbox.atolpay.test/v1/ecom"
    settings.ATOLPAY_TOKEN = "test-token"
    settings.ATOLPAY_CALLBACK_TOKEN = CALLBACK_SECRET
    settings.ATOLPAY_RECEIPT_ENABLED = True
    settings.SITE_URL = "https://dev.proff58.ru"


def make_order(total="5000.00", **kwargs) -> Order:
    defaults = {
        "order_number": "П-20260907-ABC123",
        "total": Decimal(total),
        "currency": "RUB",
        "customer_phone": "+79001234567",
        "customer_email": "buyer@example.com",
        "payment_method": "online",
        "access_token": "guest-token-123",
    }
    return Order.objects.create(**{**defaults, **kwargs})


def add_item(order, name="Перфоратор", price="5000.00", qty=1, **kwargs):
    price = Decimal(price)
    return OrderItem.objects.create(
        order=order,
        name=name,
        unit=kwargs.pop("unit", "шт"),
        price_final=price,
        quantity=qty,
        line_total=price * qty,
        **kwargs,
    )


def positions_total(positions) -> int:
    return sum(p["price"] * p["quantity"] // 1000 for p in positions)


# ═══════════════ ЧЕК ═══════════════


class TestЧек:
    def test_сумма_позиций_равна_сумме_заказа(self):
        order = make_order()
        add_item(order)

        assert positions_total(build_positions(order)) == to_kopecks(order.total)

    def test_доставка_отдельной_позицией(self):
        order = make_order(total="5350.00", delivery_cost=Decimal("350.00"))
        add_item(order)

        positions = build_positions(order)

        assert positions[-1]["name"] == "Доставка"
        assert positions[-1]["price"] == 35000
        assert positions_total(positions) == 535000

    def test_промо_скидка_строки_уменьшает_позицию(self):
        """Скидка разложена по строкам: чек считается по цене со скидкой."""
        order = make_order(total="4500.00", items_discount_total=Decimal("500.00"))
        add_item(order, promo_discount=Decimal("500.00"))

        positions = build_positions(order)

        assert positions_total(positions) == 450000

    def test_скидка_на_заказ_разносится_по_строкам(self):
        """Промокод даёт скидку на заказ целиком — по строкам её нет вовсе."""
        order = make_order(total="2700.00", items_discount_total=Decimal("300.00"))
        add_item(order, name="Диск", price="1000.00", qty=1)
        add_item(order, name="Бур", price="2000.00", qty=1)

        assert positions_total(build_positions(order)) == 270000

    def test_неделимая_цена_разбивается_на_две_позиции(self):
        """1000.01 ₽ на 3 шт не делится нацело — остаток уходит отдельной штукой."""
        order = make_order(total="1000.01")
        add_item(order, price="1000.01", qty=3, unit="шт")
        OrderItem.objects.filter(order=order).update(line_total=Decimal("1000.01"))

        positions = build_positions(order)

        assert len(positions) == 2
        assert [p["quantity"] for p in positions] == [2000, 1000]
        assert positions_total(positions) == 100001

    def test_расхождение_больше_округления_не_пробивается(self):
        """Сумма заказа не бьётся с позициями — чек не собираем, платёж не создаём."""
        order = make_order(total="9999.00")
        add_item(order, price="5000.00")

        with pytest.raises(ReceiptError):
            build_positions(order)

    def test_единица_измерения_переводится_в_код(self):
        order = make_order(total="100.00")
        add_item(order, price="100.00", unit="кг")

        assert build_positions(order)[0]["measure"] == 2

    def test_длинное_название_обрезается(self):
        order = make_order(total="100.00")
        add_item(order, name="Перфоратор " * 40, price="100.00")

        assert len(build_positions(order)[0]["name"]) == 128

    def test_чек_содержит_почту_и_сно(self, settings):
        settings.ATOLPAY_SNO = 1
        order = make_order()
        add_item(order)

        receipt = build_receipt(order)

        assert receipt["buyer"] == {"email": "buyer@example.com"}
        assert receipt["sno"] == 1
        assert receipt["providerId"] == 100

    def test_фискализацию_можно_выключить(self, settings):
        settings.ATOLPAY_RECEIPT_ENABLED = False
        order = make_order()
        add_item(order)

        assert build_receipt(order) is None


# ═══════════════ НОМЕР ЗАКАЗА ДЛЯ КАССЫ ═══════════════


class TestНомерДляКассы:
    def test_кириллица_превращается_в_латиницу(self):
        """АТОЛ не принимает «П-…»: в orderId только латиница, цифры и :+-_."""
        assert atolpay.ascii_order_id("П-20260907-ABC123") == "P-20260907-ABC123"

    def test_повторная_попытка_получает_суффикс(self):
        assert atolpay.ascii_order_id("П-20260907-ABC123", 2) == "P-20260907-ABC123-2"

    def test_длина_не_превышает_лимит_альфы(self):
        assert len(atolpay.ascii_order_id("П-" + "X" * 60, 3)) <= 36


# ═══════════════ РЕГИСТРАЦИЯ ПЛАТЕЖА ═══════════════

REPLY = {"orderId": "P-20260907-ABC123", "amount": 500000, "paymentUrl": "https://pay.test/1"}


class TestРегистрацияПлатежа:
    @mock.patch("apps.payments.atolpay.service.register_payment", return_value=REPLY)
    def test_запрос_собран_по_контракту_кассы(self, api):
        order = make_order()
        add_item(order)

        payment = atolpay.create_payment(order)

        body = api.call_args.args[0]
        assert body["amount"] == 500000  # копейки, целое число
        assert body["orderId"] == "P-20260907-ABC123"
        assert body["sessionType"] == "oneStep"
        assert body["additionalProps"]["returnUrl"].endswith("/thanks")
        assert CALLBACK_SECRET in body["additionalProps"]["notificationUrl"]
        assert positions_total(body["receipt"]["positions"]) == 500000
        assert payment.provider == PaymentProvider.ATOLPAY
        assert payment.confirmation_url == "https://pay.test/1"

    @mock.patch("apps.payments.atolpay.service.register_payment", return_value=REPLY)
    def test_повторный_вызов_не_плодит_платежи(self, api):
        order = make_order()
        add_item(order)

        first = atolpay.create_payment(order)
        second = atolpay.create_payment(order)

        assert first.pk == second.pk
        assert api.call_count == 1

    @mock.patch("apps.payments.atolpay.service.register_payment")
    def test_занятый_номер_повторяется_со_следующим(self, api):
        """Касса знает такой orderId — берём следующий, иначе оплатить нельзя."""
        api.side_effect = [AtolPayError(code="PAYMENT_EXISTS"), REPLY]
        order = make_order()
        add_item(order)

        payment = atolpay.create_payment(order)

        assert api.call_count == 2
        assert api.call_args_list[1].args[0]["orderId"] == "P-20260907-ABC123-2"
        assert payment.provider_order_id == "P-20260907-ABC123-2"

    @mock.patch("apps.payments.atolpay.service.register_payment", return_value=REPLY)
    def test_после_отказа_банка_создаётся_новый_платёж(self, api):
        """Статус 3 «повтор невозможен» — прежний orderId касса второй раз не примет."""
        order = make_order()
        add_item(order)
        first = atolpay.create_payment(order)
        Payment.objects.filter(pk=first.pk).update(status=PaymentStatus.CANCELED)

        second = atolpay.create_payment(order)

        assert second.pk != first.pk
        assert second.provider_order_id == "P-20260907-ABC123-2"

    def test_нулевая_сумма_не_отправляется_в_кассу(self):
        order = make_order(total="0.00")

        with pytest.raises(ValueError):
            atolpay.create_payment(order)


# ═══════════════ CALLBACK ═══════════════


def callback_url() -> str:
    return reverse("payments:atolpay-callback")


def post_callback(client, payload, token=CALLBACK_SECRET):
    query = f"?t={token}" if token is not None else ""
    return client.post(
        f"{callback_url()}{query}",
        data=payload,
        content_type="application/json",
    )


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def paid_order():
    order = make_order()
    add_item(order)
    return order


@pytest.fixture
def payment(paid_order):
    return Payment.objects.create(
        order=paid_order,
        provider=PaymentProvider.ATOLPAY,
        provider_order_id="P-20260907-ABC123",
        provider_payment_id="P-20260907-ABC123",
        status=PaymentStatus.PENDING,
        amount=paid_order.total,
        currency="RUB",
        idempotency_key="atolpay-P-20260907-ABC123",
    )


SUCCESS_PAYLOAD = {
    "status": "success",
    "orderId": "P-20260907-ABC123",
    "amount": 500000,
    "type": "payment",
    "paymentStatus": 1,
    "sessionType": "oneStep",
}


class TestДоступКCallback:
    def test_без_секрета_не_принимаем(self, client, payment):
        assert post_callback(client, SUCCESS_PAYLOAD, token=None).status_code == 403
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.PENDING

    def test_чужой_секрет_не_принимаем(self, client, payment):
        assert post_callback(client, SUCCESS_PAYLOAD, token="подделка").status_code == 403

    def test_пустой_секрет_в_настройках_закрывает_вход(self, client, payment, settings):
        """Не заданный секрет — это «оплата не настроена», а не «пускать всех»."""
        settings.ATOLPAY_CALLBACK_TOKEN = ""

        assert post_callback(client, SUCCESS_PAYLOAD, token="").status_code == 403

    def test_выключенная_оплата_отвечает_503(self, client, payment, settings):
        settings.PAYMENTS_ENABLED = False

        assert post_callback(client, SUCCESS_PAYLOAD).status_code == 503


class TestОбработкаCallback:
    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 1})
    def test_оплата_подтверждена_кассой(self, _status, client, payment, paid_order):
        resp = post_callback(client, SUCCESS_PAYLOAD)

        assert resp.status_code == 200
        payment.refresh_from_db()
        paid_order.refresh_from_db()
        assert payment.status == PaymentStatus.SUCCEEDED
        assert payment.paid_at is not None
        assert paid_order.payment_status == OrderPaymentStatus.PAID

    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 3})
    def test_подделанное_уведомление_не_помечает_заказ_оплаченным(
        self, _status, client, payment, paid_order
    ):
        """Тело говорит «оплачено», касса — «ошибка». Верим кассе."""
        resp = post_callback(client, SUCCESS_PAYLOAD)

        assert resp.status_code == 200
        payment.refresh_from_db()
        paid_order.refresh_from_db()
        assert payment.status == PaymentStatus.CANCELED
        assert paid_order.payment_status == OrderPaymentStatus.PENDING

    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 1})
    def test_повторное_уведомление_ничего_не_меняет(self, _status, client, payment, paid_order):
        post_callback(client, SUCCESS_PAYLOAD)
        post_callback(client, SUCCESS_PAYLOAD)

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.SUCCEEDED
        assert Payment.objects.filter(order=paid_order).count() == 1

    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 1})
    def test_чужая_сумма_отвергается(self, _status, client, payment, paid_order):
        resp = post_callback(client, {**SUCCESS_PAYLOAD, "amount": 100})

        assert resp.status_code == 500  # касса повторит, состояние не поехало
        payment.refresh_from_db()
        paid_order.refresh_from_db()
        assert payment.status == PaymentStatus.PENDING
        assert paid_order.payment_status == OrderPaymentStatus.PENDING

    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 1})
    def test_неизвестный_платёж_не_ошибка(self, _status, client, payment):
        resp = post_callback(client, {**SUCCESS_PAYLOAD, "orderId": "P-НЕТ-ТАКОГО"})

        assert resp.status_code == 200

    @mock.patch(
        "apps.payments.atolpay.service.payment_status",
        side_effect=AtolPayError(code="NETWORK_ERROR"),
    )
    def test_касса_не_ответила_на_проверку(self, _status, client, payment):
        """Без подтверждения статуса ничего не меняем — пусть касса повторит."""
        resp = post_callback(client, SUCCESS_PAYLOAD)

        assert resp.status_code == 500
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.PENDING

    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 1})
    def test_событие_оплаты_публикуется(
        self, _status, client, payment, paid_order, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            post_callback(client, SUCCESS_PAYLOAD)

        assert len(callbacks) >= 2  # payment_succeeded + order_paid

    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 9})
    def test_просроченный_платёж_отменяется(self, _status, client, payment, paid_order):
        post_callback(client, {**SUCCESS_PAYLOAD, "paymentStatus": 9})

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.CANCELED
        paid_order.refresh_from_db()
        assert paid_order.payment_status == OrderPaymentStatus.PENDING


class TestВозвраты:
    @pytest.fixture
    def succeeded(self, payment, paid_order):
        Payment.objects.filter(pk=payment.pk).update(status=PaymentStatus.SUCCEEDED)
        Order.objects.filter(pk=paid_order.pk).update(payment_status=OrderPaymentStatus.PAID)
        payment.refresh_from_db()
        return payment

    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 5})
    def test_возврат_из_лк_кассы_доходит_до_заказа(self, _status, client, succeeded, paid_order):
        """Менеджер вернул деньги в личном кабинете кассы — сайт узнаёт об этом."""
        post_callback(client, {**SUCCESS_PAYLOAD, "type": "refund", "paymentStatus": 5})

        succeeded.refresh_from_db()
        paid_order.refresh_from_db()
        assert succeeded.status == PaymentStatus.REFUNDED
        assert paid_order.payment_status == OrderPaymentStatus.REFUNDED
        assert Refund.objects.filter(payment=succeeded).count() == 1

    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 7})
    def test_частичная_отмена_видна_как_частичный_возврат(
        self, _status, client, succeeded, paid_order
    ):
        post_callback(
            client, {**SUCCESS_PAYLOAD, "type": "cancel", "paymentStatus": 7, "amount": 100000}
        )

        succeeded.refresh_from_db()
        paid_order.refresh_from_db()
        assert succeeded.status == PaymentStatus.PARTIALLY_REFUNDED
        assert paid_order.payment_status == OrderPaymentStatus.PARTIALLY_REFUNDED
        assert Refund.objects.get(payment=succeeded).amount == Decimal("1000.00")

    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 7})
    def test_повтор_уведомления_о_возврате_не_дублирует_строку(
        self, _status, client, succeeded, paid_order
    ):
        """Касса ретраит уведомления — второй раз возврат не проводим."""
        payload = {**SUCCESS_PAYLOAD, "type": "refund", "paymentStatus": 7, "amount": 100000}

        post_callback(client, payload)
        post_callback(client, payload)

        assert Refund.objects.filter(payment=succeeded).count() == 1

    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 4})
    def test_отмена_после_оплаты_это_возврат_денег(self, _status, client, succeeded, paid_order):
        """«Отменён» в день оплаты — деньги вернулись, а не «платёж не состоялся»."""
        post_callback(client, {**SUCCESS_PAYLOAD, "type": "cancel", "paymentStatus": 4})

        succeeded.refresh_from_db()
        paid_order.refresh_from_db()
        assert succeeded.status == PaymentStatus.REFUNDED
        assert paid_order.payment_status == OrderPaymentStatus.REFUNDED


class TestФискализация:
    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 1})
    def test_успешный_чек_сохраняется(self, _status, client, payment):
        post_callback(
            client,
            {
                "status": "success",
                "orderId": "P-20260907-ABC123",
                "type": "fiscal",
                "receiptId": "rcp-1",
                "amount": 500000,
                "receiptType": "sell",
            },
        )

        payment.refresh_from_db()
        assert payment.receipt_id == "rcp-1"
        assert payment.receipt_status == "success"

    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 1})
    def test_несостоявшийся_чек_не_отменяет_оплату(self, _status, client, payment, paid_order):
        """Деньги приняты, чек не пробит — это случай для менеджера, не для отмены."""
        Payment.objects.filter(pk=payment.pk).update(status=PaymentStatus.SUCCEEDED)
        Order.objects.filter(pk=paid_order.pk).update(payment_status=OrderPaymentStatus.PAID)

        post_callback(
            client,
            {
                "status": "fail",
                "orderId": "P-20260907-ABC123",
                "type": "fiscal",
                "receiptId": "rcp-2",
                "errorCode": "SEND_RECEIPT_ERROR",
                "errorMessage": "Провайдер недоступен",
            },
        )

        payment.refresh_from_db()
        paid_order.refresh_from_db()
        assert payment.receipt_status == "fail"
        assert payment.status == PaymentStatus.SUCCEEDED
        assert paid_order.payment_status == OrderPaymentStatus.PAID


class TestПоздняяОплата:
    @mock.patch("apps.payments.atolpay.service.payment_status", return_value={"status": 1})
    def test_отменённый_заказ_не_воскресает(self, _status, client, payment, paid_order):
        """Заказ отменён по таймауту, товар мог уйти другому — деньги разбирает человек."""
        Order.objects.filter(pk=paid_order.pk).update(
            fulfillment_status=FulfillmentStatus.CANCELLED
        )

        post_callback(client, SUCCESS_PAYLOAD)

        payment.refresh_from_db()
        paid_order.refresh_from_db()
        assert payment.status == PaymentStatus.SUCCEEDED  # деньги действительно пришли
        assert paid_order.payment_status == OrderPaymentStatus.PENDING
        assert paid_order.fulfillment_status == FulfillmentStatus.CANCELLED


# ═══════════════ КЛИЕНТ ═══════════════


class TestКлиент:
    @mock.patch("apps.payments.atolpay.client.urllib.request.urlopen")
    def test_токен_уходит_со_схемой_bearer(self, urlopen):
        """Документация АТОЛ обещает «голый токен», касса принимает только Bearer."""
        from .atolpay import client

        resp = mock.MagicMock()
        resp.read.return_value = b'{"status":"success","data":{"status":1}}'
        resp.__enter__.return_value = resp
        urlopen.return_value = resp

        data = client.payment_status("P-1")

        req = urlopen.call_args.args[0]
        assert req.get_header("Authorization") == "Bearer test-token"
        assert req.full_url == "https://sandbox.atolpay.test/v1/ecom/payments/P-1/status"
        assert data == {"status": 1}

    @mock.patch("apps.payments.atolpay.client.urllib.request.urlopen")
    def test_ошибка_в_теле_с_кодом_200_становится_исключением(self, urlopen):
        from .atolpay import client

        resp = mock.MagicMock()
        resp.read.return_value = (
            b'{"status":"error","errorCode":"PAYMENT_SETTINGS_NOT_FOUND","errorMessage":"x"}'
        )
        resp.__enter__.return_value = resp
        urlopen.return_value = resp

        with pytest.raises(AtolPayError) as exc:
            client.register_payment({})
        assert exc.value.code == "PAYMENT_SETTINGS_NOT_FOUND"
