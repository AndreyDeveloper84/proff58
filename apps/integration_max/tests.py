"""Тесты уведомлений о заказах через MAX (#48).

Покрытие:
- send_order_notification: success, failure, шаблоны содержат order_number
- Receivers: отправка при наличии chat_id, пропуск без chat_id
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.integration_max.handlers.orders import (
    MESSAGE_TEMPLATES,
    send_order_notification,
)


@override_settings(
    MAX_BOT_TOKEN="test-token",
    MAX_BOT_API_URL="https://platform-api.max.ru",
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class SendOrderNotificationTest(TestCase):
    """Тесты функции send_order_notification."""

    @patch("apps.integration_max.handlers.orders.urllib.request.urlopen")
    def test_success_order_created(self, mock_urlopen):
        """Успешная отправка уведомления order_created."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"ok": true}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = send_order_notification(12345, "order_created", "ORD-001")

        self.assertEqual(result, {"ok": True})
        mock_urlopen.assert_called_once()

        # Проверяем что запрос содержит правильные данные
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        self.assertEqual(req.full_url, "https://platform-api.max.ru/messages")
        self.assertEqual(req.get_header("Authorization"), "test-token")
        self.assertEqual(req.get_header("Content-type"), "application/json")

    @patch("apps.integration_max.handlers.orders.urllib.request.urlopen")
    def test_success_order_paid(self, mock_urlopen):
        """Успешная отправка уведомления order_paid."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"ok": true}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = send_order_notification(12345, "order_paid", "ORD-002")

        self.assertEqual(result, {"ok": True})

    @patch("apps.integration_max.handlers.orders.urllib.request.urlopen")
    def test_failure_raises(self, mock_urlopen):
        """При сетевой ошибке пробрасывается URLError."""
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("connection refused")

        with self.assertRaises(urllib.error.URLError):
            send_order_notification(12345, "order_created", "ORD-003")

    def test_unknown_event_raises_value_error(self):
        """Неизвестное событие вызывает ValueError."""
        with self.assertRaises(ValueError):
            send_order_notification(12345, "nonexistent_event", "ORD-004")

    def test_templates_contain_order_number(self):
        """Все шаблоны содержат placeholder {order_number}."""
        for event, template in MESSAGE_TEMPLATES.items():
            self.assertIn(
                "{order_number}",
                template,
                f"Шаблон {event} не содержит {{order_number}}",
            )

    @patch("apps.integration_max.handlers.orders.urllib.request.urlopen")
    def test_shipped_with_extra(self, mock_urlopen):
        """order_shipped с трек-номером в extra."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"ok": true}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = send_order_notification(12345, "order_shipped", "ORD-005", extra=" Трек: ABC123")

        self.assertEqual(result, {"ok": True})
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        import json

        payload = json.loads(req.data.decode("utf-8"))
        self.assertIn("ORD-005", payload["text"])
        self.assertIn("Трек: ABC123", payload["text"])


@override_settings(
    MAX_BOT_TOKEN="test-token",
    MAX_BOT_API_URL="https://platform-api.max.ru",
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class ReceiverTest(TestCase):
    """Тесты receivers: подписки на доменные события."""

    def setUp(self):
        self.user_with_chat = User.objects.create_user(
            phone="+79991112233",
            password="testpass",
            max_chat_id=99999,
        )
        self.user_without_chat = User.objects.create_user(
            phone="+79994445566",
            password="testpass",
        )

    @patch("apps.integration_max.receivers.send_order_notification_task")
    def test_order_created_with_chat_id(self, mock_task):
        """При order_created + user с max_chat_id отправляется уведомление."""
        from apps.orders.models import Order

        order = Order.objects.create(
            order_number="TST-001",
            user=self.user_with_chat,
        )

        from apps.core.events import order_created

        order_created.send(sender=self.__class__, order_id=order.pk)

        mock_task.delay.assert_called_once_with(99999, "order_created", "TST-001")

    @patch("apps.integration_max.receivers.send_order_notification_task")
    def test_order_created_without_chat_id(self, mock_task):
        """При order_created + user без max_chat_id уведомление НЕ отправляется."""
        from apps.orders.models import Order

        order = Order.objects.create(
            order_number="TST-002",
            user=self.user_without_chat,
        )

        from apps.core.events import order_created

        order_created.send(sender=self.__class__, order_id=order.pk)

        mock_task.delay.assert_not_called()

    @patch("apps.integration_max.receivers.send_order_notification_task")
    def test_order_created_guest_order(self, mock_task):
        """Гостевой заказ (без user) — уведомление НЕ отправляется."""
        from apps.orders.models import Order

        order = Order.objects.create(
            order_number="TST-003",
            user=None,
        )

        from apps.core.events import order_created

        order_created.send(sender=self.__class__, order_id=order.pk)

        mock_task.delay.assert_not_called()

    @patch("apps.integration_max.receivers.send_order_notification_task")
    def test_order_paid_with_chat_id(self, mock_task):
        """При order_paid + user с max_chat_id отправляется уведомление."""
        from apps.orders.models import Order

        order = Order.objects.create(
            order_number="TST-004",
            user=self.user_with_chat,
        )

        from apps.core.events import order_paid

        order_paid.send(sender=self.__class__, order_id=order.pk, payment_id=1)

        mock_task.delay.assert_called_once_with(99999, "order_paid", "TST-004")

    @patch("apps.integration_max.receivers.send_order_notification_task")
    def test_order_status_changed_shipped(self, mock_task):
        """При order_status_changed -> shipped уведомляем."""
        from apps.orders.models import Order

        order = Order.objects.create(
            order_number="TST-005",
            user=self.user_with_chat,
            tracking_number="TRACK-123",
        )

        from apps.core.events import order_status_changed

        order_status_changed.send(
            sender=self.__class__,
            order_id=order.pk,
            old_status="assembling",
            new_status="shipped",
        )

        mock_task.delay.assert_called_once_with(
            99999,
            "order_shipped",
            "TST-005",
            " Трек-номер: TRACK-123",
        )

    @patch("apps.integration_max.receivers.send_order_notification_task")
    def test_order_status_changed_completed(self, mock_task):
        """При order_status_changed -> completed уведомляем."""
        from apps.orders.models import Order

        order = Order.objects.create(
            order_number="TST-006",
            user=self.user_with_chat,
        )

        from apps.core.events import order_status_changed

        order_status_changed.send(
            sender=self.__class__,
            order_id=order.pk,
            old_status="shipped",
            new_status="completed",
        )

        mock_task.delay.assert_called_once_with(99999, "order_completed", "TST-006", "")

    @patch("apps.integration_max.receivers.send_order_notification_task")
    def test_order_status_changed_irrelevant_status(self, mock_task):
        """При переходе в статус, для которого нет шаблона, уведомление НЕ отправляется."""
        from apps.orders.models import Order

        order = Order.objects.create(
            order_number="TST-007",
            user=self.user_with_chat,
        )

        from apps.core.events import order_status_changed

        order_status_changed.send(
            sender=self.__class__,
            order_id=order.pk,
            old_status="new",
            new_status="confirmed",
        )

        mock_task.delay.assert_not_called()
