"""Тесты order-receivers: события заказа → notifications.send() (#310)."""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from apps.core import events
from apps.core.models import SiteSettings
from apps.notifications.models import NotificationLog, NotificationStatus
from apps.orders.models import Order

from .models import MaxAccount

User = get_user_model()


@pytest.fixture
def _enable_max(db):
    s = SiteSettings.get_solo()
    s.max_chat_enabled = True
    s.save()


@pytest.fixture
def user_with_max(db):
    return User.objects.create_user(phone="+79001234567", password="pass", max_chat_id=12345)


@pytest.fixture
def user_without_max(db):
    return User.objects.create_user(phone="+79009999999", password="pass")


@pytest.fixture
def order(user_with_max):
    return Order.objects.create(
        order_number="П-TEST-310",
        user=user_with_max,
        total=Decimal("5000.00"),
    )


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.send")
def test_order_created_sends_notification(mock_send, order):
    from apps.integration_max import receivers  # noqa: F401

    events.order_created.send(sender=Order, order_id=order.id)
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args[1]
    assert call_kwargs["event"] == "order_created"
    assert call_kwargs["user"] == order.user
    assert "П-TEST-310" in str(call_kwargs["payload"])


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.send")
def test_order_paid_sends_notification(mock_send, order):
    from apps.integration_max import receivers  # noqa: F401

    events.order_paid.send(sender=Order, order_id=order.id, payment_id=1)
    mock_send.assert_called_once()
    assert mock_send.call_args[1]["event"] == "order_paid"


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.send")
def test_order_status_shipped(mock_send, order):
    from apps.integration_max import receivers  # noqa: F401

    events.order_status_changed.send(
        sender=Order, order_id=order.id, old_status="ready", new_status="shipped"
    )
    mock_send.assert_called_once()
    assert mock_send.call_args[1]["event"] == "order_shipped"


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.send")
def test_order_status_completed(mock_send, order):
    from apps.integration_max import receivers  # noqa: F401

    events.order_status_changed.send(
        sender=Order, order_id=order.id, old_status="shipped", new_status="completed"
    )
    mock_send.assert_called_once()
    assert mock_send.call_args[1]["event"] == "order_delivered"


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.send")
def test_order_created_calls_send_even_without_max_link(mock_send, user_without_max):
    """#514: receiver — тонкий адаптер, не решает сам, есть ли получатель.

    Резолв (и решение skip/send) — целиком в notifications.send(); здесь только
    фиксируем, что событие всегда доходит до send(), а не отфильтровывается на
    уровне receiver дублирующей проверкой max_chat_id (именно эта дублирующая
    проверка не видела новый MaxAccount-flow и была причиной бага).
    """
    from apps.integration_max import receivers  # noqa: F401

    order = Order.objects.create(
        order_number="П-NO-MAX", user=user_without_max, total=Decimal("1000.00")
    )
    events.order_created.send(sender=Order, order_id=order.id)
    mock_send.assert_called_once()


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.send")
def test_no_notification_guest_order(mock_send, db):
    from apps.integration_max import receivers  # noqa: F401

    order = Order.objects.create(order_number="П-GUEST", user=None, total=Decimal("500.00"))
    events.order_created.send(sender=Order, order_id=order.id)
    mock_send.assert_not_called()


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.send")
def test_idempotency_key_set(mock_send, order):
    from apps.integration_max import receivers  # noqa: F401

    events.order_created.send(sender=Order, order_id=order.id)
    key = mock_send.call_args[1]["idempotency_key"]
    assert f"order-created-{order.id}" == key


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@override_settings(MAX_BOT_TOKEN="test-token")
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_order_created_sends_via_canonical_max_account(mock_max_send, user_without_max):
    """Регрессия #514, сквозной сценарий: MaxAccount.chat_id есть, легаси-поле
    User.max_chat_id пусто → уведомление реально уходит (без мока send())."""
    from apps.integration_max import receivers  # noqa: F401

    MaxAccount.objects.create(
        user=user_without_max,
        max_user_id=42,
        chat_id=777,
        phone=user_without_max.phone,
        phone_verified_at=timezone.now(),
    )
    order = Order.objects.create(
        order_number="П-CANON", user=user_without_max, total=Decimal("2500.00")
    )
    events.order_created.send(sender=Order, order_id=order.id)

    mock_max_send.assert_called_once_with(777, mock.ANY)
    log = NotificationLog.objects.latest("created_at")
    assert log.status == NotificationStatus.SENT
    assert log.chat_id == 777


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.send")
def test_duplicate_receiver_connect_no_duplicate_delivery(mock_send, order):
    """AC #514: повторное подключение receiver (напр. AppConfig.ready() при
    повторной загрузке приложений) не создаёт дублирующую отправку — dispatch_uid
    делает connect() идемпотентным."""
    from apps.integration_max import receivers

    events.order_created.connect(
        receivers._on_order_created, dispatch_uid="integration_max_order_created"
    )
    events.order_created.connect(
        receivers._on_order_created, dispatch_uid="integration_max_order_created"
    )
    events.order_created.send(sender=Order, order_id=order.id)
    mock_send.assert_called_once()
