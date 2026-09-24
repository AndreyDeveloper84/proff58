"""Письма покупателю (T2): подтверждение заказа и смена статуса — после коммита,
один раз на событие, с составом и честной строкой доставки; без e-mail — ничего."""

from __future__ import annotations

import pytest
from django.core import mail
from django.db import transaction

from apps.core import events
from apps.notifications.models import NotificationLog, NotificationStatus
from apps.orders.models import Order
from apps.orders.services import add_to_cart, place_order

ГОСТЬ = {
    "customer_name": "Гость Тестовый",
    "customer_phone": "+79001234567",
    "customer_email": "buyer@example.com",
}


@pytest.fixture(autouse=True)
def _почта(settings):
    settings.STAFF_NOTIFICATION_EMAILS = []
    settings.DEFAULT_FROM_EMAIL = "site@example.com"
    settings.SITE_URL = "https://proff58.ru"


def _customer_mails():
    return [m for m in mail.outbox if m.to == ["buyer@example.com"]]


@pytest.mark.django_db
def test_подтверждение_заказа_с_составом_и_суммами(
    cart, product, django_capture_on_commit_callbacks
):
    add_to_cart(cart, product, 2)
    with django_capture_on_commit_callbacks(execute=True):
        order = place_order(cart, customer_data=ГОСТЬ)

    письма = _customer_mails()
    assert len(письма) == 1
    m = письма[0]
    assert m.subject == f"Заказ №{order.order_number} принят"
    item = order.items.first()
    assert f"{item.name} × 2" in m.body
    assert f"Итого: {order.total:.2f}" in m.body
    assert f"/order/{order.order_number}/thanks" in m.body
    assert order.access_token not in m.body  # токен доступа в письмо не кладём
    log = NotificationLog.objects.get(idempotency_key=f"customer-order-created-{order.pk}")
    assert log.status == NotificationStatus.SENT and log.recipients == "buyer@example.com"


@pytest.mark.django_db
def test_без_email_письма_нет(cart, product, django_capture_on_commit_callbacks):
    add_to_cart(cart, product, 1)
    with django_capture_on_commit_callbacks(execute=True):
        order = place_order(
            cart, customer_data={k: v for k, v in ГОСТЬ.items() if k != "customer_email"}
        )
    assert _customer_mails() == []
    assert not NotificationLog.objects.filter(
        idempotency_key=f"customer-order-created-{order.pk}"
    ).exists()


@pytest.mark.django_db
def test_повтор_события_не_даёт_второго_письма(cart, product, django_capture_on_commit_callbacks):
    add_to_cart(cart, product, 1)
    with django_capture_on_commit_callbacks(execute=True):
        order = place_order(cart, customer_data=ГОСТЬ)
    events.order_created.send(sender=Order, order_id=order.pk)
    assert len(_customer_mails()) == 1


@pytest.mark.django_db
def test_откат_транзакции_не_порождает_письма(cart, product, django_capture_on_commit_callbacks):
    add_to_cart(cart, product, 1)
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                place_order(cart, customer_data=ГОСТЬ)
                raise RuntimeError("откат")
    assert mail.outbox == []


@pytest.mark.django_db
def test_manual_required_не_показывает_доставку_как_бесплатную(
    cart, product, django_capture_on_commit_callbacks
):
    add_to_cart(cart, product, 1)
    with django_capture_on_commit_callbacks(execute=True):
        order = place_order(cart, customer_data=ГОСТЬ)
    Order.objects.filter(pk=order.pk).update(
        delivery_calc_status="manual_required", delivery_cost=None
    )
    mail.outbox.clear()
    NotificationLog.objects.all().delete()
    events.order_created.send(sender=Order, order_id=order.pk)
    body = _customer_mails()[0].body
    assert "Доставка: стоимость уточнит менеджер" in body
    assert "предварительно, без доставки" in body
    assert "бесплатно" not in body


@pytest.mark.django_db
def test_сбой_отправки_не_теряет_заказ(
    cart, product, django_capture_on_commit_callbacks, monkeypatch
):
    from apps.notifications.channels import RetryableChannelError
    from apps.notifications.channels import email as email_channel

    def _boom(*a, **kw):
        raise RetryableChannelError("SMTP down")

    monkeypatch.setattr(email_channel, "send_email", _boom)
    add_to_cart(cart, product, 1)
    with django_capture_on_commit_callbacks(execute=True):
        order = place_order(cart, customer_data=ГОСТЬ)
    assert Order.objects.filter(pk=order.pk).exists()
    log = NotificationLog.objects.get(idempotency_key=f"customer-order-created-{order.pk}")
    assert log.status != NotificationStatus.SENT


@pytest.mark.django_db
def test_смена_статуса_одно_письмо_с_трек_номером(
    cart, product, django_capture_on_commit_callbacks
):
    add_to_cart(cart, product, 1)
    with django_capture_on_commit_callbacks(execute=True):
        order = place_order(cart, customer_data=ГОСТЬ)
    mail.outbox.clear()
    Order.objects.filter(pk=order.pk).update(tracking_number="TRK-1")
    for _ in range(2):  # повторная обработка того же перехода
        events.order_status_changed.send(
            sender=Order, order_id=order.pk, old_status="ready", new_status="shipped"
        )
    письма = _customer_mails()
    assert len(письма) == 1
    assert "передан в доставку" in письма[0].subject
    assert "Трек-номер: TRK-1" in письма[0].body


@pytest.mark.django_db
def test_статус_вне_списка_письма_не_даёт(cart, product, django_capture_on_commit_callbacks):
    add_to_cart(cart, product, 1)
    with django_capture_on_commit_callbacks(execute=True):
        order = place_order(cart, customer_data=ГОСТЬ)
    mail.outbox.clear()
    events.order_status_changed.send(
        sender=Order, order_id=order.pk, old_status="new", new_status="assembling"
    )
    assert _customer_mails() == []
