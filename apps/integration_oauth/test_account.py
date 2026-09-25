"""Кабинет: привязка, список, отвязка; удаление аккаунта; сброс пароля; system checks."""

from __future__ import annotations

import pytest
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.core import mail
from rest_framework.test import APIClient

from apps.integration_max.models import MaxAccount

from .apps import _check_oauth_config
from .conftest import HOST, callback, location, query, vk_ok, ya_ok
from .models import OAuthAccount

User = get_user_model()
pytestmark = pytest.mark.django_db

LAST_METHOD = (
    "Это единственный способ входа в аккаунт. Сначала задайте пароль или привяжите другой способ."
)


def _session_user(client):
    raw = client.session.get(SESSION_KEY)
    return int(raw) if raw is not None else None


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        phone="+79001112233", email="owner@site.ru", password="Strong2026x"
    )


@pytest.fixture
def cabinet(owner):
    c = APIClient(HTTP_HOST=HOST)
    c.force_login(owner)
    return c


def _link_state(client, provider="vkid") -> str:
    resp = client.post(f"/api/account/oauth/{provider}/link/")
    assert resp.status_code == 200, resp.content
    return query(resp.json()["url"])["state"]


# ═══════════ Привязка ═══════════


def test_link_success(cabinet, owner, net, django_capture_on_commit_callbacks):
    vk_ok(net, email="someone@vk.ru")
    state = _link_state(cabinet)
    with django_capture_on_commit_callbacks(execute=True):
        resp = callback(cabinet, "vkid", state)
    assert location(resp) == "/account/profile?oauth_linked=vkid"
    acct = OAuthAccount.objects.get()
    assert (acct.user_id, acct.provider_user_id, acct.email) == (owner.pk, "1001", "someone@vk.ru")
    assert _session_user(cabinet) == owner.pk
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["owner@site.ru"]
    assert "привязан VK ID" in mail.outbox[0].body
    # Повторный колбэк той же привязки — тот же результат, без обмена.
    calls = len(net.calls)
    assert location(callback(cabinet, "vkid", state)) == "/account/profile?oauth_linked=vkid"
    assert len(net.calls) == calls


def test_link_same_account_again_is_noop(cabinet, owner, net):
    OAuthAccount.objects.create(user=owner, provider="vkid", provider_user_id="1001")
    # Кабинет не даст начать (409), но колбэк, уже начатый раньше, отработает как noop.
    from . import pending

    session = cabinet.session
    state, _ = pending.create(
        session, provider="vkid", intent="link", next_url="/account/profile", user_id=owner.pk
    )
    session.save()
    vk_ok(net)
    assert location(callback(cabinet, "vkid", state)) == "/account/profile?oauth_linked=vkid"
    assert OAuthAccount.objects.count() == 1


def test_link_foreign_account_already_linked(cabinet, owner, net):
    other = User.objects.create_user(email="other@site.ru", password="Strong2026x")
    OAuthAccount.objects.create(user=other, provider="vkid", provider_user_id="1001")
    vk_ok(net)
    state = _link_state(cabinet)
    resp = callback(cabinet, "vkid", state)
    assert location(resp) == "/account/profile?oauth_error=already_linked"
    assert _session_user(cabinet) == owner.pk  # чужого не впустили
    assert OAuthAccount.objects.get().user_id == other.pk


def test_link_when_user_has_other_account_of_provider(cabinet, owner, net):
    OAuthAccount.objects.create(user=owner, provider="vkid", provider_user_id="555")
    from . import pending

    session = cabinet.session
    state, _ = pending.create(
        session, provider="vkid", intent="link", next_url="/account/profile", user_id=owner.pk
    )
    session.save()
    vk_ok(net, user_id="1001")
    assert location(callback(cabinet, "vkid", state)).endswith("oauth_error=already_linked")
    assert list(OAuthAccount.objects.values_list("provider_user_id", flat=True)) == ["555"]


def test_link_other_user_in_browser_is_link_expired(cabinet, owner, net):
    state = _link_state(cabinet)
    intruder = User.objects.create_user(email="intruder@site.ru", password="Strong2026x")
    # Штатный login() другого пользователя стирает сессию целиком (вместе с state);
    # здесь — худший случай: сессия с ожиданием привязки досталась другому.
    session = cabinet.session
    session[SESSION_KEY] = str(intruder.pk)
    session[HASH_SESSION_KEY] = intruder.get_session_auth_hash()
    session.save()
    vk_ok(net)
    resp = callback(cabinet, "vkid", state)
    assert location(resp) == "/account/profile?oauth_error=link_expired"
    assert net.calls == []
    assert not OAuthAccount.objects.exists()
    assert _session_user(cabinet) == intruder.pk


