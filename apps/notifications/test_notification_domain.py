"""Тесты notification domain: preferences, intent/history, policy (#515)."""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import override_settings

from apps.core.models import SiteSettings

from .models import (
    Notification,
    NotificationCategory,
    NotificationStatus,
    UserNotificationPreference,
)
from .services import create_notification, get_or_create_preference

User = get_user_model()

MAX_SETTINGS = {"MAX_BOT_TOKEN": "test-token", "MAX_BOT_API_URL": "https://test.max.ru"}


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+79001234567", password="pass")


@pytest.fixture
def _enable_max(db):
    s = SiteSettings.get_solo()
    s.max_chat_enabled = True
    s.save()


def _link_max(user, chat_id=555):
    from django.utils import timezone

    from apps.integration_max.models import MaxAccount

    return MaxAccount.objects.create(
        user=user,
        max_user_id=42,
        chat_id=chat_id,
        phone=user.phone,
        phone_verified_at=timezone.now(),
    )


# ═══════════════════════════════════════════════════════════════════════
# 1. PREFERENCES — defaults
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_preference_defaults(user):
    pref = get_or_create_preference(user)
    assert pref.max_enabled is True
    assert pref.order_updates_enabled is True
    assert pref.product_availability_enabled is True
    assert pref.marketing_enabled is False
    assert pref.marketing_consent_at is None


@pytest.mark.django_db
def test_get_or_create_preference_idempotent(user):
    p1 = get_or_create_preference(user)
    p2 = get_or_create_preference(user)
    assert p1.pk == p2.pk
    assert UserNotificationPreference.objects.filter(user=user).count() == 1


# ═══════════════════════════════════════════════════════════════════════
# 2. CREATE_NOTIFICATION — intent + policy
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_create_notification_no_user_returns_none():
    assert create_notification(user=None, event="order_created") is None


@override_settings(**MAX_SETTINGS)
@pytest.mark.django_db
@pytest.mark.usefixtures("_enable_max")
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_create_notification_enabled_category_sends(mock_max, user):
    """Категория включена (default) → intent создан, есть delivery, статус SENT."""
    _link_max(user, chat_id=777)
    intent = create_notification(
        user=user, event="order_paid", payload={"order_id": 1}, idempotency_key="np-1"
    )
    assert intent is not None
    assert intent.category == NotificationCategory.ORDER_UPDATES
    assert intent.title == "Заказ оплачен"
    assert intent.policy_skip_reason == ""
    assert intent.delivery is not None
    # Celery в тестах eager — задача уже отработала и обновила status в БД поверх
    # in-memory объекта, который send() успел вернуть раньше; перечитываем.
    intent.delivery.refresh_from_db()
    assert intent.delivery.status == NotificationStatus.SENT
    mock_max.assert_called_once_with(777, mock.ANY)


@pytest.mark.django_db
def test_create_notification_category_disabled_skips_without_send(user):
    """Выключенная категория → explain-skip, delivery не создаётся, send() не трогается."""
    pref = get_or_create_preference(user)
    pref.order_updates_enabled = False
    pref.save()
    _link_max(user)

    with mock.patch("apps.notifications.services.send") as mock_send:
        intent = create_notification(user=user, event="order_paid", payload={"order_id": 2})

    mock_send.assert_not_called()
    assert intent.policy_skip_reason == "category_disabled:order_updates"
    assert intent.delivery is None


@pytest.mark.django_db
def test_create_notification_max_disabled_master_switch_skips(user):
    """max_enabled=False гасит вообще всё, независимо от категории."""
    pref = get_or_create_preference(user)
    pref.max_enabled = False
    pref.save()
    _link_max(user)

    with mock.patch("apps.notifications.services.send") as mock_send:
        intent = create_notification(user=user, event="order_paid")

    mock_send.assert_not_called()
    assert intent.policy_skip_reason == "max_disabled"


