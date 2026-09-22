"""После ручного расчёта доставки: резерв удерживается заново, покупатель получает
письмо со ссылкой на оплату (DRF-2299, оплата позже)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Product, ProductStatus
from apps.notifications.models import NotificationLog
from apps.orders.models import DeliveryCalcStatus, Order, OrderItem, ReservationStatus

User = get_user_model()


@pytest.fixture(autouse=True)
def _env(settings):
    settings.SITE_URL = "https://proff58.ru"
    settings.DEFAULT_FROM_EMAIL = "site@proff58.ru"
    settings.STAFF_NOTIFICATION_EMAILS = []


@pytest.fixture
def менеджер(db):
    return User.objects.create_superuser(phone="+79993330077", password="pwd12345")


@pytest.fixture
def товар(db):
    return Product.objects.create(
        name="Дрель",
        code_1c="dp-1",
        slug="dp-1",
        unit="шт",
        price=Decimal("1000.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("5"),
        reserved_quantity=Decimal("0"),
    )


def _заказ(товар, **kw):
    defaults = dict(
        order_number="DP-1",
        total=Decimal("2000.00"),
        payment_method="online",
        delivery_method="courier",
        delivery_zone="cdek",
        delivery_calc_status=DeliveryCalcStatus.MANUAL_REQUIRED,
        delivery_cost=None,
        reservation_status=ReservationStatus.RELEASED,  # 30 минут давно прошли
        customer_phone="+79001112233",
        customer_email="buyer@example.com",
        access_token="guest-tok-123",
    )
    defaults.update(kw)
    order = Order.objects.create(**defaults)
    OrderItem.objects.create(
        order=order,
        product=товар,
        name="Дрель",
        quantity=2,
        price_final=Decimal("1000.00"),
        line_total=Decimal("2000.00"),
    )
    return order


def _post(client, order, **overrides):
    data = {
        "order_number": order.order_number,
        "currency": order.currency,
        "fulfillment_status": order.fulfillment_status,
        "payment_status": order.payment_status,
        "sync_1c_status": order.sync_1c_status,
        "user": order.user_id or "",
        "customer_type": order.customer_type,
        "customer_name": "",
        "customer_phone": order.customer_phone,
        "customer_email": order.customer_email,
        "company_name": "",
        "inn": "",
        "kpp": "",
        "legal_address": "",
        "delivery_method": order.delivery_method,
        "delivery_address": "",
        "delivery_zone": order.delivery_zone,
        "comment": "",
        "payment_method": order.payment_method,
        "tracking_number": "",
        "total": "2700.00",
        "delivery_cost": "700.00",
        "delivery_calc_status": order.delivery_calc_status,
        "items-TOTAL_FORMS": "0",
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
        "_save": "1",
    }
    data.update(overrides)
    return client.post(reverse("admin:orders_order_change", args=[order.pk]), data)


@pytest.mark.django_db
def test_расчёт_удерживает_резерв_и_шлёт_гостю_ссылку_с_токеном(
    client, менеджер, товар, django_capture_on_commit_callbacks
):
    order = _заказ(товар)
    client.force_login(менеджер)
    with django_capture_on_commit_callbacks(execute=True):
        resp = _post(client, order)
    assert resp.status_code == 302, resp.content[:300]

    order.refresh_from_db()
    товар.refresh_from_db()
    assert order.delivery_calc_status == DeliveryCalcStatus.CALCULATED
    assert order.reservation_status == ReservationStatus.HELD
    assert order.reserved_until > timezone.now() + timedelta(hours=23)
    assert товар.available_quantity == Decimal("3") and товар.reserved_quantity == Decimal("2")

    assert len(mail.outbox) == 1
    письмо = mail.outbox[0]
    assert письмо.to == ["buyer@example.com"]
    assert "700.00" in письмо.body and "2700.00" in письмо.body
    assert "https://proff58.ru/order/DP-1/thanks?t=guest-tok-123" in письмо.body
    assert "guest-tok-123" not in письмо.subject


@pytest.mark.django_db
def test_владельцу_ссылка_в_кабинет_и_email_из_аккаунта(
    client, менеджер, товар, django_capture_on_commit_callbacks
):
    user = User.objects.create_user(
        phone="+79001110099", email="owner@example.com", password="x12345678"
    )
    order = _заказ(товар, user=user, customer_email="", access_token="")
    client.force_login(менеджер)
    with django_capture_on_commit_callbacks(execute=True):
        _post(client, order, customer_email="")
    assert mail.outbox[0].to == ["owner@example.com"]
    assert "https://proff58.ru/account/orders/DP-1" in mail.outbox[0].body
    assert "?t=" not in mail.outbox[0].body


@pytest.mark.django_db
def test_без_email_письма_нет_а_менеджер_предупреждён(
    client, менеджер, товар, django_capture_on_commit_callbacks
):
    order = _заказ(товар, customer_email="")
    client.force_login(менеджер)
    with django_capture_on_commit_callbacks(execute=True):
        resp = (
            _post(client, order, customer_email="", follow=True)
            if False
            else _post(client, order, customer_email="")
        )
    assert resp.status_code == 302
    assert mail.outbox == []
    page = client.get(resp["Location"]).content.decode()
    assert "нет e-mail" in page
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.HELD  # резерв всё равно удержан


@pytest.mark.django_db
def test_товара_нет_письма_нет_предупреждение(
    client, менеджер, товар, django_capture_on_commit_callbacks
):
    товар.available_quantity = Decimal("1")
    товар.save(update_fields=["available_quantity"])
    order = _заказ(товар)
    client.force_login(менеджер)
    with django_capture_on_commit_callbacks(execute=True):
        resp = _post(client, order)
    assert mail.outbox == []
    page = client.get(resp["Location"]).content.decode()
    assert "нет в наличии" in page
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.RELEASED
    assert order.delivery_calc_status == DeliveryCalcStatus.CALCULATED  # стоимость сохранена


@pytest.mark.django_db
def test_повторное_сохранение_без_изменений_не_шлёт_второе_письмо(
    client, менеджер, товар, django_capture_on_commit_callbacks
):
    order = _заказ(товар)
    client.force_login(менеджер)
    with django_capture_on_commit_callbacks(execute=True):
        _post(client, order)
    order.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        _post(client, order, delivery_calc_status="calculated")
    assert len(mail.outbox) == 1
    assert NotificationLog.objects.filter(event="customer_delivery_calculated").count() == 1


@pytest.mark.django_db
def test_правка_стоимости_даёт_новое_письмо(
    client, менеджер, товар, django_capture_on_commit_callbacks
):
    order = _заказ(товар)
    client.force_login(менеджер)
    with django_capture_on_commit_callbacks(execute=True):
        _post(client, order)
    order.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        _post(
            client,
            order,
            delivery_calc_status="calculated",
            delivery_cost="900.00",
            total="2900.00",
        )
    assert len(mail.outbox) == 2
    assert "900.00" in mail.outbox[1].body


@pytest.mark.django_db
@pytest.mark.parametrize("kw", [{"payment_status": "paid"}, {"payment_method": "cash"}])
def test_оплаченному_или_не_онлайн_письма_нет(
    client, менеджер, товар, django_capture_on_commit_callbacks, kw
):
    order = _заказ(товар, **kw)
    client.force_login(менеджер)
    with django_capture_on_commit_callbacks(execute=True):
        _post(
            client, order, payment_status=order.payment_status, payment_method=order.payment_method
        )
    assert mail.outbox == []
