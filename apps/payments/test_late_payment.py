"""DRF-2736: оплата отменённого заказа и оплата на границе окна резерва.

Страница оплаты у кассы живёт дольше, чем резерв товара, и погасить её нельзя
(``/cancel`` для неоплаченного платежа — ``ORDER_NOT_PAID``, проверено в песочнице
АТОЛ Pay 02.10.2026). Значит, деньги за отменённый заказ прийти могут, и главный
инвариант этих тестов: такие деньги не теряются из виду — заказ становится
«отменён, оплачен», и у менеджера появляется заявка на возврат.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Product, ProductStatus
from apps.core import events
from apps.orders.fulfillment import advance_fulfillment
from apps.orders.models import (
    DeliveryCalcStatus,
    FulfillmentStatus,
    Order,
    OrderItem,
    ReservationStatus,
)
from apps.orders.models import PaymentStatus as OrderPaymentStatus

from . import refund_requests
from .atolpay.client import AtolPayError
from .expiry import expire_one, expire_unpaid_online_orders
from .models import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    RefundReason,
    RefundRequest,
    RefundRequestStatus,
)

pytestmark = pytest.mark.django_db

CALLBACK_SECRET = "secret-callback-token"
STATUS = "apps.payments.atolpay.service.payment_status"
CANCEL_OR_REFUND = "apps.payments.atolpay.service.cancel_or_refund"


@pytest.fixture(autouse=True)
def atolpay_settings(settings):
    settings.PAYMENTS_ENABLED = True
    settings.PAYMENT_PROVIDER = "atolpay"
    settings.ATOLPAY_BASE_URL = "https://sandbox.atolpay.test/v1/ecom"
    settings.ATOLPAY_TOKEN = "test-token"
    settings.ATOLPAY_CALLBACK_TOKEN = CALLBACK_SECRET
    settings.SITE_URL = "https://dev.proff58.ru"
    settings.STAFF_NOTIFICATION_EMAILS = ["manager@example.com"]
    settings.DEFAULT_FROM_EMAIL = "site@example.com"
    settings.PAYMENT_IN_FLIGHT_GRACE_MINUTES = 15


_seq = iter(range(1, 10_000))


def make_product(available="4", reserved="1") -> Product:
    n = next(_seq)
    return Product.objects.create(
        name="Перфоратор",
        code_1c=f"late-{n}",
        slug=f"late-{n}",
        price=Decimal("5000.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal(available),
        reserved_quantity=Decimal(reserved),
    )


def make_order(product=None, *, minutes_left: int = -1, **kwargs) -> Order:
    n = next(_seq)
    defaults = {
        "order_number": f"П-LATE-{n}",
        "total": Decimal("5000.00"),
        "currency": "RUB",
        "customer_name": "Иван",
        "customer_phone": "+79001234567",
        "customer_email": "buyer@example.com",
        "payment_method": "online",
        "payment_status": OrderPaymentStatus.PENDING,
        "fulfillment_status": FulfillmentStatus.NEW,
        "reservation_status": ReservationStatus.HELD,
        "reserved_until": timezone.now() + timedelta(minutes=minutes_left),
        "access_token": f"guest-token-{n}",
    }
    order = Order.objects.create(**{**defaults, **kwargs})
    OrderItem.objects.create(
        order=order,
        product=product,
        name="Перфоратор",
        unit="шт",
        price_final=Decimal("5000.00"),
        quantity=1,
        line_total=Decimal("5000.00"),
    )
    return order


def make_payment(order: Order, status: str = PaymentStatus.PENDING, suffix: str = "") -> Payment:
    provider_id = f"LATE{order.pk}{suffix}"
    return Payment.objects.create(
        order=order,
        provider=PaymentProvider.ATOLPAY,
        provider_order_id=provider_id,
        provider_payment_id=provider_id,
        status=status,
        amount=order.total,
        currency="RUB",
        idempotency_key=f"atolpay-{provider_id}",
    )


def cancelled(order: Order, payment_status: str = OrderPaymentStatus.EXPIRED) -> Order:
    """Заказ отменён: автоматикой (expired) либо покупателем/менеджером (pending)."""
    Order.objects.filter(pk=order.pk).update(
        fulfillment_status=FulfillmentStatus.CANCELLED,
        payment_status=payment_status,
        reservation_status=ReservationStatus.RELEASED,
    )
    order.refresh_from_db()
    return order


def paid_callback(payment: Payment, client: Client | None = None):
    """Уведомление кассы «оплачен» — через настоящую ручку, с перезапросом статуса."""
    payload = {
        "status": "success",
        "orderId": payment.provider_order_id,
        "amount": int(payment.amount * 100),
        "type": "payment",
        "paymentStatus": 1,
    }
    with mock.patch(STATUS, return_value={"status": 1}):
        return (client or Client()).post(
            f"{reverse('payments:atolpay-callback')}?t={CALLBACK_SECRET}",
            data=payload,
            content_type="application/json",
        )


def release_reservation_for_test():
    """Настоящая функция снятия резерва — для обёрток с побочным эффектом."""
    from apps.orders.reservation import release_reservation

    return release_reservation


def by_code(codes: dict[str, int | Exception]):
    """Подмена ``/status``: код кассы (или исключение) по ``provider_order_id``."""

    def fake(order_id):
        value = codes[order_id]
        if isinstance(value, Exception):
            raise value
        return {"status": value}

    return mock.patch(STATUS, side_effect=fake)


# ═══════════════ ПОЗДНЯЯ ОПЛАТА ═══════════════


class TestПоздняяОплата:
    @pytest.mark.parametrize(
        "payment_status",
        [OrderPaymentStatus.EXPIRED, OrderPaymentStatus.PENDING],
        ids=["отменён автоматикой", "отменён покупателем или менеджером"],
    )
    def test_заказ_становится_отменён_оплачен_и_получает_заявку(
        self, payment_status, django_capture_on_commit_callbacks
    ):
        product = make_product(available="5", reserved="0")
        order = cancelled(make_order(product), payment_status)
        payment = make_payment(order)

        with django_capture_on_commit_callbacks(execute=True):
            resp = paid_callback(payment)

        assert resp.status_code == 200
        payment.refresh_from_db()
        order.refresh_from_db()
        assert payment.status == PaymentStatus.SUCCEEDED
        assert order.payment_status == OrderPaymentStatus.PAID
        # Заказ не воскресает: товар мог уйти другому покупателю.
        assert order.fulfillment_status == FulfillmentStatus.CANCELLED
        assert "вернём деньги" in order.display_status

        request = RefundRequest.objects.get(order=order)
        assert request.status == RefundRequestStatus.PENDING
        assert request.reason == RefundReason.OTHER
        assert request.comment == refund_requests.LATE_PAYMENT_COMMENT

        # Остаток не тронут: отменённый заказ товар не занимает.
        product.refresh_from_db()
        assert product.available_quantity == Decimal("5")
        assert product.reserved_quantity == Decimal("0")

    def test_гостевой_заказ_тоже_получает_заявку(self, django_capture_on_commit_callbacks):
        """Гость сам заявку подать не может — её подаёт сайт."""
        order = cancelled(make_order())
        assert order.user_id is None
        payment = make_payment(order)

        with django_capture_on_commit_callbacks(execute=True):
            paid_callback(payment)

        request = RefundRequest.objects.get(order=order)
        assert request.user_id is None

    def test_сотрудники_узнают_о_заявке_письмом(self, django_capture_on_commit_callbacks):
        from django.core import mail

        order = cancelled(make_order())
        payment = make_payment(order)

        with django_capture_on_commit_callbacks(execute=True):
            paid_callback(payment)

        letters = [m for m in mail.outbox if m.to == ["manager@example.com"]]
        assert len(letters) == 1
        assert order.order_number in letters[0].subject
        assert "Оплата поступила после отмены заказа" in letters[0].body

    def test_события_оплаты_не_издаются(self, django_capture_on_commit_callbacks):
        """«Заказ оплачен, собираем» по отменённому заказу — неправда, и резерв
        списывать не за что."""
        order = cancelled(make_order())
        payment = make_payment(order)
        seen = []

        def on_event(sender, **kwargs):
            seen.append(kwargs)

        events.payment_succeeded.connect(on_event, dispatch_uid="late-test-succeeded")
        events.order_paid.connect(on_event, dispatch_uid="late-test-paid")
        try:
            with django_capture_on_commit_callbacks(execute=True):
                paid_callback(payment)
        finally:
            events.payment_succeeded.disconnect(dispatch_uid="late-test-succeeded")
            events.order_paid.disconnect(dispatch_uid="late-test-paid")

        assert seen == []

    def test_повтор_уведомления_не_плодит_заявки(self, django_capture_on_commit_callbacks):
        order = cancelled(make_order())
        payment = make_payment(order)

        with django_capture_on_commit_callbacks(execute=True):
            paid_callback(payment)
            paid_callback(payment)

        assert RefundRequest.objects.filter(order=order).count() == 1

    def test_открытая_заявка_уже_есть_платёж_всё_равно_зачтён(self):
        """Вторая оплата того же отменённого заказа (два живых платежа): заявка одна,
        но оба платежа отмечены полученными."""
        order = cancelled(make_order())
        first = make_payment(order, suffix="a")
        second = make_payment(order, suffix="b")

        paid_callback(first)
        paid_callback(second)

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.status == second.status == PaymentStatus.SUCCEEDED
        assert RefundRequest.objects.filter(order=order).count() == 1

    def test_сбой_создания_заявки_не_откатывает_оплату(self):
        """Факт «деньги получены» важнее заявки: без него касса повторит уведомление
        несколько раз и бросит, а от денег не останется следа."""
        order = cancelled(make_order())
        payment = make_payment(order)

        with mock.patch.object(
            refund_requests, "create_request", side_effect=RuntimeError("db is down")
        ):
            resp = paid_callback(payment)

        assert resp.status_code == 200
        payment.refresh_from_db()
        order.refresh_from_db()
        assert payment.status == PaymentStatus.SUCCEEDED
        assert order.payment_status == OrderPaymentStatus.PAID
        assert not RefundRequest.objects.filter(order=order).exists()

    def test_возврат_по_заявке_доводит_заказ_до_возвращён(self, django_user_model):
        """Сквозной путь: поздняя оплата → заявка → «Вернуть деньги» → касса сообщает
        о возврате → заказ «отменён, деньги возвращены»."""
        manager = django_user_model.objects.create_superuser(
            phone="+79993330001", password="pwd12345"
        )
        order = cancelled(make_order())
        payment = make_payment(order)
        paid_callback(payment)
        request = RefundRequest.objects.get(order=order)

        with mock.patch(CANCEL_OR_REFUND, return_value={"status": "success"}):
            done = refund_requests.approve(request.pk, amount=None, actor_id=manager.pk)
        assert done.status == RefundRequestStatus.REFUNDED
        assert done.refund.amount == order.total
        order.refresh_from_db()
        assert order.payment_status == OrderPaymentStatus.REFUNDED

        # Следом касса сама сообщает о возврате (статус 5): второй строки возврата
        # и второго уведомления покупателю быть не должно.
        with mock.patch(STATUS, return_value={"status": 5}):
            Client().post(
                f"{reverse('payments:atolpay-callback')}?t={CALLBACK_SECRET}",
                data={
                    "orderId": payment.provider_order_id,
                    "type": "payment",
                    "paymentStatus": 5,
                    "amount": int(order.total * 100),
                },
                content_type="application/json",
            )

        order.refresh_from_db()
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.REFUNDED
        assert payment.refunds.count() == 1
        assert order.payment_status == OrderPaymentStatus.REFUNDED
        assert order.fulfillment_status == FulfillmentStatus.CANCELLED
        assert order.display_status == "Заказ отменён"

    def test_в_1с_такой_заказ_не_уходит(self):
        from apps.sync_1c.use_cases import export_new_orders

        order = cancelled(make_order())
        paid_callback(make_payment(order))

        _log, items = export_new_orders()

        assert items == []


# ═══════════════ ЗАЯВКА ПО ОТМЕНЁННОМУ ЗАКАЗУ ═══════════════


class TestОтменаОплаченногоЗаказа:
    """Менеджер отменил уже оплаченный заказ (товара не оказалось, покупатель
    передумал по телефону): деньги тоже должны попасть в очередь на возврат."""

    def _paid(self, **kwargs) -> Order:
        order = make_order(
            make_product(),
            payment_status=OrderPaymentStatus.PAID,
            reservation_status=ReservationStatus.CONFIRMED,
            **kwargs,
        )
        make_payment(order, PaymentStatus.SUCCEEDED)
        return order

    def test_отмена_заводит_заявку(self, django_capture_on_commit_callbacks):
        order = self._paid()

        with django_capture_on_commit_callbacks(execute=True):
            advance_fulfillment(order.pk, FulfillmentStatus.CANCELLED, actor_id=None)

        request = RefundRequest.objects.get(order=order)
        assert request.comment == refund_requests.CANCELLED_PAID_COMMENT
        assert request.status == RefundRequestStatus.PENDING

    def test_админка_предупреждает_о_возврате_до_отмены(self, client, django_user_model):
        manager = django_user_model.objects.create_superuser(
            phone="+79993330003", password="pwd12345"
        )
        client.force_login(manager)
        order = self._paid()

        page = client.get(
            reverse("admin:orders_order_advance", args=[order.pk, "cancelled"])
        ).content.decode()

        assert "появится заявка на возврат" in page

    def test_отмена_неоплаченного_заявку_не_заводит(self, django_capture_on_commit_callbacks):
        order = make_order(make_product())
        make_payment(order)

        with django_capture_on_commit_callbacks(execute=True):
            advance_fulfillment(order.pk, FulfillmentStatus.CANCELLED, actor_id=None)

        assert not RefundRequest.objects.exists()

    def test_оплата_не_через_кассу_заявку_не_заводит(self, django_capture_on_commit_callbacks):
        """Счёт организации оплачен переводом: платежа кассы нет, кнопкой вернуть нечего."""
        order = make_order(
            make_product(),
            payment_method="invoice",
            payment_status=OrderPaymentStatus.PAID,
            reservation_status=ReservationStatus.CONFIRMED,
        )

        with django_capture_on_commit_callbacks(execute=True):
            advance_fulfillment(order.pk, FulfillmentStatus.CANCELLED, actor_id=None)

        assert not RefundRequest.objects.exists()

    def test_другие_переходы_заявку_не_заводят(self, django_capture_on_commit_callbacks):
        order = self._paid()

        with django_capture_on_commit_callbacks(execute=True):
            advance_fulfillment(order.pk, FulfillmentStatus.CONFIRMED, actor_id=None)

        assert not RefundRequest.objects.exists()

    def test_отмена_от_1с_тоже_заводит_заявку(self, django_capture_on_commit_callbacks):
        from apps.sync_1c.use_cases import confirm_orders

        order = self._paid(fulfillment_status=FulfillmentStatus.CONFIRMED)
        Order.objects.filter(pk=order.pk).update(sync_1c_status="exported")

        with django_capture_on_commit_callbacks(execute=True):
            confirm_orders(
                [{"order_number": order.order_number, "fulfillment_status": "cancelled"}]
            )

        order.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.CANCELLED
        assert RefundRequest.objects.filter(order=order).count() == 1

    def test_сбой_заявки_не_мешает_остальным_подписчикам(self):
        order = cancelled(self._paid(), OrderPaymentStatus.PAID)

        with mock.patch.object(
            refund_requests, "ensure_request_for_cancelled", side_effect=RuntimeError("boom")
        ) as ensure:
            # send (не send_robust): исключение подписчика вылетело бы отсюда наружу.
            events.order_status_changed.send(
                sender=Order, order_id=order.pk, old_status="new", new_status="cancelled"
            )

        ensure.assert_called_once()


class TestРешениеПоЗаявкеОтменённогоЗаказа:
    """Заказ отменён, деньги у магазина. Менеджер по-прежнему решает сам, но тупиков
    быть не должно: вернуть остаток после частичного возврата, закрыть заявку, если
    деньги вернули в кабинете кассы, — всё это возможно; удалить заявку — нет."""

    @pytest.fixture
    def request_(self):
        order = cancelled(make_order())
        paid_callback(make_payment(order))
        return RefundRequest.objects.get(order=order)

    def test_вернуть_всё_после_частичного_возврата(self, request_):
        """«Вернуть деньги» с пустой суммой — это остаток, а не вся сумма платежа:
        раньше после частичного возврата кнопка упиралась в «сумма превышает остаток»."""
        payment = request_.order.payments.get()
        with mock.patch(CANCEL_OR_REFUND, return_value={"status": "success"}):
            from .services import refund

            refund(payment, Decimal("1000.00"))  # часть вернули раньше, мимо заявки
            done = refund_requests.approve(request_.pk, amount=None, actor_id=None)

        assert done.status == RefundRequestStatus.REFUNDED
        assert done.refund.amount == Decimal("4000.00")
        request_.order.refresh_from_db()
        assert request_.order.payment_status == OrderPaymentStatus.REFUNDED

    def test_отказ_возможен_когда_деньги_вернули_в_кабинете_кассы(self, request_):
        done = refund_requests.reject(
            request_.pk, comment="Деньги возвращены через кабинет кассы.", actor_id=None
        )

        assert done.status == RefundRequestStatus.REJECTED

    def test_админка_предупреждает_об_отказе_и_о_частичной_сумме(
        self, client, request_, django_user_model
    ):
        manager = django_user_model.objects.create_superuser(
            phone="+79993330002", password="pwd12345"
        )
        client.force_login(manager)

        reject = client.get(
            reverse("admin:payments_refundrequest_decide", args=[request_.pk, "reject"])
        ).content.decode()
        assert "деньги останутся у магазина" in reject

        approve = client.get(
            reverse("admin:payments_refundrequest_decide", args=[request_.pk, "approve"])
        ).content.decode()
        assert "Оставьте поле суммы пустым" in approve
        assert 'name="amount"' in approve

    def test_обычная_заявка_без_предупреждений(self, client, django_user_model):
        """Заказ не отменён — страница решения прежняя."""
        manager = django_user_model.objects.create_superuser(
            phone="+79993330004", password="pwd12345"
        )
        client.force_login(manager)
        order = make_order(
            payment_status=OrderPaymentStatus.PAID, fulfillment_status=FulfillmentStatus.CONFIRMED
        )
        make_payment(order, PaymentStatus.SUCCEEDED)
        request = refund_requests.create_request(
            order.pk, user_id=None, reason=RefundReason.DEFECT, comment=""
        )

        for decision in ("approve", "reject"):
            page = client.get(
                reverse("admin:payments_refundrequest_decide", args=[request.pk, decision])
            ).content.decode()
            assert "Заказ отменён" not in page

    def test_заявку_нельзя_удалить(self, client, request_, django_user_model):
        """Удаление обходило бы любую защиту: заказ «отменён, оплачен» без заявки."""
        manager = django_user_model.objects.create_superuser(
            phone="+79993330005", password="pwd12345"
        )
        client.force_login(manager)

        resp = client.post(
            reverse("admin:payments_refundrequest_delete", args=[request_.pk]), {"post": "yes"}
        )
        assert resp.status_code == 403
        resp = client.post(
            reverse("admin:payments_refundrequest_changelist"),
            {"action": "delete_selected", "_selected_action": [request_.pk], "post": "yes"},
        )
        assert RefundRequest.objects.filter(pk=request_.pk).exists()

    def test_второй_оплаченный_платёж_не_теряется_после_возврата_первого(self):
        """Обе страницы оплаты сработали. Возврат по заявке закрывает один платёж —
        заказ не становится «возвращён», а на второй платёж заводится новая заявка."""
        order = cancelled(make_order())
        first = make_payment(order, suffix="a")
        second = make_payment(order, suffix="b")
        paid_callback(first)
        paid_callback(second)
        request = RefundRequest.objects.get(order=order)

        with mock.patch(CANCEL_OR_REFUND, return_value={"status": "success"}):
            refund_requests.approve(request.pk, amount=None, actor_id=None)

        order.refresh_from_db()
        assert order.payment_status == OrderPaymentStatus.PARTIALLY_REFUNDED
        assert "вернём деньги" in order.display_status
        open_requests = RefundRequest.objects.filter(
            order=order, status=RefundRequestStatus.PENDING
        )
        assert open_requests.count() == 1
        assert open_requests.get().comment == refund_requests.SECOND_PAYMENT_COMMENT

        with mock.patch(CANCEL_OR_REFUND, return_value={"status": "success"}):
            refund_requests.approve(open_requests.get().pk, amount=None, actor_id=None)

        order.refresh_from_db()
        assert order.payment_status == OrderPaymentStatus.REFUNDED
        assert not RefundRequest.objects.filter(
            order=order, status=RefundRequestStatus.PENDING
        ).exists()

    def test_частичный_возврат_не_плодит_новых_заявок(self, request_):
        """Удержание части суммы — решение менеджера, автоматика с ним не спорит."""
        with mock.patch(CANCEL_OR_REFUND, return_value={"status": "success"}):
            refund_requests.approve(request_.pk, amount=Decimal("4500.00"), actor_id=None)

        assert refund_requests.heal_missing_requests() == 0
        assert RefundRequest.objects.filter(order=request_.order).count() == 1


class TestСамовосстановлениеЗаявок:
    """Заказ «отменён, оплачен» вовсе без заявки: создание сорвалось либо заказ
    отменили оплаченным до появления автоматики."""

    def _orphan(self) -> Order:
        order = cancelled(make_order(), OrderPaymentStatus.PAID)
        make_payment(order, PaymentStatus.SUCCEEDED)
        return order

    def test_заявка_заводится(self):
        order = self._orphan()

        assert refund_requests.heal_missing_requests() == 1

        request = RefundRequest.objects.get(order=order)
        assert request.comment == refund_requests.HEALED_COMMENT
        assert refund_requests.heal_missing_requests() == 0  # повтор ничего не плодит

    def test_после_сбоя_создания_заявку_заводит_следующий_прогон_janitor(self):
        from .tasks import expire_unpaid_online_orders as task

        order = cancelled(make_order())
        payment = make_payment(order)
        with mock.patch.object(
            refund_requests, "create_request", side_effect=RuntimeError("db is down")
        ):
            paid_callback(payment)
        assert not RefundRequest.objects.filter(order=order).exists()

        task()

        assert RefundRequest.objects.filter(order=order).count() == 1

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"fulfillment_status": FulfillmentStatus.NEW},  # заказ жив
            {"payment_status": OrderPaymentStatus.REFUNDED},  # деньги уже вернули
            {"payment_status": OrderPaymentStatus.EXPIRED},  # денег не было
        ],
    )
    def test_чужие_заказы_не_трогает(self, kwargs):
        order = self._orphan()
        Order.objects.filter(pk=order.pk).update(**kwargs)

        assert refund_requests.heal_missing_requests() == 0

    def test_отклонённую_заявку_не_пересоздаёт(self):
        order = self._orphan()
        refund_requests.heal_missing_requests()
        request = RefundRequest.objects.get(order=order)
        refund_requests.reject(request.pk, comment="Возвращено через кассу.", actor_id=None)

        assert refund_requests.heal_missing_requests() == 0

    def test_счёт_организации_не_трогает(self):
        """Оплата не через кассу: платежа нет, кнопкой возвращать нечего."""
        cancelled(make_order(payment_method="invoice"), OrderPaymentStatus.PAID)

        assert refund_requests.heal_missing_requests() == 0


# ═══════════════ АВТООТМЕНА: ЧТО ГОВОРИТ КАССА ═══════════════


class TestАвтоотменаПоСтатусуКассы:
    @pytest.mark.parametrize("code", [0, 3, 4, 6, 9, 12])
    def test_оплаты_нет_заказ_отменяется(self, code):
        product = make_product()
        order = make_order(product)
        payment = make_payment(order)

        with by_code({payment.provider_order_id: code}):
            assert expire_one(order.pk) is True

        order.refresh_from_db()
        product.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.CANCELLED
        assert order.payment_status == OrderPaymentStatus.EXPIRED
        assert order.reservation_status == ReservationStatus.RELEASED
        assert product.available_quantity == Decimal("5")

    def test_оплачен_заказ_становится_оплаченным_сразу(self, django_capture_on_commit_callbacks):
        """Вебхук потерялся: раньше janitor лишь не отменял заказ, и тот вечно висел
        «ожидает оплаты» с деньгами в кассе. Теперь статус применяется сразу."""
        product = make_product()
        order = make_order(product)
        payment = make_payment(order)

        with by_code({payment.provider_order_id: 1}):
            with django_capture_on_commit_callbacks(execute=True):
                assert expire_one(order.pk) is False

        order.refresh_from_db()
        payment.refresh_from_db()
        product.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.NEW
        assert order.payment_status == OrderPaymentStatus.PAID
        assert payment.status == PaymentStatus.SUCCEEDED
        # События изданы: резерв списан подписчиком оплаты.
        assert order.reservation_status == ReservationStatus.CONFIRMED
        assert product.reserved_quantity == Decimal("0")
        assert product.available_quantity == Decimal("4")

    @pytest.mark.parametrize("code", [-1, 5, 7, 8, 11, 99])
    def test_непонятный_ответ_заказ_не_трогаем(self, code):
        order = make_order(make_product())
        payment = make_payment(order)

        with by_code({payment.provider_order_id: code}):
            assert expire_one(order.pk) is False

        order.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.NEW
        assert order.payment_status == OrderPaymentStatus.PENDING

    @pytest.mark.parametrize("code", [2, 10])
    def test_покупатель_в_банке_ждём_но_не_вечно(self, code):
        """Банк ещё не ответил или идёт 3-D Secure: отменить сейчас — получить «деньги
        списаны, заказ отменён». После отсрочки зависший статус заказ не держит."""
        product = make_product()
        order = make_order(product, minutes_left=-5)
        payment = make_payment(order)

        with by_code({payment.provider_order_id: code}):
            assert expire_one(order.pk) is False
            order.refresh_from_db()
            assert order.fulfillment_status == FulfillmentStatus.NEW

            Order.objects.filter(pk=order.pk).update(
                reserved_until=timezone.now() - timedelta(minutes=16)
            )
            assert expire_one(order.pk) is True

        order.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.CANCELLED

    def test_два_живых_платежа_один_в_полёте_ждём(self):
        order = make_order(make_product(), minutes_left=-5)
        old = make_payment(order, suffix="a")
        new = make_payment(order, suffix="b")

        with by_code({old.provider_order_id: 0, new.provider_order_id: 10}):
            assert expire_one(order.pk) is False

        order.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.NEW

    def test_оплачен_старший_из_двух_платежей(self, django_capture_on_commit_callbacks):
        """Спрашиваем по каждому живому платежу, а не только по последнему."""
        order = make_order(make_product())
        old = make_payment(order, suffix="a")
        new = make_payment(order, suffix="b")

        with by_code({old.provider_order_id: 1, new.provider_order_id: 0}):
            with django_capture_on_commit_callbacks(execute=True):
                assert expire_one(order.pk) is False

        order.refresh_from_db()
        old.refresh_from_db()
        assert order.payment_status == OrderPaymentStatus.PAID
        assert old.status == PaymentStatus.SUCCEEDED

    def test_непонятный_ответ_по_одному_платежу_не_мешает_зачесть_оплату_другого(
        self, django_capture_on_commit_callbacks
    ):
        order = make_order(make_product())
        broken = make_payment(order, suffix="a")
        paid = make_payment(order, suffix="b")

        with by_code({broken.provider_order_id: -1, paid.provider_order_id: 1}):
            with django_capture_on_commit_callbacks(execute=True):
                assert expire_one(order.pk) is False

        order.refresh_from_db()
        assert order.payment_status == OrderPaymentStatus.PAID

    def test_настоящее_уведомление_после_janitor_ничего_не_дублирует(
        self, django_capture_on_commit_callbacks
    ):
        """Janitor применил оплату, следом дошло уведомление кассы: одно событие
        оплаты, одно списание товара."""
        product = make_product()
        order = make_order(product)
        payment = make_payment(order)
        seen = []

        def on_paid(sender, **kwargs):
            seen.append(kwargs["order_id"])

        events.order_paid.connect(on_paid, dispatch_uid="late-test-order-paid")
        try:
            with django_capture_on_commit_callbacks(execute=True):
                with by_code({payment.provider_order_id: 1}):
                    expire_one(order.pk)
                paid_callback(payment)
        finally:
            events.order_paid.disconnect(dispatch_uid="late-test-order-paid")

        assert seen == [order.pk]
        product.refresh_from_db()
        payment.refresh_from_db()
        assert product.available_quantity == Decimal("4")
        assert product.reserved_quantity == Decimal("0")
        # Тело настоящего уведомления сохранено, пометка janitor'а его не затёрла.
        assert payment.webhook_payload.get("orderId") == payment.provider_order_id

    def test_заказ_отменили_пока_janitor_спрашивал_кассу(self, django_capture_on_commit_callbacks):
        """Касса: «оплачен», а заказ в эту секунду отменил менеджер. Оплата не теряется:
        срабатывает ветка поздней оплаты."""
        order = make_order(make_product())
        make_payment(order)

        def paid_and_cancelled(order_id):
            cancelled(order, OrderPaymentStatus.PENDING)
            return {"status": 1}

        with mock.patch(STATUS, side_effect=paid_and_cancelled):
            with django_capture_on_commit_callbacks(execute=True):
                assert expire_one(order.pk) is False

        order.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.CANCELLED
        assert order.payment_status == OrderPaymentStatus.PAID
        assert RefundRequest.objects.filter(order=order).count() == 1

    def test_сбой_связи_по_второму_платежу_не_отбрасывает_оплату_первого(
        self, django_capture_on_commit_callbacks
    ):
        order = make_order(make_product())
        paid = make_payment(order, suffix="a")
        unreachable = make_payment(order, suffix="b")
        down = AtolPayError(code="NETWORK_ERROR", message="timeout")

        with by_code({paid.provider_order_id: 1, unreachable.provider_order_id: down}):
            with django_capture_on_commit_callbacks(execute=True):
                assert expire_one(order.pk) is False

        order.refresh_from_db()
        assert order.payment_status == OrderPaymentStatus.PAID

    def test_ошибка_кассы_по_платежу_заказ_не_отменяет(self):
        order = make_order(make_product())
        payment = make_payment(order)
        unknown = AtolPayError(code="ORDER_NOT_FOUND", message="нет такого", http_status=404)

        with by_code({payment.provider_order_id: unknown}):
            assert expire_one(order.pk) is False

        order.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.NEW


class TestАвтоотменаГраницы:
    def test_заказ_с_ручным_расчётом_доставки_не_отменяется(self):
        """Оплатить такой заказ нельзя — значит, и «не оплачен вовремя» к нему не
        относится. Раньше робот отменял его через 30–35 минут после оформления."""
        order = make_order(
            make_product(),
            delivery_calc_status=DeliveryCalcStatus.MANUAL_REQUIRED,
            delivery_cost=None,
        )

        assert expire_unpaid_online_orders() == 0
        assert expire_one(order.pk) is False

        order.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.NEW

        # Менеджер посчитал доставку, покупатель так и не оплатил — обычная отмена.
        Order.objects.filter(pk=order.pk).update(
            delivery_calc_status=DeliveryCalcStatus.CALCULATED, delivery_cost=Decimal("500")
        )
        assert expire_unpaid_online_orders() == 1

    def test_покупатель_узнаёт_об_отмене(self, django_capture_on_commit_callbacks):
        """Страница оплаты у кассы ещё открыта — без письма он оплатит отменённый заказ."""
        from django.core import mail

        order = make_order(make_product())

        with django_capture_on_commit_callbacks(execute=True):
            assert expire_one(order.pk) is True

        letters = [m for m in mail.outbox if m.to == ["buyer@example.com"]]
        assert len(letters) == 1
        assert "отменён" in letters[0].subject
        assert "Оплата не поступила в срок" in letters[0].body
        assert "не оплачивайте" in letters[0].body

    def test_упавший_подписчик_отмены_не_роняет_прогон(self, django_capture_on_commit_callbacks):
        product = make_product(available="3", reserved="2")
        first = make_order(product)
        second = make_order(product)

        calls = []

        def boom(sender, *, order_id, **kwargs):
            calls.append(order_id)
            raise RuntimeError("MAX недоступен")

        events.order_status_changed.connect(boom, dispatch_uid="late-test-boom")
        try:
            with django_capture_on_commit_callbacks(execute=True):
                assert expire_unpaid_online_orders() == 2
        finally:
            events.order_status_changed.disconnect(dispatch_uid="late-test-boom")

        assert sorted(calls) == sorted([first.pk, second.pk])  # подписчик звался и падал
        for order in (first, second):
            order.refresh_from_db()
            assert order.fulfillment_status == FulfillmentStatus.CANCELLED

    def test_сбой_на_одном_заказе_не_лишает_остальных_обработки(self):
        product = make_product(available="3", reserved="2")
        first = make_order(product, minutes_left=-10)
        second = make_order(product, minutes_left=-5)
        real = release_reservation_for_test()

        def flaky(order_id, **kwargs):
            if order_id == first.pk:
                raise RuntimeError("deadlock detected")
            return real(order_id, **kwargs)

        with mock.patch("apps.payments.expiry.release_reservation", side_effect=flaky):
            assert expire_unpaid_online_orders() == 1

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.fulfillment_status == FulfillmentStatus.NEW  # откатилось целиком
        assert second.fulfillment_status == FulfillmentStatus.CANCELLED

    def test_зачтённый_платёж_при_заказе_ожидает_оплаты_не_отменяется(self):
        """Статус заказа затёрт (сохранение карточки в админке поверх только что
        пришедшей оплаты): платёж успешен, заказ «ожидает оплаты». Раньше кассу
        спрашивали и по такому платежу; теперь живых платежей нет — и без этой
        проверки заказ с деньгами был бы отменён «за неоплату»."""
        product = make_product()
        order = make_order(product)
        make_payment(order, PaymentStatus.SUCCEEDED)

        assert expire_one(order.pk) is False

        order.refresh_from_db()
        product.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.NEW
        assert order.payment_status == OrderPaymentStatus.PAID  # статус исправлен
        assert product.reserved_quantity == Decimal("1")  # резерв не снят

    def test_отмена_и_снятие_резерва_одной_транзакцией(self):
        """Сбой при возврате остатка откатывает и отмену: «отменён, а товар удержан»
        не должно существовать."""
        product = make_product()
        order = make_order(product)

        with mock.patch(
            "apps.payments.expiry.release_reservation", side_effect=RuntimeError("deadlock")
        ):
            with pytest.raises(RuntimeError):
                expire_one(order.pk)

        order.refresh_from_db()
        assert order.fulfillment_status == FulfillmentStatus.NEW
        assert order.payment_status == OrderPaymentStatus.PENDING


class TestПредохранительПрогона:
    """Касса лежит — не стоим по таймауту на каждом из сотен заказов."""

    def _orders(self, count: int):
        product = make_product(available="0", reserved=str(count))
        orders = [make_order(product, minutes_left=-(count - i)) for i in range(count)]
        return orders, [make_payment(o) for o in orders]

    def test_три_сбоя_связи_подряд_прерывают_прогон(self):
        orders, payments = self._orders(5)
        down = AtolPayError(code="NETWORK_ERROR", message="timeout")

        with by_code({p.provider_order_id: down for p in payments}) as status:
            assert expire_unpaid_online_orders() == 0

        assert status.call_count == 3
        assert not Order.objects.filter(fulfillment_status=FulfillmentStatus.CANCELLED).exists()

    def test_ошибка_по_одному_платежу_прогон_не_прерывает(self):
        """Касса не знает платёж (сменили токен, платёж из песочницы): такой заказ
        висит в начале выборки вечно. Три таких раньше остановили бы автоотмену всем."""
        orders, payments = self._orders(5)
        unknown = AtolPayError(code="ORDER_NOT_FOUND", message="нет такого", http_status=404)
        codes = {p.provider_order_id: unknown for p in payments[:3]}
        codes.update({p.provider_order_id: 0 for p in payments[3:]})

        with by_code(codes):
            assert expire_unpaid_online_orders() == 2

        for order in orders[:3]:
            order.refresh_from_db()
            assert order.fulfillment_status == FulfillmentStatus.NEW
        for order in orders[3:]:
            order.refresh_from_db()
            assert order.fulfillment_status == FulfillmentStatus.CANCELLED

    def test_счётчик_сбоев_сбрасывается_после_успешного_ответа(self):
        orders, payments = self._orders(5)
        down = AtolPayError(code="NETWORK_ERROR", message="timeout")
        codes = {
            payments[0].provider_order_id: down,
            payments[1].provider_order_id: down,
            payments[2].provider_order_id: 0,
            payments[3].provider_order_id: down,
            payments[4].provider_order_id: 0,
        }

        with by_code(codes):
            assert expire_unpaid_online_orders() == 2

    def test_заказы_без_платежей_счётчик_сбоев_не_обнуляют(self):
        """Покупатель ушёл до кассы — платежа нет, кассу не спрашивали. Такой заказ
        ничего не говорит о том, жива ли касса."""
        product = make_product(available="0", reserved="6")
        orders = [make_order(product, minutes_left=-(10 - i)) for i in range(6)]
        payments = [make_payment(orders[i]) for i in (0, 2, 4)]  # через одного
        down = AtolPayError(code="NETWORK_ERROR", message="timeout")

        with by_code({p.provider_order_id: down for p in payments}) as status:
            cancelled_count = expire_unpaid_online_orders()

        assert status.call_count == 3
        assert cancelled_count == 2  # заказы без платежей до обрыва прогона отменены
        orders[5].refresh_from_db()
        assert orders[5].fulfillment_status == FulfillmentStatus.NEW  # до него не дошли

    @pytest.mark.parametrize(
        "exc",
        [
            AtolPayError(code="NETWORK_ERROR"),
            AtolPayError(code="NOT_CONFIGURED"),
            AtolPayError(code="", http_status=502),
            AtolPayError(code="AUTH_ERROR", http_status=403),  # протух токен
            AtolPayError(code="", http_status=429),
            AtolPayError(message="ответ не является JSON"),
        ],
    )
    def test_что_считается_сбоем_связи(self, exc):
        orders, payments = self._orders(4)

        with by_code({p.provider_order_id: exc for p in payments}) as status:
            expire_unpaid_online_orders()

        assert status.call_count == 3
