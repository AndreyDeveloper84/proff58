"""Общие фикстуры тестов входа через VK ID / Яндекс ID: ключи, сеть-заглушка, браузер."""

from __future__ import annotations

import io
import json
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

SITE = "https://proff58.ru"
HOST = "proff58.ru"
VK_TOKEN = "https://id.vk.ru/oauth2/auth"
VK_INFO = "https://id.vk.ru/oauth2/user_info"
YA_TOKEN = "https://oauth.yandex.ru/token"
YA_INFO = "https://login.yandex.ru/info"


@pytest.fixture(autouse=True)
def oauth_settings(settings):
    settings.SITE_URL = SITE
    settings.VKID_CLIENT_ID = "vk-client"
    settings.VKID_SERVICE_TOKEN = "vk-service"
    settings.YANDEX_ID_CLIENT_ID = "ya-client"
    settings.YANDEX_ID_CLIENT_SECRET = "ya-secret"
    settings.FEATURES = {**settings.FEATURES, "oauth_login": True}
    settings.DEFAULT_FROM_EMAIL = "site@proff58.ru"
    # MAX по умолчанию не настроен — тесты, которым он нужен, включают сами.
    settings.MAX_BOT_TOKEN = ""
    settings.MAX_BOT_USERNAME = ""
    cache.clear()
    yield settings
    cache.clear()


class _Resp:
    def __init__(self, body: bytes):
        self._buf = io.BytesIO(body)

    def read(self, n=-1):
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeNet:
    """Заглушка urlopen: ответы по префиксу URL, запись всех запросов.

    Ответ — dict, bytes или callable(request) → dict. ``status`` ≥ 400 → HTTPError.
    """

    def __init__(self):
        self.routes: list[tuple[str, int, object]] = []
        self.calls = []

    def add(self, prefix: str, body, status: int = 200):
        self.routes.insert(0, (prefix, status, body))
        return self

    def __call__(self, req, timeout=None):
        self.calls.append(req)
        for prefix, status, body in self.routes:
            if req.full_url.startswith(prefix):
                if callable(body):
                    body = body(req)
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                if status >= 400:
                    raise HTTPError(req.full_url, status, "error", {}, io.BytesIO(raw))
                return _Resp(raw)
        raise URLError("нет маршрута в тесте")

    def form(self, index: int) -> dict:
        """Тело form-запроса ``index`` как dict (одиночные значения)."""
        data = self.calls[index].data.decode()
        return {k: v[0] for k, v in parse_qs(data).items()}


@pytest.fixture
def net(monkeypatch):
    fake = FakeNet()
    monkeypatch.setattr("apps.integration_oauth.providers.urlopen", fake)
    return fake


def vk_ok(net: FakeNet, *, user_id="1001", email="ivan@vk.ru", first="Иван", last="П"):
    """VK ID: обмен эхом возвращает state из запроса, профиль — заданный."""

    def token(req):
        form = {k: v[0] for k, v in parse_qs(req.data.decode()).items()}
        return {"access_token": "vk-at", "state": form.get("state"), "user_id": int(user_id)}

    user = {"user_id": user_id, "first_name": first, "last_name": last}
    if email is not None:
        user["email"] = email
    net.add(VK_TOKEN, token)
    net.add(VK_INFO, {"user": user})
    return net


def ya_ok(net: FakeNet, *, user_id="777", email="petr@yandex.ru"):
    net.add(YA_TOKEN, {"access_token": "ya-at", "token_type": "bearer"})
    info = {"id": user_id, "first_name": "Пётр", "last_name": "Иванов", "login": "petr"}
    if email is not None:
        info["default_email"] = email
    net.add(YA_INFO, info)
    return net


@pytest.fixture
def browser():
    """Браузер на каноническом хосте SITE_URL (одна сессия на весь тест)."""
    return APIClient(HTTP_HOST=HOST)


def location(resp) -> str:
    assert resp.status_code == 302, resp.status_code
    return resp["Location"]


def query(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def start(browser, provider="vkid", **params) -> str:
    """Начать вход, вернуть state из адреса провайдера."""
    resp = browser.get(f"/api/oauth/{provider}/start/", params)
    return query(location(resp))["state"]


def callback(browser, provider, state, **extra):
    params = {"state": state, "code": "the-code"}
    if provider == "vkid":
        params["device_id"] = "dev-1"
    params.update(extra)
    params = {k: v for k, v in params.items() if v is not None}
    return browser.get(f"/api/oauth/{provider}/callback/", params)
