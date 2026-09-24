"""Колбэк входа: state, ошибки провайдера, регистрация, повторный вход, коллизии."""

from __future__ import annotations

import base64
import json
import time
from unittest import mock

import pytest
from django.contrib.auth import SESSION_KEY, get_user_model
from django.core import mail
from django.db import IntegrityError

from . import pending, services
from .conftest import (
    SITE,
    VK_INFO,
    VK_TOKEN,
    YA_INFO,
    YA_TOKEN,
    callback,
    location,
    query,
    start,
    vk_ok,
    ya_ok,
)
from .models import OAuthAccount
from .providers import ProviderProfile

User = get_user_model()
pytestmark = pytest.mark.django_db


def _logged_in_as(browser):
    raw = browser.session.get(SESSION_KEY)
    return int(raw) if raw is not None else None


# ═══════════ state ═══════════


def test_unknown_state_is_expired_without_network(browser, net):
    start(browser)
    resp = callback(browser, "vkid", "x" * 43)
    assert location(resp) == "/account/login?oauth_error=expired"
    assert net.calls == []


def test_expired_state(browser, net, oauth_settings):
    vk_ok(net)
    state = start(browser)
    later = time.time() + oauth_settings.OAUTH_STATE_TTL_SECONDS + 5
    with mock.patch("apps.integration_oauth.pending.time.time", return_value=later):
        resp = callback(browser, "vkid", state)
    assert location(resp) == "/account/login?oauth_error=expired"
    assert net.calls == []


def test_state_is_single_use(browser, net):
    state = start(browser)
    assert location(callback(browser, "vkid", state, error="access_denied")).endswith(
        "oauth_error=cancelled"
    )
    # Та же запись второй раз не находится — и до обмена кода не доходит.
    vk_ok(net)
    assert location(callback(browser, "vkid", state)) == "/account/login?oauth_error=expired"
    assert net.calls == []


def test_state_of_other_provider_not_accepted(browser, net):
    state = start(browser, "yandex")
    vk_ok(net)
    assert location(callback(browser, "vkid", state)) == "/account/login?oauth_error=expired"
    assert net.calls == []


def test_state_from_other_browser_not_accepted(browser, net):
    from rest_framework.test import APIClient

    state = start(browser)
    vk_ok(net)
    other = APIClient(HTTP_HOST="proff58.ru")
    assert location(callback(other, "vkid", state)) == "/account/login?oauth_error=expired"
    assert net.calls == []


def test_access_denied_is_cancelled(browser, net):
    state = start(browser, next="/catalog")
    resp = callback(browser, "vkid", state, code=None, error="access_denied")
    assert location(resp) == "/account/login?oauth_error=cancelled&next=%2Fcatalog"
    assert net.calls == []


def test_exchange_state_mismatch_fails(browser, net):
    net.add(VK_TOKEN, {"access_token": "at", "state": "другой", "user_id": 1})
    net.add(VK_INFO, {"user": {"user_id": "1", "email": "a@b.ru"}})
    state = start(browser)
    assert location(callback(browser, "vkid", state)) == "/account/login?oauth_error=failed"
    assert len(net.calls) == 1  # профиль с подменённым токеном не запрашиваем
    assert not User.objects.exists()


@pytest.mark.parametrize(
    "token_response",
    [
        {"error": "invalid_grant", "error_description": "bad"},
        b"<html>not json</html>",
    ],
)
def test_provider_errors_fail(browser, net, token_response):
    net.add(VK_TOKEN, token_response)
    state = start(browser)
    assert location(callback(browser, "vkid", state)) == "/account/login?oauth_error=failed"


def test_http_error_fails_without_logging_secrets(browser, net, caplog):
    net.add(VK_TOKEN, {"error": "invalid_client", "access_token": "LEAK-TOKEN"}, status=401)
    state = start(browser)
    with caplog.at_level("DEBUG"):
        assert location(callback(browser, "vkid", state)).endswith("oauth_error=failed")
    text = caplog.text
    assert "LEAK-TOKEN" not in text and "the-code" not in text and state not in text
    assert "invalid_client" in text


