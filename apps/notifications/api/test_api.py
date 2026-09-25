"""Тесты API preferences и истории уведомлений (#515)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from ..models import Notification, NotificationCategory, UserNotificationPreference
from ..services import get_or_create_preference

User = get_user_model()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+79001234567", password="pass")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(phone="+79009999999", password="pass")


# ═══════════════════════════════════════════════════════════════════════
# PREFERENCES
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_preferences_requires_auth(client):
    resp = client.get("/api/account/notifications/preferences/")
    assert resp.status_code == 401 or resp.status_code == 403


@pytest.mark.django_db
def test_preferences_get_creates_defaults(client, user):
    client.force_authenticate(user=user)
    resp = client.get("/api/account/notifications/preferences/")
    assert resp.status_code == 200
    assert resp.data["max_enabled"] is True
    assert resp.data["marketing_enabled"] is False
    assert UserNotificationPreference.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_preferences_patch_boolean_field(client, user):
    client.force_authenticate(user=user)
    resp = client.patch("/api/account/notifications/preferences/", {"order_updates_enabled": False})
    assert resp.status_code == 200
    assert resp.data["order_updates_enabled"] is False
    pref = get_or_create_preference(user)
    assert pref.order_updates_enabled is False


@pytest.mark.django_db
def test_preferences_patch_marketing_without_consent_rejected(client, user):
    client.force_authenticate(user=user)
    resp = client.patch("/api/account/notifications/preferences/", {"marketing_enabled": True})
    assert resp.status_code == 400
    assert "consent_version" in resp.data


@pytest.mark.django_db
def test_preferences_patch_marketing_with_consent_records_audit(client, user):
    client.force_authenticate(user=user)
    resp = client.patch(
        "/api/account/notifications/preferences/",
        {"marketing_enabled": True, "consent_version": "v2"},
    )
    assert resp.status_code == 200
    pref = get_or_create_preference(user)
    assert pref.marketing_enabled is True
    assert pref.marketing_consent_at is not None
    assert pref.marketing_consent_version == "v2"


@pytest.mark.django_db
def test_preferences_disabling_marketing_keeps_consent_history(client, user):
    pref = get_or_create_preference(user)
    pref.marketing_enabled = True
    pref.marketing_consent_at = timezone.now()
    pref.marketing_consent_version = "v1"
    pref.save()

    client.force_authenticate(user=user)
    resp = client.patch("/api/account/notifications/preferences/", {"marketing_enabled": False})
    assert resp.status_code == 200
    pref.refresh_from_db()
    assert pref.marketing_enabled is False
    assert pref.marketing_consent_version == "v1"  # исторический след не стирается


@pytest.mark.django_db
def test_preferences_are_per_user_not_shared(client, user, other_user):
    """Нет id пользователя в пути — PATCH одного не задевает настройки другого."""
    p_user = get_or_create_preference(user)
    p_other = get_or_create_preference(other_user)
    assert p_user.pk != p_other.pk

    client.force_authenticate(user=user)
    client.patch("/api/account/notifications/preferences/", {"order_updates_enabled": False})

    p_other.refresh_from_db()
    assert p_other.order_updates_enabled is True


# ═══════════════════════════════════════════════════════════════════════
# HISTORY
# ═══════════════════════════════════════════════════════════════════════


def _make_notification(user, **kwargs):
    defaults = dict(
        user=user, event="order_created", category=NotificationCategory.ORDER_UPDATES, title="t"
    )
    defaults.update(kwargs)
    return Notification.objects.create(**defaults)


@pytest.mark.django_db
def test_history_list_only_own_notifications(client, user, other_user):
    _make_notification(user)
    _make_notification(other_user)

    client.force_authenticate(user=user)
    resp = client.get("/api/account/notifications/")
    assert resp.status_code == 200
    assert resp.data["count"] == 1


@pytest.mark.django_db
def test_history_list_paginated(client, user):
    for i in range(3):
        _make_notification(user, idempotency_key=f"k{i}")

    client.force_authenticate(user=user)
    resp = client.get("/api/account/notifications/?limit=2")
    assert resp.status_code == 200
    assert resp.data["count"] == 3
    assert len(resp.data["results"]) == 2
    assert resp.data["next"] is not None


@pytest.mark.django_db
def test_unread_count(client, user):
    _make_notification(user, idempotency_key="a")
    _make_notification(user, idempotency_key="b", read_at=timezone.now())

    client.force_authenticate(user=user)
    resp = client.get("/api/account/notifications/unread-count/")
    assert resp.status_code == 200
    assert resp.data["unread_count"] == 1


@pytest.mark.django_db
def test_mark_read_own_notification(client, user):
    n = _make_notification(user)
    client.force_authenticate(user=user)
    resp = client.post(f"/api/account/notifications/{n.pk}/read/")
    assert resp.status_code == 200
    n.refresh_from_db()
    assert n.read_at is not None


@pytest.mark.django_db
def test_mark_read_foreign_notification_404(client, user, other_user):
    """Владение — на уровне запроса (get_object_or_404 фильтрует по user), чужой
    id не даёт ни прочитать, ни пометить прочитанным."""
    n = _make_notification(other_user)
    client.force_authenticate(user=user)
    resp = client.post(f"/api/account/notifications/{n.pk}/read/")
    assert resp.status_code == 404
    n.refresh_from_db()
    assert n.read_at is None


@pytest.mark.django_db
def test_mark_all_read(client, user):
    _make_notification(user, idempotency_key="a")
    _make_notification(user, idempotency_key="b")
    _make_notification(user, idempotency_key="c", read_at=timezone.now())

    client.force_authenticate(user=user)
    resp = client.post("/api/account/notifications/read-all/")
    assert resp.status_code == 200
    assert resp.data["marked"] == 2
    assert Notification.objects.filter(user=user, read_at__isnull=True).count() == 0


@pytest.mark.django_db
def test_mark_all_read_does_not_touch_other_users(client, user, other_user):
    _make_notification(other_user, idempotency_key="foreign")
    client.force_authenticate(user=user)
    client.post("/api/account/notifications/read-all/")
    assert Notification.objects.get(idempotency_key="foreign").read_at is None