@pytest.mark.django_db
def test_create_notification_account_category_not_gated_by_order_toggle(user):
    """ACCOUNT-категория (напр. max_connected) не имеет своего тумблера — её
    гасит только max_enabled, а не order_updates_enabled/product_availability_enabled."""
    pref = get_or_create_preference(user)
    pref.order_updates_enabled = False
    pref.product_availability_enabled = False
    pref.save()
    _link_max(user)

    with mock.patch("apps.notifications.services.send") as mock_send:
        mock_send.return_value = None
        intent = create_notification(user=user, event="max_connected")

    assert intent.category == NotificationCategory.ACCOUNT
    assert intent.policy_skip_reason == ""
    mock_send.assert_called_once()


@pytest.mark.django_db
def test_create_notification_idempotent(user):
    """Повтор idempotency_key не создаёт второй intent (AC #515)."""
    _link_max(user)
    with mock.patch("apps.notifications.services.send", return_value=None):
        first = create_notification(user=user, event="order_created", idempotency_key="oc-1")
        second = create_notification(user=user, event="order_created", idempotency_key="oc-1")

    assert first.pk == second.pk
    assert Notification.objects.filter(idempotency_key="oc-1").count() == 1


@pytest.mark.django_db
def test_notification_idempotency_key_db_constraint():
    """Модельный уровень: непустой ключ уникален на всей таблице."""
    u = User.objects.create_user(phone="+79000000001", password="pass")
    Notification.objects.create(
        user=u, event="e", category=NotificationCategory.ACCOUNT, title="t", idempotency_key="k1"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Notification.objects.create(
            user=u,
            event="e",
            category=NotificationCategory.ACCOUNT,
            title="t",
            idempotency_key="k1",
        )
    # Пустые ключи не конфликтуют.
    Notification.objects.create(user=u, event="e", category=NotificationCategory.ACCOUNT, title="t")
    Notification.objects.create(user=u, event="e", category=NotificationCategory.ACCOUNT, title="t")


@pytest.mark.django_db
def test_create_notification_transaction_rollback_creates_nothing(user):
    """Откат внешней транзакции не должен оставлять Notification в БД."""
    with mock.patch("apps.notifications.services.send", return_value=None):
        try:
            with transaction.atomic():
                create_notification(user=user, event="order_created", idempotency_key="rb-1")
                raise RuntimeError("boom")
        except RuntimeError:
            pass

    assert not Notification.objects.filter(idempotency_key="rb-1").exists()


# ═══════════════════════════════════════════════════════════════════════
# 3. max_connected — welcome hook (integration_max._upsert_account)
# ═══════════════════════════════════════════════════════════════════════


@override_settings(**MAX_SETTINGS)
@pytest.mark.django_db
@pytest.mark.usefixtures("_enable_max")
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_max_connected_fires_on_new_link_only(mock_max, user, django_capture_on_commit_callbacks):
    from apps.integration_max.services import _upsert_account

    with django_capture_on_commit_callbacks(execute=True):
        _upsert_account(user, max_user_id=100, phone=user.phone, chat_id=999, profile={})
    assert Notification.objects.filter(user=user, event="max_connected").count() == 1

    # Повторный upsert той же привязки (напр. re-login/чат обновился) — не должен
    # заново слать приветствие.
    with django_capture_on_commit_callbacks(execute=True):
        _upsert_account(user, max_user_id=100, phone=user.phone, chat_id=999, profile={})
    assert Notification.objects.filter(user=user, event="max_connected").count() == 1


@pytest.mark.django_db
def test_max_connected_not_fired_before_commit(user):
    """on_commit: в тест-транзакции без django_capture_on_commit_callbacks коллбэк
    не срабатывает (тот же приём, что apps/catalog/test_attrs_cache.py) — значит и
    до реального commit в проде уведомление не создаётся раньше времени."""
    from apps.integration_max.services import _upsert_account

    _upsert_account(user, max_user_id=101, phone=user.phone, chat_id=1000, profile={})
    assert not Notification.objects.filter(user=user, event="max_connected").exists()
