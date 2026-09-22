"""Письмо сотрудникам о новом заказе (DRF-2296): после коммита, один раз,
без секретов, со ссылкой в админку под входом; сбой уведомления не ломает checkout."""

from __future__ import annotations

from unittest import mock

import pytest
from django.core import mail
from django.db import transaction

from apps.notifications.models import NotificationChannel, NotificationLog, NotificationStatus
from apps.orders.services import add_to_cart, place_order

ГОСТЬ = {"customer_name": "Гость Тестовый", "customer_phone": "+79001234567"}


@pytest.fixture(autouse=True)
def _почта(settings):
    settings.STAFF_NOTIFICATION_EMAILS = ["manager@example.com"]
    settings.DEFAULT_FROM_EMAIL = "site@example.com"
    settings.SITE_URL = "https://proff58.ru"
    settings.ATOLPAY_TOKEN = "secret-atol-token-xyz"
    settings.ONEC_API_KEY = "secret-1c-key-xyz"
    settings.EMAIL_HOST_PASSWORD = "secret-smtp-pass-xyz"


@pytest.mark.django_db
def test_новый_заказ_даёт_одно_письмо_после_коммита(
    cart, product, django_capture_on_commit_callbacks
):
    add_to_cart(cart, product, 2)
    with django_capture_on_commit_callbacks(execute=True):
        order = place_order(cart, customer_data=ГОСТЬ)

    assert len(mail.outbox) == 1
    письмо = mail.outbox[0]
    assert order.order_number in письмо.subject
    assert письмо.to == ["manager@example.com"]
    assert f"/admin/orders/order/{order.pk}/change/" in письмо.body
    assert "https://proff58.ru/admin/" in письмо.body
    assert "Гость Тестовый" in письмо.body and "+79001234567" in письмо.body
    assert "позиций: 1" in письмо.body
    log = NotificationLog.objects.get(idempotency_key=f"staff-order-created-{order.pk}")
    assert log.channel == NotificationChannel.EMAIL and log.status == NotificationStatus.SENT


@pytest.mark.django_db
def test_повторный_обработчик_не_ставит_второе_письмо(
    cart, product, django_capture_on_commit_callbacks
):
    from apps.core import events
    from apps.orders.models import Order

    add_to_cart(cart, product, 1)
    with django_capture_on_commit_callbacks(execute=True):
        order = place_order(cart, customer_data=ГОСТЬ)
    events.order_created.send(sender=Order, order_id=order.pk)  # повтор события
    assert len(mail.outbox) == 1
    assert (
        NotificationLog.objects.filter(idempotency_key=f"staff-order-created-{order.pk}").count()
        == 1
    )


@pytest.mark.django_db
def test_откат_транзакции_не_порождает_письма(cart, product, django_capture_on_commit_callbacks):
    add_to_cart(cart, product, 1)
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                place_order(cart, customer_data=ГОСТЬ)
                raise RuntimeError("откат")
    assert mail.outbox == []
    assert not NotificationLog.objects.exists()


@pytest.mark.django_db
def test_недоступный_брокер_не_ломает_оформление(cart, product, django_capture_on_commit_callbacks):
    add_to_cart(cart, product, 1)
    with mock.patch(
        "apps.notifications.tasks.send_notification_task.delay",
        side_effect=ConnectionError("redis down"),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            order = place_order(cart, customer_data=ГОСТЬ)
    assert order.pk is not None
    log = NotificationLog.objects.get(idempotency_key=f"staff-order-created-{order.pk}")
    assert log.status == NotificationStatus.QUEUED  # строка есть, доставку можно повторить


@pytest.mark.django_db
def test_недоступная_почта_не_ломает_оформление(cart, product, django_capture_on_commit_callbacks):
    from apps.notifications.channels import RetryableChannelError
    from apps.notifications.tasks import send_notification_task

    add_to_cart(cart, product, 1)
    with mock.patch(
        "apps.notifications.channels.email.send_email",
        side_effect=RetryableChannelError("SMTPServerDisconnected"),
    ):
        with mock.patch.object(send_notification_task, "retry", side_effect=Exception("retry")):
            with django_capture_on_commit_callbacks(execute=True):
                order = place_order(cart, customer_data=ГОСТЬ)
    assert order.pk is not None
    log = NotificationLog.objects.get(idempotency_key=f"staff-order-created-{order.pk}")
    assert log.status == NotificationStatus.FAILED


@pytest.mark.django_db
def test_в_письме_нет_секретов_и_ссылка_требует_входа(
    client, cart, product, django_capture_on_commit_callbacks
):
    add_to_cart(cart, product, 1)
    with django_capture_on_commit_callbacks(execute=True):
        order = place_order(cart, customer_data=ГОСТЬ)
    письмо = mail.outbox[0]
    текст = письмо.subject + письмо.body
    for секрет in ("secret-atol-token-xyz", "secret-1c-key-xyz", "secret-smtp-pass-xyz"):
        assert секрет not in текст
    assert "access_token" not in текст and "X-Api-Key" not in текст
    assert str(order.guest_token) not in текст if getattr(order, "guest_token", None) else True

    resp = client.get(f"/admin/orders/order/{order.pk}/change/")
    assert resp.status_code == 302 and "/admin/login/" in resp["Location"]


@pytest.mark.django_db
def test_без_получателей_заказ_оформляется_а_строка_skipped(
    settings, cart, product, django_capture_on_commit_callbacks
):
    settings.STAFF_NOTIFICATION_EMAILS = []
    add_to_cart(cart, product, 1)
    with django_capture_on_commit_callbacks(execute=True):
        order = place_order(cart, customer_data=ГОСТЬ)
    assert mail.outbox == []
    log = NotificationLog.objects.get(idempotency_key=f"staff-order-created-{order.pk}")
    assert log.status == NotificationStatus.SKIPPED
