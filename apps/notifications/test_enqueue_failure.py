"""Недоступная очередь не ломает заказ (DRF-2293).

Постановка в Celery идёт из on_commit-колбэков оформления; исключение оттуда дало
бы покупателю 500 при уже созданном заказе. Сбой брокера превращается в строку
failed/retryable с повтором из админки; собственные ошибки задачи (eager-режим)
не маскируются.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from kombu.exceptions import OperationalError

from .admin import NotificationLogAdmin
from .channels import PermanentChannelError
from .models import NotificationChannel, NotificationErrorKind, NotificationLog, NotificationStatus
from .services import notify_staff, send

User = get_user_model()

BROKER_DOWN = OperationalError("Error 111 connecting to redis:6379. Connection refused.")


@pytest.fixture
def получатели(settings):
    settings.STAFF_NOTIFICATION_EMAILS = ["m@example.com"]
    settings.DEFAULT_FROM_EMAIL = "site@example.com"


@pytest.mark.django_db
@mock.patch("apps.notifications.tasks.send_notification_task.delay", side_effect=BROKER_DOWN)
def test_send_при_недоступной_очереди_не_бросает_и_помечает_failed(mock_delay, settings):
    settings.FEATURES = {**settings.FEATURES, "max_chat": True}
    settings.MAX_BOT_TOKEN = "t"
    log = send(
        user=None,
        chat_id=5,
        event="order_paid",
        payload={"order_number": "1"},
        idempotency_key="q-1",
    )
    assert log.status == NotificationStatus.FAILED
    assert log.error_kind == NotificationErrorKind.RETRYABLE
    assert log.error_message.startswith("Очередь недоступна")


@pytest.mark.django_db
@mock.patch("apps.notifications.tasks.send_notification_task.delay", side_effect=BROKER_DOWN)
def test_notify_staff_при_недоступной_очереди(mock_delay, получатели):
    log = notify_staff(
        event="staff_inquiry_created",
        payload={
            "inquiry_id": 1,
            "kind": "Консультация",
            "created_at": "x",
            "product": "—",
            "name": "—",
            "phone": "+7",
            "message": "—",
            "admin_url": "/admin/",
        },
        idempotency_key="q-2",
    )
    assert log.status == NotificationStatus.FAILED and log.channel == NotificationChannel.EMAIL


@pytest.mark.django_db
def test_ошибка_самой_задачи_в_eager_режиме_не_маскируется(получатели):
    """Задача записала честный failed/permanent — enqueue не должен переписать причину."""
    with mock.patch(
        "apps.notifications.channels.email.send_email",
        side_effect=PermanentChannelError("SMTPRecipientsRefused"),
    ):
        log = notify_staff(
            event="staff_order_created",
            payload={
                k: "x"
                for k in (
                    "order_number",
                    "created_at",
                    "customer",
                    "customer_phone",
                    "total",
                    "currency",
                    "items_count",
                    "delivery",
                    "payment",
                    "admin_url",
                )
            },
            idempotency_key="q-3",
        )
    log.refresh_from_db()
    assert log.status == NotificationStatus.FAILED
    assert log.error_kind == NotificationErrorKind.PERMANENT
    assert "Очередь" not in log.error_message


@pytest.mark.django_db
@mock.patch("apps.notifications.tasks.send_notification_task.delay", side_effect=BROKER_DOWN)
def test_повтор_из_админки_при_недоступной_очереди_не_падает(mock_delay, rf):
    log = NotificationLog.objects.create(
        channel=NotificationChannel.MAX,
        event="order_paid",
        chat_id=1,
        text="x",
        status=NotificationStatus.FAILED,
        error_kind=NotificationErrorKind.RETRYABLE,
    )
    admin_instance = NotificationLogAdmin(NotificationLog, AdminSite())
    request = rf.post("/admin/notifications/notificationlog/")
    request._messages = mock.MagicMock()

    admin_instance.retry_failed(request, NotificationLog.objects.filter(pk=log.pk))

    log.refresh_from_db()
    assert log.status == NotificationStatus.FAILED  # не завис в QUEUED
    assert log.error_kind == NotificationErrorKind.RETRYABLE
    assert "Очередь недоступна" in str(request._messages.add.call_args)


@pytest.mark.django_db
def test_упавший_подписчик_order_created_не_ломает_оформление(django_capture_on_commit_callbacks):
    """robust=True у on_commit: ошибка любого подписчика логируется, заказ создан."""
    from decimal import Decimal

    from apps.catalog.models import Product, ProductStatus
    from apps.core import events
    from apps.orders.models import Cart
    from apps.orders.services import add_to_cart, place_order

    product = Product.objects.create(
        name="Т",
        code_1c="rb-1",
        slug="rb-1",
        unit="шт",
        price=Decimal("10.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("5"),
    )
    cart = Cart.objects.create(session_key="rb-sess")
    add_to_cart(cart, product, 1)

    def boom(sender, **kwargs):
        raise RuntimeError("подписчик упал")

    events.order_created.connect(boom, dispatch_uid="test-boom")
    try:
        with django_capture_on_commit_callbacks(execute=True):
            order = place_order(
                cart, customer_data={"customer_name": "Г", "customer_phone": "+79001234567"}
            )
    finally:
        events.order_created.disconnect(boom, dispatch_uid="test-boom")
    assert order.pk is not None
