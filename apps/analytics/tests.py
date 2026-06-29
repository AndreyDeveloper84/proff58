"""Тесты модуля аналитики событий (#55)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.analytics.models import AnalyticsEvent, EventType
from apps.analytics.services import track

User = get_user_model()

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# track() — базовая запись
# ---------------------------------------------------------------------------
class TestTrack:
    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_creates_event(self, _mock):
        event = track(EventType.SEARCH, payload={"query": "дрель"})
        assert event is not None
        assert event.event_type == EventType.SEARCH
        assert event.payload == {"query": "дрель"}

    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_creates_event_with_user(self, _mock):
        user = User.objects.create_user(phone="79001234567", password="test")
        event = track(EventType.PRODUCT_VIEW, user=user, payload={"product_id": 42})
        assert event is not None
        assert event.user == user

    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_creates_event_with_session_id(self, _mock):
        event = track(EventType.ADD_TO_CART, session_id="sess-abc", payload={"product_id": 1})
        assert event is not None
        assert event.session_id == "sess-abc"

    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_empty_payload_defaults_to_dict(self, _mock):
        event = track(EventType.CHECKOUT_START)
        assert event is not None
        assert event.payload == {}


# ---------------------------------------------------------------------------
# PII-фильтрация
# ---------------------------------------------------------------------------
class TestPIIFiltering:
    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_strips_phone(self, _mock):
        event = track(EventType.ORDER_CREATED, payload={"order_id": 1, "phone": "+79001234567"})
        assert "phone" not in event.payload
        assert event.payload["order_id"] == 1

    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_strips_email(self, _mock):
        event = track(EventType.ORDER_CREATED, payload={"order_id": 1, "email": "a@b.com"})
        assert "email" not in event.payload

    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_strips_password(self, _mock):
        event = track(EventType.SEARCH, payload={"query": "x", "password": "secret"})
        assert "password" not in event.payload

    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_strips_card_number(self, _mock):
        event = track(
            EventType.PAYMENT_STARTED,
            payload={"order_id": 1, "card_number": "4111111111111111"},
        )
        assert "card_number" not in event.payload

    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_strips_cvv(self, _mock):
        event = track(EventType.PAYMENT_STARTED, payload={"order_id": 1, "cvv": "123"})
        assert "cvv" not in event.payload

    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_strips_token(self, _mock):
        event = track(EventType.PAYMENT_SUCCESS, payload={"order_id": 1, "token": "tok_xxx"})
        assert "token" not in event.payload

    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_strips_nested_pii(self, _mock):
        event = track(
            EventType.ORDER_CREATED,
            payload={"order_id": 1, "customer": {"name": "Иван", "email": "i@x.ru"}},
        )
        assert "email" not in event.payload["customer"]
        assert event.payload["customer"]["name"] == "Иван"

    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_strips_multiple_pii_keys(self, _mock):
        event = track(
            EventType.PAYMENT_STARTED,
            payload={
                "order_id": 5,
                "phone": "+7",
                "email": "x@y",
                "card_number": "4111",
                "cvv": "000",
                "token": "tok",
                "password": "pw",
            },
        )
        assert event.payload == {"order_id": 5}


# ---------------------------------------------------------------------------
# Feature-флаг отключён
# ---------------------------------------------------------------------------
class TestDisabledFlag:
    @patch("apps.analytics.services.is_enabled", return_value=False)
    def test_returns_none_when_disabled(self, _mock):
        result = track(EventType.SEARCH, payload={"query": "test"})
        assert result is None

    @patch("apps.analytics.services.is_enabled", return_value=False)
    def test_no_db_write_when_disabled(self, _mock):
        track(EventType.SEARCH, payload={"query": "test"})
        assert AnalyticsEvent.objects.count() == 0


# ---------------------------------------------------------------------------
# Receiver: order_created
# ---------------------------------------------------------------------------
class TestReceiverOrderCreated:
    @pytest.fixture(autouse=True)
    def _connect_receivers(self):
        """Подключаем обработчики сигналов вручную (в тестах флаг analytics выключен)."""
        import apps.analytics.receivers  # noqa: F401

    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_order_created_signal_creates_event(self, _mock):
        from apps.core.events import order_created

        order_created.send(sender=self.__class__, order_id=42)
        event = AnalyticsEvent.objects.filter(event_type=EventType.ORDER_CREATED).first()
        assert event is not None
        assert event.payload["order_id"] == 42

    @patch("apps.analytics.services.is_enabled", return_value=True)
    def test_order_paid_signal_creates_event(self, _mock):
        from apps.core.events import order_paid

        order_paid.send(sender=self.__class__, order_id=10, payment_id=99)
        event = AnalyticsEvent.objects.filter(event_type=EventType.PAYMENT_SUCCESS).first()
        assert event is not None
        assert event.payload["order_id"] == 10
        assert event.payload["payment_id"] == 99