def test_network_error_fails(browser, net):
    state = start(browser)  # маршрутов нет → URLError
    assert location(callback(browser, "vkid", state)).endswith("oauth_error=failed")


def test_vk_without_device_id_fails_without_network(browser, net):
    state = start(browser)
    resp = callback(browser, "vkid", state, device_id=None)
    assert location(resp).endswith("oauth_error=failed")
    assert net.calls == []


# ═══════════ Регистрация и вход ═══════════


def test_new_user_via_vk(browser, net, django_capture_on_commit_callbacks):
    vk_ok(net, email="Ivan@VK.ru")
    state = start(browser, next="/catalog/drel", via="mail_ru")
    with mock.patch("apps.analytics.services.track") as track:
        with django_capture_on_commit_callbacks(execute=True):
            resp = callback(browser, "vkid", state)
    assert location(resp) == "/catalog/drel"

    user = User.objects.get()
    assert user.email == "Ivan@vk.ru"  # домен нормализует менеджер
    assert user.full_name == "Иван П"
    assert user.phone is None
    assert not user.has_usable_password()
    assert _logged_in_as(browser) == user.pk
    acct = OAuthAccount.objects.get()
    assert (acct.user_id, acct.provider, acct.provider_user_id) == (user.pk, "vkid", "1001")
    assert acct.last_login_at is not None

    # Запросы к VK: PKCE verifier тот же, redirect_uri байт-в-байт, сервисный ключ.
    token_form = net.form(0)
    assert net.calls[0].full_url == VK_TOKEN
    assert token_form["grant_type"] == "authorization_code"
    assert token_form["code"] == "the-code"
    assert token_form["device_id"] == "dev-1"
    assert token_form["state"] == state
    assert token_form["client_id"] == "vk-client"
    assert token_form["service_token"] == "vk-service"
    assert token_form["redirect_uri"] == f"{SITE}/api/oauth/vkid/callback/"
    assert len(token_form["code_verifier"]) >= 43
    assert net.form(1) == {"client_id": "vk-client", "access_token": "vk-at"}

    # Письмо о созданном аккаунте со ссылкой на восстановление.
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["Ivan@vk.ru"]
    assert "VK ID" in msg.body
    assert f"{SITE}/account/forgot-password" in msg.body

    events = {c.args[0]: c.kwargs["payload"] for c in track.call_args_list}
    assert events["oauth_login_completed"] == {
        "provider": "vkid",
        "via": "mail_ru",
        "is_new_user": True,
    }
    # В аналитике нет ПДн: ни почты, ни id у провайдера.
    dumped = json.dumps([c.kwargs["payload"] for c in track.call_args_list])
    assert "vk.ru" not in dumped.lower() and "1001" not in dumped

    # Пендинг снят, сессия несёт только маркер завершённого входа.
    assert state not in browser.session.get(pending.SESSION_KEY, {})


def test_new_user_via_yandex(browser, net, django_capture_on_commit_callbacks):
    ya_ok(net)
    state = start(browser, "yandex")
    with django_capture_on_commit_callbacks(execute=True):
        resp = callback(browser, "yandex", state)
    assert location(resp) == "/account/profile"
    user = User.objects.get(email="petr@yandex.ru")
    assert user.full_name == "Пётр Иванов"
    assert OAuthAccount.objects.get().provider_user_id == "777"
    token_req, info_req = net.calls
    assert token_req.full_url == YA_TOKEN
    expected = base64.b64encode(b"ya-client:ya-secret").decode()
    assert token_req.get_header("Authorization") == f"Basic {expected}"
    assert net.form(0)["code_verifier"]
    assert "redirect_uri" not in net.form(0)
    assert info_req.full_url.startswith(YA_INFO)
    assert info_req.get_header("Authorization") == "OAuth ya-at"
    assert "Яндекс ID" in mail.outbox[0].body


