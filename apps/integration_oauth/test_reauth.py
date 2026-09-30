"""DRF-2497: подтверждение личности через VK ID / Яндекс ID и гейт на привязку.

Подтверждение (intent ``reauth``) никого не впускает и не создаёт: засчитывается
только аккаунт провайдера, уже привязанный к пользователю этой сессии.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import SESSION_KEY, get_user_model
from rest_framework.test import APIClient

from apps.accounts import reauth

from .conftest import HOST, callback, location, query, vk_ok, ya_ok
from .models import OAuthAccount
from .views import with_query

User = get_user_model()
pytestmark = pytest.mark.django_db
MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"


@pytest.fixture
def owner(db):
    user = User.objects.create_user(email="oauth@vk.ru", password=None)
    OAuthAccount.objects.create(user=user, provider="vkid", provider_user_id="1001")
    OAuthAccount.objects.create(user=user, provider="yandex", provider_user_id="777")
    return user


@pytest.fixture
def cabinet(owner):
    """Сессия владельца, открытая давно: свежего подтверждения нет."""
    c = APIClient(HTTP_HOST=HOST)
    c.force_login(owner, backend=MODEL_BACKEND)
    session = c.session
    session.pop(reauth.SESSION_KEY, None)
    session.save()
    return c


def _reauth_state(client, provider="vkid", next_url="/account/profile?resume=delete") -> str:
    resp = client.post(f"/api/account/oauth/{provider}/reauth/", {"next": next_url}, format="json")
    assert resp.status_code == 200, resp.content
    return query(resp.json()["url"])["state"]


def _verified(client) -> bool:
    return client.get("/api/account/me/").json()["reauth_valid_until"] is not None


# ═══════════ Подтверждение ═══════════


def test_тот_же_аккаунт_провайдера_подтверждает(cabinet, owner, net):
    vk_ok(net, user_id="1001")
    state = _reauth_state(cabinet)
    users = User.objects.count()
    resp = callback(cabinet, "vkid", state)
    assert location(resp) == "/account/profile?resume=delete&reauth=ok"
    assert int(cabinet.session[SESSION_KEY]) == owner.pk
    assert User.objects.count() == users
    assert _verified(cabinet)
    assert cabinet.post("/api/account/delete/").status_code == 200


def test_повторный_колбэк_подтверждения_тот_же_адрес(cabinet, net):
    vk_ok(net, user_id="1001")
    state = _reauth_state(cabinet)
    first = location(callback(cabinet, "vkid", state))
    calls = len(net.calls)
    assert location(callback(cabinet, "vkid", state)) == first
    assert len(net.calls) == calls


def test_другой_аккаунт_провайдера_отказ_без_входа_и_создания(cabinet, owner, net):
    vk_ok(net, user_id="5555", email="other@vk.ru")
    state = _reauth_state(cabinet)
    users = User.objects.count()
    resp = callback(cabinet, "vkid", state)
    assert location(resp) == "/account/profile?oauth_error=reauth_mismatch"
    assert User.objects.count() == users
    assert not OAuthAccount.objects.filter(provider_user_id="5555").exists()
    assert int(cabinet.session[SESSION_KEY]) == owner.pk
    assert not _verified(cabinet)


def test_аккаунт_провайдера_другого_пользователя_отказ(cabinet, owner, net):
    stranger = User.objects.create_user(email="s@vk.ru", password=None)
    OAuthAccount.objects.create(user=stranger, provider="vkid", provider_user_id="4242")
    vk_ok(net, user_id="4242")
    state = _reauth_state(cabinet)
    resp = callback(cabinet, "vkid", state)
    assert "reauth_mismatch" in location(resp)
    assert int(cabinet.session[SESSION_KEY]) == owner.pk
    assert not _verified(cabinet)


def test_колбэк_после_выхода_отказ_до_обмена(cabinet, net):
    state = _reauth_state(cabinet)
    cabinet.post("/api/account/logout/")  # сессия очищена вместе с ожиданием
    calls = len(net.calls)
    assert "oauth_error=expired" in location(callback(cabinet, "vkid", state))
    assert len(net.calls) == calls


def test_колбэк_подтверждения_чужого_пользователя_отказ_до_обмена(cabinet, owner, net):
    from . import pending

    stranger = User.objects.create_user(email="z@vk.ru", password=None)
    session = cabinet.session
    state, _ = pending.create(
        session, provider="vkid", intent="reauth", next_url="/account/profile", user_id=stranger.pk
    )
    session.save()
    calls = len(net.calls)
    assert "reauth_expired" in location(callback(cabinet, "vkid", state))
    assert len(net.calls) == calls
    assert not _verified(cabinet)


def test_яндекс_спрашивает_выбор_аккаунта(cabinet, net):
    ya_ok(net, user_id="777")
    resp = cabinet.post("/api/account/oauth/yandex/reauth/", {}, format="json")
    assert query(resp.json()["url"]).get("force_confirm") == "yes"
    resp = callback(cabinet, "yandex", query(resp.json()["url"])["state"])
    assert location(resp) == "/account/profile?reauth=ok"


def test_подтверждение_непривязанным_провайдером_нельзя(db):
    user = User.objects.create_user(email="x@vk.ru", password=None)
    OAuthAccount.objects.create(user=user, provider="vkid", provider_user_id="1")
    c = APIClient(HTTP_HOST=HOST)
    c.force_login(user, backend=MODEL_BACKEND)
    assert c.post("/api/account/oauth/yandex/reauth/", {}, format="json").status_code == 400


def test_подтверждение_у_пользователя_с_паролем_нельзя(db):
    user = User.objects.create_user(email="p@vk.ru", password="Strong2026x")
    OAuthAccount.objects.create(user=user, provider="vkid", provider_user_id="1")
    c = APIClient(HTTP_HOST=HOST)
    c.force_login(user)
    assert c.post("/api/account/oauth/vkid/reauth/", {}, format="json").status_code == 400


def test_next_наружу_не_уводит(cabinet, net):
    vk_ok(net, user_id="1001")
    state = _reauth_state(cabinet, next_url="https://evil.example/x")
    assert location(callback(cabinet, "vkid", state)) == "/account/profile?reauth=ok"


def test_with_query_сохраняет_свои_параметры():
    assert with_query("/account/profile?resume=delete", reauth="ok") == (
        "/account/profile?resume=delete&reauth=ok"
    )
    assert with_query("/account/profile?reauth=old", reauth="ok") == "/account/profile?reauth=ok"


# ═══════════ Гейт на привязку (обход через свой провайдер) ═══════════


def test_привязка_без_подтверждения_запрещена(db):
    user = User.objects.create_user(email="m@vk.ru", password=None)
    OAuthAccount.objects.create(user=user, provider="vkid", provider_user_id="1")
    c = APIClient(HTTP_HOST=HOST)
    c.force_login(user, backend=MODEL_BACKEND)
    session = c.session
    session.pop(reauth.SESSION_KEY, None)
    session.save()

    resp = c.post("/api/account/oauth/yandex/link/")
    assert resp.status_code == 403 and resp.json()["code"] == "reauth_required"


def test_привязка_после_свежего_входа_разрешена(db):
    user = User.objects.create_user(email="m2@vk.ru", password=None)
    OAuthAccount.objects.create(user=user, provider="vkid", provider_user_id="1")
    c = APIClient(HTTP_HOST=HOST)
    c.force_login(user, backend=MODEL_BACKEND)
    assert c.post("/api/account/oauth/yandex/link/").status_code == 200