def test_link_after_logout_is_link_expired(cabinet, net):
    state = _link_state(cabinet)
    session = cabinet.session
    session.pop(SESSION_KEY)  # вышел, но сессия (и state) осталась
    session.save()
    vk_ok(net)
    assert location(callback(cabinet, "vkid", state)) == "/account/profile?oauth_error=link_expired"
    assert net.calls == []
    assert _session_user(cabinet) is None


def test_link_cancelled_returns_to_profile(cabinet):
    state = _link_state(cabinet)
    resp = callback(cabinet, "vkid", state, error="access_denied")
    assert location(resp) == "/account/profile?oauth_error=cancelled"


def test_link_yandex_force_confirm(cabinet, owner, net):
    resp = cabinet.post("/api/account/oauth/yandex/link/")
    url = resp.json()["url"]
    assert url.startswith("https://oauth.yandex.ru/authorize?")
    q = query(url)
    assert q["force_confirm"] == "yes"
    ya_ok(net)
    assert location(callback(cabinet, "yandex", q["state"])) == (
        "/account/profile?oauth_linked=yandex"
    )
    assert OAuthAccount.objects.get().user_id == owner.pk


def test_link_vk_has_no_force_confirm(cabinet):
    q = query(cabinet.post("/api/account/oauth/vkid/link/").json()["url"])
    assert "force_confirm" not in q and q["provider"] == "vkid"


def test_link_errors(cabinet, owner, oauth_settings):
    OAuthAccount.objects.create(user=owner, provider="vkid", provider_user_id="1")
    assert cabinet.post("/api/account/oauth/vkid/link/").status_code == 409
    oauth_settings.YANDEX_ID_CLIENT_ID = ""
    assert cabinet.post("/api/account/oauth/yandex/link/").status_code == 404
    assert cabinet.post("/api/account/oauth/google/link/").status_code == 404


def test_cabinet_requires_auth():
    anon = APIClient(HTTP_HOST=HOST)
    assert anon.get("/api/account/oauth/").status_code == 403
    assert anon.post("/api/account/oauth/vkid/link/").status_code == 403
    assert anon.post("/api/account/oauth/vkid/unlink/").status_code == 403


def test_cabinet_post_requires_csrf(owner):
    c = APIClient(HTTP_HOST=HOST, enforce_csrf_checks=True)
    c.force_login(owner)
    assert c.post("/api/account/oauth/vkid/link/").status_code == 403


# ═══════════ Список и отвязка ═══════════


def test_accounts_list(cabinet, owner, oauth_settings):
    acct = OAuthAccount.objects.create(
        user=owner, provider="vkid", provider_user_id="1", email="a@vk.ru"
    )
    data = cabinet.get("/api/account/oauth/").json()
    assert data == {
        "providers": [
            {
                "id": "vkid",
                "linked": True,
                "email": "a@vk.ru",
                "linked_at": acct.linked_at.isoformat(),
                "can_unlink": True,  # есть пароль
            },
            {"id": "yandex", "linked": False, "email": "", "linked_at": None, "can_unlink": False},
        ]
    }
    oauth_settings.YANDEX_ID_CLIENT_ID = ""
    assert [p["id"] for p in cabinet.get("/api/account/oauth/").json()["providers"]] == ["vkid"]


@pytest.fixture
def oauth_only(db):
    user = User.objects.create_user(email="oauth@vk.ru", password=None)
    OAuthAccount.objects.create(user=user, provider="vkid", provider_user_id="1")
    c = APIClient(HTTP_HOST=HOST)
    c.force_login(user)
    return user, c


def test_unlink_last_method_forbidden(oauth_only):
    user, c = oauth_only
    resp = c.post("/api/account/oauth/vkid/unlink/")
    assert resp.status_code == 400 and resp.json() == {"detail": LAST_METHOD}
    assert OAuthAccount.objects.filter(user=user).exists()
    listed = c.get("/api/account/oauth/").json()["providers"][0]
    assert listed["linked"] is True and listed["can_unlink"] is False


def test_unlink_with_password(cabinet, owner):
    OAuthAccount.objects.create(user=owner, provider="vkid", provider_user_id="1")
    resp = cabinet.post("/api/account/oauth/vkid/unlink/")
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert not OAuthAccount.objects.exists()
    assert cabinet.post("/api/account/oauth/vkid/unlink/").status_code == 404


def test_unlink_with_other_enabled_provider(oauth_only, oauth_settings):
    user, c = oauth_only
    OAuthAccount.objects.create(user=user, provider="yandex", provider_user_id="7")
    oauth_settings.YANDEX_ID_CLIENT_ID = ""  # Яндекс выключен — не считается
    assert c.post("/api/account/oauth/vkid/unlink/").status_code == 400
    oauth_settings.YANDEX_ID_CLIENT_ID = "ya-client"
    assert c.post("/api/account/oauth/vkid/unlink/").status_code == 200
    assert list(OAuthAccount.objects.values_list("provider", flat=True)) == ["yandex"]


