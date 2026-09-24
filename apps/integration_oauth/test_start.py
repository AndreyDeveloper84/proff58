"""Старт входа через VK ID / Яндекс ID: адрес провайдера, PKCE, next, хост, лимит."""

from __future__ import annotations

import base64
import hashlib
import re

import pytest

from . import pending
from .conftest import HOST, SITE, location, query, start
from .views import sanitize_next

pytestmark = pytest.mark.django_db


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


def _pending(browser) -> dict:
    return browser.session[pending.SESSION_KEY]


def test_vk_authorize_url_and_pkce(browser):
    url = location(browser.get("/api/oauth/vkid/start/", {"next": "/catalog/drel?x=1"}))
    assert url.startswith("https://id.vk.ru/authorize?")
    q = query(url)
    assert q["response_type"] == "code"
    assert q["client_id"] == "vk-client"
    assert q["redirect_uri"] == f"{SITE}/api/oauth/vkid/callback/"
    assert q["scope"] == "vkid.personal_info email"  # телефон не просим
    assert q["provider"] == "vkid"
    assert q["lang_id"] == "0"
    assert q["code_challenge_method"] == "S256"
    assert re.fullmatch(r"[A-Za-z0-9_-]{43,}", q["state"])
    entry = _pending(browser)[q["state"]]
    assert entry["provider"] == "vkid" and entry["intent"] == "login"
    assert entry["next"] == "/catalog/drel?x=1"
    assert entry["user_id"] is None
    assert 43 <= len(entry["verifier"]) <= 128
    assert q["code_challenge"] == _challenge(entry["verifier"])
    assert "=" not in q["code_challenge"]
    # Секреты в адрес не утекают.
    assert "vk-service" not in url and entry["verifier"] not in url


def test_yandex_authorize_url(browser):
    url = location(browser.get("/api/oauth/yandex/start/"))
    assert url.startswith("https://oauth.yandex.ru/authorize?")
    q = query(url)
    assert q["client_id"] == "ya-client"
    assert q["redirect_uri"] == f"{SITE}/api/oauth/yandex/callback/"
    assert q["scope"] == "login:email login:info"
    assert q["code_challenge_method"] == "S256"
    assert "force_confirm" not in q  # только для привязки из кабинета
    assert "ya-secret" not in url
    entry = _pending(browser)[q["state"]]
    assert q["code_challenge"] == _challenge(entry["verifier"])
    assert entry["next"] == "/account/profile"


@pytest.mark.parametrize(
    ("provider", "via", "expected_provider_param", "expected_via"),
    [
        ("vkid", "mail_ru", "mail_ru", "mail_ru"),
        ("vkid", "ok_ru", "ok_ru", "ok_ru"),
        ("vkid", "evil", "vkid", None),
        ("yandex", "mail_ru", None, None),
    ],
)
def test_via(browser, provider, via, expected_provider_param, expected_via):
    q = query(location(browser.get(f"/api/oauth/{provider}/start/", {"via": via})))
    assert q.get("provider") == expected_provider_param
    assert _pending(browser)[q["state"]]["via"] == expected_via


@pytest.mark.parametrize(
    "raw",
    [
        "/\t/evil.com",
        "/\n/evil.com",
        "/ /evil.com",
        "//evil.com",
        "/\\evil.com",
        "/x\\y",
        "https://evil.com/",
        "https://proff58.ru/catalog",  # только путь, даже свой хост абсолютным не берём
        "catalog",
        "",
        "/api/oauth/vkid/start/",
        "/API/account/me/",
        "/api",
        "/account/login?next=/x",
        "/account/login",
        "/a​b",  # невидимый символ формата
        "/" + "a" * 2000,
    ],
)
def test_sanitize_next_rejects(raw):
    assert sanitize_next(raw) == "/account/profile"


@pytest.mark.parametrize(
    "raw",
    ["/", "/catalog/drel", "/catalog?brand=bosch&page=2", "/account/orders/PROF-1", "/поиск"],
)
def test_sanitize_next_accepts(raw):
    assert sanitize_next(raw) == raw


def test_bad_next_falls_back_in_pending(browser):
    q = query(location(browser.get("/api/oauth/vkid/start/", {"next": "/\t/evil.com"})))
    assert _pending(browser)[q["state"]]["next"] == "/account/profile"


def test_other_host_redirected_to_site_url():
    from rest_framework.test import APIClient

    www = APIClient(HTTP_HOST=f"www.{HOST}")
    resp = www.get("/api/oauth/vkid/start/", {"next": "/catalog", "via": "mail_ru"})
    url = location(resp)
    assert url.startswith(f"{SITE}/api/oauth/vkid/start/?")
    assert query(url) == {"next": "/catalog", "via": "mail_ru"}
    assert pending.SESSION_KEY not in www.session  # state на чужом хосте не заводим


@pytest.mark.parametrize(
    "tweak",
    [
        {"VKID_CLIENT_ID": ""},
        {"SITE_URL": ""},
        {"SITE_URL": "http://proff58.ru"},
        {"SITE_URL": "https://proff58.ru/shop"},
        {"FEATURES": {"oauth_login": False}},
    ],
)
def test_disabled_provider(browser, oauth_settings, tweak):
    for key, value in tweak.items():
        setattr(oauth_settings, key, value)
    resp = browser.get("/api/oauth/vkid/start/", {"next": "/catalog"})
    assert location(resp).startswith("/account/login?oauth_error=unavailable")
    assert pending.SESSION_KEY not in browser.session


def test_disabled_provider_keeps_next(browser, oauth_settings):
    oauth_settings.VKID_CLIENT_ID = ""
    resp = browser.get("/api/oauth/vkid/start/", {"next": "/catalog"})
    assert location(resp) == "/account/login?oauth_error=unavailable&next=%2Fcatalog"


def test_unknown_provider(browser):
    assert location(browser.get("/api/oauth/google/start/")).endswith("oauth_error=unavailable")


def test_yandex_needs_secret(browser, oauth_settings):
    oauth_settings.YANDEX_ID_CLIENT_SECRET = ""
    assert location(browser.get("/api/oauth/yandex/start/")).endswith("oauth_error=unavailable")
    assert location(browser.get("/api/oauth/vkid/start/")).startswith("https://id.vk.ru/")


def test_rate_limited(browser, oauth_settings):
    oauth_settings.REST_FRAMEWORK = {
        **oauth_settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **oauth_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
            "auth": "2/min",
        },
    }
    for _ in range(2):
        assert location(browser.get("/api/oauth/vkid/start/")).startswith("https://id.vk.ru/")
    assert (
        location(browser.get("/api/oauth/vkid/start/")) == "/account/login?oauth_error=rate_limited"
    )


def test_pending_capped(browser):
    states = [start(browser) for _ in range(pending.MAX_PENDING + 2)]
    kept = _pending(browser)
    assert len(kept) == pending.MAX_PENDING
    assert states[-1] in kept and states[0] not in kept


def test_providers_list(client, oauth_settings):
    assert client.get("/api/oauth/providers/").json() == {
        "providers": [{"id": "vkid"}, {"id": "yandex"}]
    }
    oauth_settings.VKID_CLIENT_ID = ""
    assert client.get("/api/oauth/providers/").json() == {"providers": [{"id": "yandex"}]}
    oauth_settings.FEATURES = {"oauth_login": False}
    assert client.get("/api/oauth/providers/").json() == {"providers": []}
