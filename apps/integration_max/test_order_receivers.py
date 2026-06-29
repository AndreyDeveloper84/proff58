"""Тесты order-receivers: события заказа → notifications.send() (#310)."""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model

from apps.core import events
from apps.core.models import SiteSettings
from apps.orders.models import Order

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
def test_no_notification_without_max_chat_id(mock_send, user_without_max):
    from apps.integration_max import receivers  # noqa: F401

    order = Order.objects.create(
        order_number="П-NO-MAX", user=user_without_max, total=Decimal("1000.00")
    )
    events.order_created.send(sender=Order, order_id=order.id)
    mock_send.assert_not_called()


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