def test_unlink_max_counts_only_when_configured(oauth_only, oauth_settings):
    user, c = oauth_only
    MaxAccount.objects.create(user=user, max_user_id=42, phone="+79001234567")
    assert c.post("/api/account/oauth/vkid/unlink/").status_code == 400
    oauth_settings.MAX_BOT_TOKEN = "bot-token"
    oauth_settings.MAX_BOT_USERNAME = "proff_bot"
    assert c.post("/api/account/oauth/vkid/unlink/").status_code == 200


def test_can_login_via_max_rules(oauth_settings):
    from apps.integration_max.services import can_login_via_max

    user = User.objects.create_user(phone="+79005550000", password=None)
    oauth_settings.MAX_BOT_TOKEN = "bot-token"
    oauth_settings.MAX_BOT_USERNAME = "proff_bot"
    assert can_login_via_max(user) is False
    acct = MaxAccount.objects.create(user=user, max_user_id=43, phone="+79005550000")
    assert can_login_via_max(user) is True  # chat_id не нужен
    acct.is_active = False
    acct.save()
    assert can_login_via_max(user) is False
    assert can_login_via_max(None) is False


# ═══════════ Удаление аккаунта ═══════════


def test_delete_account_drops_links(oauth_only, django_capture_on_commit_callbacks):
    user, c = oauth_only
    with django_capture_on_commit_callbacks(execute=True):
        resp = c.post("/api/account/delete/")
    assert resp.status_code == 200
    user.refresh_from_db()
    assert not user.is_active and user.is_anonymized
    assert not OAuthAccount.objects.exists()


def test_user_deleted_event_payload(oauth_only, django_capture_on_commit_callbacks):
    from apps.core.events import user_deleted

    user, c = oauth_only
    seen = []

    def spy(sender, **kwargs):
        seen.append(kwargs)

    user_deleted.connect(spy)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            c.post("/api/account/delete/")
    finally:
        user_deleted.disconnect(spy)
    assert seen == [{"signal": user_deleted, "user_id": user.pk}]


# ═══════════ Восстановление доступа ═══════════


def test_password_reset_for_oauth_user(oauth_only):
    anon = APIClient()
    resp = anon.post("/api/account/password-reset/", {"email": "oauth@vk.ru"}, format="json")
    assert resp.status_code == 200
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["oauth@vk.ru"]


def test_password_reset_not_for_max_only():
    user = User.objects.create_user(phone="+79001110002", email="max@site.ru", password=None)
    MaxAccount.objects.create(user=user, max_user_id=44, phone="+79001110002")
    anon = APIClient()
    resp = anon.post("/api/account/password-reset/", {"email": "max@site.ru"}, format="json")
    assert resp.status_code == 200
    assert mail.outbox == []


def test_reset_confirm_for_oauth_user_then_unlink_allowed(oauth_only):
    """Задал пароль через сброс → пароль стал способом входа → VK можно отвязать."""
    import re

    user, c = oauth_only
    APIClient().post("/api/account/password-reset/", {"email": "oauth@vk.ru"}, format="json")
    m = re.search(r"uid=([\w-]+)&token=([\w-]+)", mail.outbox[0].body)
    resp = APIClient().post(
        "/api/account/password-reset/confirm/",
        {"uid": m.group(1), "token": m.group(2), "new_password": "Brand-New-2026"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    user.refresh_from_db()
    assert user.has_usable_password()
    c.force_login(user)
    assert c.post("/api/account/oauth/vkid/unlink/").status_code == 200


# ═══════════ System checks ═══════════


def test_check_ok_with_keys_and_https(oauth_settings):
    assert _check_oauth_config(None) == []


def test_check_ok_without_keys(oauth_settings):
    oauth_settings.VKID_CLIENT_ID = ""
    oauth_settings.YANDEX_ID_CLIENT_ID = ""
    oauth_settings.YANDEX_ID_CLIENT_SECRET = ""
    oauth_settings.SITE_URL = ""
    assert _check_oauth_config(None) == []


@pytest.mark.parametrize("site", ["", "http://proff58.ru", "https://proff58.ru/shop"])
def test_check_bad_site_url(oauth_settings, site):
    oauth_settings.SITE_URL = site
    ids = [e.id for e in _check_oauth_config(None)]
    assert ids == ["integration_oauth.E001"]


def test_check_partial_yandex(oauth_settings):
    oauth_settings.YANDEX_ID_CLIENT_SECRET = ""
    assert [e.id for e in _check_oauth_config(None)] == ["integration_oauth.E002"]