def test_mail_failure_does_not_break_login(browser, net, django_capture_on_commit_callbacks):
    from apps.notifications.channels import RetryableChannelError

    vk_ok(net)
    state = start(browser)
    with mock.patch(
        "apps.notifications.channels.email.send_email", side_effect=RetryableChannelError("x")
    ):
        with django_capture_on_commit_callbacks(execute=True):
            resp = callback(browser, "vkid", state)
    assert location(resp) == "/account/profile"
    assert _logged_in_as(browser) == User.objects.get().pk


def test_repeat_login_by_link(browser, net, django_capture_on_commit_callbacks):
    user = User.objects.create_user(email="old@site.ru", password="Strong2026x")
    OAuthAccount.objects.create(user=user, provider="vkid", provider_user_id="1001")
    vk_ok(net, email="other@vk.ru")
    state = start(browser)
    with django_capture_on_commit_callbacks(execute=True):
        resp = callback(browser, "vkid", state)
    assert location(resp) == "/account/profile"
    assert _logged_in_as(browser) == user.pk
    assert User.objects.count() == 1
    assert mail.outbox == []  # повторный вход — без писем
    acct = OAuthAccount.objects.get()
    assert acct.last_login_at is not None and acct.email == "other@vk.ru"


def test_deleted_user_link_dropped_and_new_account(browser, net):
    old = User.objects.create_user(email="ivan@vk.ru", password=None)
    OAuthAccount.objects.create(user=old, provider="vkid", provider_user_id="1001")
    # Обезличен так же, как делает DeleteAccountView.
    User.objects.filter(pk=old.pk).update(phone=f"deleted-{old.pk}", email="", is_active=False)
    vk_ok(net)
    state = start(browser)
    assert location(callback(browser, "vkid", state)) == "/account/profile"
    new = User.objects.get(email="ivan@vk.ru")
    assert new.pk != old.pk
    assert list(OAuthAccount.objects.values_list("user_id", flat=True)) == [new.pk]
    assert _logged_in_as(browser) == new.pk


def test_blocked_user_is_inactive(browser, net):
    blocked = User.objects.create_user(email="ivan@vk.ru", password=None, is_active=False)
    OAuthAccount.objects.create(user=blocked, provider="vkid", provider_user_id="1001")
    vk_ok(net, email="new-address@vk.ru")
    state = start(browser)
    assert location(callback(browser, "vkid", state)) == "/account/login?oauth_error=inactive"
    assert User.objects.count() == 1 and OAuthAccount.objects.count() == 1
    assert _logged_in_as(browser) is None


def test_email_collision_other_case_not_merged(browser, net):
    existing = User.objects.create_user(email="ivan@vk.ru", password="Strong2026x")
    vk_ok(net, email="IVAN@vk.ru")
    state = start(browser, next="/catalog")
    resp = callback(browser, "vkid", state)
    assert query(location(resp)) == {
        "oauth_error": "email_exists",
        "provider": "vkid",
        "next": "/catalog",
    }
    assert location(resp).startswith("/account/login?")
    assert User.objects.count() == 1
    assert not OAuthAccount.objects.filter(user=existing).exists()
    assert _logged_in_as(browser) is None


def test_no_email(browser, net):
    ya_ok(net, email=None)
    state = start(browser, "yandex")
    resp = callback(browser, "yandex", state)
    assert location(resp) == "/account/login?oauth_error=no_email&provider=yandex"
    assert not User.objects.exists()


def test_invalid_email_treated_as_missing(browser, net):
    vk_ok(net, email="не почта")
    state = start(browser)
    assert location(callback(browser, "vkid", state)).startswith(
        "/account/login?oauth_error=no_email"
    )


