"""Тесты order-receivers: доменные события заказа/оплаты →
notifications.services.create_notification() (#310/#514/#516)."""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from apps.core import events
from apps.core.models import SiteSettings
from apps.notifications.models import Notification, NotificationLog, NotificationStatus
from apps.orders.models import Order
from apps.payments.models import Refund

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


# ═══════════════════════════════════════════════════════════════════════
# order_created / order_paid
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_order_created_sends_notification(mock_create, order):
    from apps.integration_max import receivers  # noqa: F401

    events.order_created.send(sender=Order, order_id=order.id)
    mock_create.assert_called_once()
    kwargs = mock_create.call_args[1]
    assert kwargs["event"] == "order_created"
    assert kwargs["user"] == order.user
    assert kwargs["payload"] == {"order_number": "П-TEST-310"}
    assert kwargs["idempotency_key"] == f"order-created-{order.id}"


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_order_paid_sends_notification(mock_create, order):
    from apps.integration_max import receivers  # noqa: F401

    events.order_paid.send(sender=Order, order_id=order.id, payment_id=1)
    mock_create.assert_called_once()
    kwargs = mock_create.call_args[1]
    assert kwargs["event"] == "order_paid"
    assert kwargs["idempotency_key"] == f"order-paid-{order.id}"


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_order_created_calls_create_notification_even_without_max_link(
    mock_create, user_without_max
):
    """#514: receiver — тонкий адаптер, не решает сам, есть ли получатель.

    Резолв (и решение skip/send) — целиком в create_notification()/send(); здесь
    только фиксируем, что событие всегда доходит туда, а не отфильтровывается на
    уровне receiver дублирующей проверкой (именно так был устроен баг #514).
    """
    from apps.integration_max import receivers  # noqa: F401

    order = Order.objects.create(
        order_number="П-NO-MAX", user=user_without_max, total=Decimal("1000.00")
    )
    events.order_created.send(sender=Order, order_id=order.id)
    mock_create.assert_called_once()


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_no_notification_guest_order(mock_create, db):
    from apps.integration_max import receivers  # noqa: F401

    order = Order.objects.create(order_number="П-GUEST", user=None, total=Decimal("500.00"))
    events.order_created.send(sender=Order, order_id=order.id)
    mock_create.assert_not_called()


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@override_settings(MAX_BOT_TOKEN="test-token")
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_order_created_sends_via_canonical_max_account(mock_max_send, user_without_max):
    """Регрессия #514, сквозной сценарий: MaxAccount.chat_id есть, легаси-поле
    User.max_chat_id пусто → уведомление реально уходит (без мока create_notification)."""
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
@mock.patch("apps.notifications.services.create_notification")
def test_duplicate_receiver_connect_no_duplicate_delivery(mock_create, order):
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
    mock_create.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# #516 — fulfillment transition matrix
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@pytest.mark.parametrize(
    "new_status, expected_event",
    [
        ("confirmed", "order_confirmed"),
        ("ready", "order_ready"),
        ("shipped", "order_shipped"),
        ("completed", "order_delivered"),
        ("cancelled", "order_cancelled"),
    ],
)
@mock.patch("apps.notifications.services.create_notification")
def test_fulfillment_transition_matrix(mock_create, order, new_status, expected_event):
    """AC #516: каждый перечисленный реальный переход создаёт ровно одно уведомление."""
    from apps.integration_max import receivers  # noqa: F401

    events.order_status_changed.send(
        sender=Order, order_id=order.id, old_status="x", new_status=new_status
    )
    mock_create.assert_called_once()
    kwargs = mock_create.call_args[1]
    assert kwargs["event"] == expected_event
    assert kwargs["idempotency_key"] == f"order-status-{order.id}-{new_status}"


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_assembling_does_not_notify(mock_create, order):
    """Scope #516: assembling намеренно не уведомляет в MVP."""
    from apps.integration_max import receivers  # noqa: F401

    events.order_status_changed.send(
        sender=Order, order_id=order.id, old_status="confirmed", new_status="assembling"
    )
    mock_create.assert_not_called()


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_unknown_status_does_not_notify(mock_create, order):
    """Немаппленный статус — whitelist по докам, а не сокрытие бага."""
    from apps.integration_max import receivers  # noqa: F401

    events.order_status_changed.send(
        sender=Order, order_id=order.id, old_status="x", new_status="some_future_status"
    )
    mock_create.assert_not_called()


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_ready_pickup_note(mock_create, user_with_max):
    """AC #516: ready учитывает способ получения в тексте — самовывоз."""
    from apps.delivery.models import DeliveryType
    from apps.integration_max import receivers  # noqa: F401

    order = Order.objects.create(
        order_number="П-PICKUP",
        user=user_with_max,
        total=Decimal("1000.00"),
        delivery_method=DeliveryType.PICKUP,
    )
    events.order_status_changed.send(
        sender=Order, order_id=order.id, old_status="confirmed", new_status="ready"
    )
    assert "самовывоза" in mock_create.call_args[1]["payload"]["ready_note"]


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_ready_courier_note(mock_create, user_with_max):
    """AC #516: ready учитывает способ получения в тексте — курьер."""
    from apps.delivery.models import DeliveryType
    from apps.integration_max import receivers  # noqa: F401

    order = Order.objects.create(
        order_number="П-COURIER",
        user=user_with_max,
        total=Decimal("1000.00"),
        delivery_method=DeliveryType.COURIER,
    )
    events.order_status_changed.send(
        sender=Order, order_id=order.id, old_status="confirmed", new_status="ready"
    )
    note = mock_create.call_args[1]["payload"]["ready_note"]
    assert "доставку" in note
    assert "самовывоза" not in note


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_shipped_includes_tracking_when_present(mock_create, user_with_max):
    """AC #516: shipped добавляет трек-номер только при наличии — есть."""
    from apps.integration_max import receivers  # noqa: F401

    order = Order.objects.create(
        order_number="П-TRACK",
        user=user_with_max,
        total=Decimal("1000.00"),
        tracking_number="ABC123",
    )
    events.order_status_changed.send(
        sender=Order, order_id=order.id, old_status="ready", new_status="shipped"
    )
    assert "ABC123" in mock_create.call_args[1]["payload"]["tracking_note"]


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_shipped_no_tracking_note_when_absent(mock_create, order):
    """AC #516: shipped добавляет трек-номер только при наличии — нет."""
    from apps.integration_max import receivers  # noqa: F401

    events.order_status_changed.send(
        sender=Order, order_id=order.id, old_status="ready", new_status="shipped"
    )
    assert mock_create.call_args[1]["payload"]["tracking_note"] == ""