def test_double_callback_of_logged_in_user(browser, net):
    vk_ok(net)
    state = start(browser, next="/catalog")
    assert location(callback(browser, "vkid", state)) == "/catalog"
    calls = len(net.calls)
    assert location(callback(browser, "vkid", state)) == "/catalog"
    assert len(net.calls) == calls  # второй раз код не обменивали
    assert User.objects.count() == 1


# ═══════════ Гонка: IntegrityError → один повтор ═══════════

PROFILE = ProviderProfile(
    provider="vkid", provider_user_id="1001", email="ivan@vk.ru", full_name="Иван"
)


def _flaky_once():
    """Первый разбор падает на уникальности (сосед успел раньше), второй — настоящий."""
    original = services._resolve_login_once
    calls = []

    def flaky(profile):
        calls.append(1)
        if len(calls) == 1:
            raise IntegrityError("dup")
        return original(profile)

    return flaky, calls


def test_race_retry_finds_neighbours_link():
    neighbour = User.objects.create_user(email="ivan@vk.ru", password=None)
    OAuthAccount.objects.create(user=neighbour, provider="vkid", provider_user_id="1001")
    flaky, calls = _flaky_once()
    with mock.patch.object(services, "_resolve_login_once", flaky):
        result = services.resolve_login(PROFILE)
    assert result.error == "" and result.user.pk == neighbour.pk and len(calls) == 2


def test_race_retry_email_exists():
    User.objects.create_user(email="ivan@vk.ru", password=None)
    flaky, calls = _flaky_once()
    with mock.patch.object(services, "_resolve_login_once", flaky):
        result = services.resolve_login(PROFILE)
    assert result.error == "email_exists" and len(calls) == 2


def test_race_twice_is_failed():
    with mock.patch.object(services, "_resolve_login_once", side_effect=IntegrityError("dup")):
        assert services.resolve_login(PROFILE).error == "failed"


def test_real_unique_violation_rolls_back_user(browser, net):
    """Настоящий IntegrityError на вставке привязки не оставляет сироту-пользователя."""
    vk_ok(net)
    state = start(browser)
    real_create = OAuthAccount.objects.create
    calls = []

    def create(**kw):
        calls.append(1)
        if len(calls) == 1:
            raise IntegrityError("dup")
        return real_create(**kw)

    with mock.patch.object(OAuthAccount.objects, "create", side_effect=create):
        resp = callback(browser, "vkid", state)
    assert location(resp) == "/account/profile"
    assert User.objects.count() == 1 and OAuthAccount.objects.count() == 1


# ═══════════ VK ID: payload-вариант колбэка ═══════════


def test_vk_payload_variant(browser, net):
    vk_ok(net)
    state = start(browser)
    payload = json.dumps(
        {"code": "the-code", "state": state, "type": "code_v2", "device_id": "dev-9"}
    )
    resp = browser.get("/api/oauth/vkid/callback/", {"payload": payload})
    assert location(resp) == "/account/profile"
    assert net.form(0)["device_id"] == "dev-9"
    assert User.objects.count() == 1


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        json.dumps(["list"]),
        json.dumps({"code": 1, "state": "x"}),
        "x" * 5000,
    ],
)
def test_vk_bad_payload(browser, net, payload):
    start(browser)
    resp = browser.get("/api/oauth/vkid/callback/", {"payload": payload})
    assert location(resp) == "/account/login?oauth_error=failed"
    assert net.calls == []


def test_callback_of_unknown_provider(browser):
    assert location(browser.get("/api/oauth/google/callback/")).endswith("oauth_error=unavailable")


def test_callback_when_provider_switched_off(browser, net, oauth_settings):
    vk_ok(net)
    state = start(browser)
    oauth_settings.VKID_CLIENT_ID = ""
    assert location(callback(browser, "vkid", state)).endswith("oauth_error=unavailable")
    assert net.calls == []