# ═══════════════════════════════════════════════════════════════════════
# #516 — возврат (ADR-0009 payment_refunded)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_refund_full(mock_create, order):
    from apps.integration_max import receivers  # noqa: F401

    events.payment_refunded.send(
        sender=Refund,
        payment_id=1,
        order_id=order.id,
        refund_id=99,
        amount="5000.00",
        is_full=True,
    )
    mock_create.assert_called_once()
    kwargs = mock_create.call_args[1]
    assert kwargs["event"] == "order_refunded"
    assert kwargs["idempotency_key"] == f"order-refunded-{order.id}-99"


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_refund_partial(mock_create, order):
    from apps.integration_max import receivers  # noqa: F401

    events.payment_refunded.send(
        sender=Refund,
        payment_id=1,
        order_id=order.id,
        refund_id=100,
        amount="500.00",
        is_full=False,
    )
    kwargs = mock_create.call_args[1]
    assert kwargs["event"] == "order_partially_refunded"
    assert kwargs["idempotency_key"] == f"order-refunded-{order.id}-100"


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_refund_no_user_no_notification(mock_create, db):
    from apps.integration_max import receivers  # noqa: F401

    order = Order.objects.create(order_number="П-GUEST-REFUND", user=None, total=Decimal("500.00"))
    events.payment_refunded.send(
        sender=Refund, payment_id=1, order_id=order.id, refund_id=1, amount="500.00", is_full=True
    )
    mock_create.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# #516 — идемпотентность на дублирующий callback/webhook
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@override_settings(MAX_BOT_TOKEN="test-token")
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_duplicate_order_status_event_creates_one_notification(mock_max_send, order):
    """AC #516: повторный callback (напр. 1С ретраит confirm) не создаёт дубль —
    без мока create_notification, реальная идемпотентность через intent+outbox."""
    from apps.integration_max import receivers  # noqa: F401

    for _ in range(2):
        events.order_status_changed.send(
            sender=Order, order_id=order.id, old_status="new", new_status="confirmed"
        )
    assert (
        Notification.objects.filter(idempotency_key=f"order-status-{order.id}-confirmed").count()
        == 1
    )
    assert mock_max_send.call_count == 1


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@override_settings(MAX_BOT_TOKEN="test-token")
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_duplicate_refund_event_creates_one_notification(mock_max_send, order):
    """AC #516: повторная доставка payment_refunded не создаёт дубль."""
    from apps.integration_max import receivers  # noqa: F401

    for _ in range(2):
        events.payment_refunded.send(
            sender=Refund,
            payment_id=1,
            order_id=order.id,
            refund_id=7,
            amount="100.00",
            is_full=True,
        )
    assert Notification.objects.filter(idempotency_key=f"order-refunded-{order.id}-7").count() == 1
    assert mock_max_send.call_count == 1


# ═══════════════════════════════════════════════════════════════════════
# #516 — preferences реально применяются (до этого receivers звали send()
# напрямую, preferences игнорировались)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
def test_order_updates_disabled_preference_skips_without_send(order):
    from apps.integration_max import receivers  # noqa: F401
    from apps.notifications.services import get_or_create_preference

    pref = get_or_create_preference(order.user)
    pref.order_updates_enabled = False
    pref.save()

    with mock.patch("apps.notifications.channels.max.send_message") as mock_max_send:
        events.order_status_changed.send(
            sender=Order, order_id=order.id, old_status="new", new_status="confirmed"
        )

    mock_max_send.assert_not_called()
    notification = Notification.objects.get(idempotency_key=f"order-status-{order.id}-confirmed")
    assert notification.policy_skip_reason == "category_disabled:order_updates"


# ═══════════════════════════════════════════════════════════════════════
# #516 — privacy: payload не содержит id/токенов, только публичные поля
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.services.create_notification")
def test_payload_contains_only_safe_public_fields(mock_create, order):
    """Privacy (#516 AC): whitelist безопасных полей — расширять осознанно, не
    добавлять id/токены молча."""
    from apps.integration_max import receivers  # noqa: F401

    events.order_created.send(sender=Order, order_id=order.id)
    payload = mock_create.call_args[1]["payload"]
    assert set(payload.keys()) <= {"order_number", "ready_note", "tracking_note"}
    assert payload["order_number"] == order.order_number
