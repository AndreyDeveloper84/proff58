"""Клиенты провайдеров входа: VK ID (id.vk.ru) и Яндекс ID (oauth.yandex.ru).

Здесь только протокол: собрать адрес авторизации (Authorization Code + PKCE S256),
обменять код на токен и получить профиль. Решения «кого впустить» — в services.py.

Правила:
- токены, код и тела ответов /token НЕ логируем и никуда не сохраняем — в логе
  только имя операции, http-статус и короткий код ошибки провайдера;
- любой сбой сети/протокола превращается в :class:`OAuthProviderError` с кодом —
  вызывающий смотрит на ``code``, текст не парсит;
- таймаут на каждый сокетный шаг — ``OAUTH_HTTP_TIMEOUT`` (5 с), плюс общий бюджет
  колбэка ``OAUTH_HTTP_BUDGET`` (15 с) — заметно меньше таймаута gunicorn (120 с);
- телефон не запрашиваем и не берём никогда (scope ``phone`` у VK не просим).
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import logging
import time
import urllib.parse
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.core.features import is_enabled as feature_enabled

logger = logging.getLogger(__name__)

VKID = "vkid"
YANDEX = "yandex"
#: Порядок важен: в таком порядке провайдеры отдаются витрине.
PROVIDERS = (VKID, YANDEX)
LABELS = {VKID: "VK ID", YANDEX: "Яндекс ID"}
#: Способ входа внутри VK ID: сам VK ID, Mail (mail_ru) или OK (ok_ru).
VK_VIA = ("vkid", "mail_ru", "ok_ru")

VK_AUTHORIZE_URL = "https://id.vk.ru/authorize"
VK_TOKEN_URL = "https://id.vk.ru/oauth2/auth"
VK_USER_INFO_URL = "https://id.vk.ru/oauth2/user_info"
VK_SCOPE = "vkid.personal_info email"

YANDEX_AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"
YANDEX_TOKEN_URL = "https://oauth.yandex.ru/token"
YANDEX_INFO_URL = "https://login.yandex.ru/info?format=json"
YANDEX_SCOPE = "login:email login:info"

#: Потолок чтения ответа провайдера: профиль и токены — сотни байт, больше
#: ждать нечего, а бесконечный ответ не должен съесть память воркера.
_MAX_RESPONSE_BYTES = 64 * 1024


class OAuthProviderError(RuntimeError):
    """Сбой провайдера. ``code`` — короткий машинный код для лога и аналитики."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ProviderProfile:
    """Что провайдер сообщил о пользователе (после нормализации)."""

    provider: str
    provider_user_id: str
    email: str  # "" — провайдер почту не отдал или она невалидна
    full_name: str


# ═══════════ Конфигурация ═══════════


def site_origin() -> str:
    """Origin витрины из SITE_URL (``https://host[:port]``) или "" — если непригоден.

    Пригоден только https без пути/query: от него строится redirect_uri, который
    провайдер сверяет байт-в-байт с зарегистрированным.
    """
    raw = (getattr(settings, "SITE_URL", "") or "").strip()
    if not raw:
        return ""
    parts = urllib.parse.urlsplit(raw)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        return ""
    return f"https://{parts.netloc.lower()}"


def site_host() -> str:
    """Host (с портом, если задан) витрины — для сверки Host запроса."""
    origin = site_origin()
    return origin[len("https://") :] if origin else ""


def has_credentials(provider: str) -> bool:
    if provider == VKID:
        return bool(_setting("VKID_CLIENT_ID"))
    if provider == YANDEX:
        return bool(_setting("YANDEX_ID_CLIENT_ID") and _setting("YANDEX_ID_CLIENT_SECRET"))
    return False


def is_enabled(provider: str) -> bool:
    """Провайдер включён ⇔ фичефлаг ∧ ключи ∧ пригодный SITE_URL."""
    return (
        provider in PROVIDERS
        and feature_enabled("oauth_login")
        and has_credentials(provider)
        and bool(site_origin())
    )


def enabled_providers() -> list[str]:
    return [p for p in PROVIDERS if is_enabled(p)]


def redirect_uri(provider: str) -> str:
    """Адрес возврата. Одинаковый в authorize и в обмене кода (VK сверяет байт-в-байт)."""
    return f"{site_origin()}/api/oauth/{provider}/callback/"


def _setting(name: str) -> str:
    return (getattr(settings, name, "") or "").strip()


# ═══════════ Authorize ═══════════


def pkce_challenge(verifier: str) -> str:
    """BASE64URL(SHA256(verifier)) без '=' (RFC 7636, S256)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def authorize_url(
    provider: str,
    *,
    state: str,
    verifier: str,
    via: str | None = None,
    force_confirm: bool = False,
) -> str:
    """Адрес, на который отправляем браузер пользователя."""
    challenge = pkce_challenge(verifier)
    if provider == VKID:
        params = {
            "response_type": "code",
            "client_id": _setting("VKID_CLIENT_ID"),
            "redirect_uri": redirect_uri(VKID),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": VK_SCOPE,
            "provider": via if via in VK_VIA else "vkid",
            "lang_id": "0",
        }
        return f"{VK_AUTHORIZE_URL}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"
    if provider == YANDEX:
        params = {
            "response_type": "code",
            "client_id": _setting("YANDEX_ID_CLIENT_ID"),
            # Явно: иначе Яндекс берёт первый Redirect URI из настроек приложения.
            "redirect_uri": redirect_uri(YANDEX),
            "state": state,
            "scope": YANDEX_SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if force_confirm:
            # Привязка из кабинета: даём выбрать аккаунт Яндекса, а не молча
            # взять тот, под которым браузер уже вошёл.
            params["force_confirm"] = "yes"
        return (
            f"{YANDEX_AUTHORIZE_URL}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"
        )
    raise OAuthProviderError("unknown_provider")


# ═══════════ Обмен кода и профиль ═══════════


def fetch_profile(
    provider: str, *, code: str, verifier: str, state: str, device_id: str = ""
) -> ProviderProfile:
    """Обменять код на токен и получить профиль. Бросает :class:`OAuthProviderError`."""
    deadline = time.monotonic() + float(getattr(settings, "OAUTH_HTTP_BUDGET", 15))
    if provider == VKID:
        return _vk_profile(
            code=code, verifier=verifier, state=state, device_id=device_id, deadline=deadline
        )
    if provider == YANDEX:
        return _yandex_profile(code=code, verifier=verifier, deadline=deadline)
    raise OAuthProviderError("unknown_provider")


def _vk_profile(
    *, code: str, verifier: str, state: str, device_id: str, deadline: float
) -> ProviderProfile:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri(VKID),
        "client_id": _setting("VKID_CLIENT_ID"),
        "device_id": device_id,
        "state": state,
    }
    service_token = _setting("VKID_SERVICE_TOKEN")
    if service_token:
        # Конфиденциальное приложение: сервисный ключ — POST-параметром.
        form["service_token"] = service_token
    token = _request("vkid.token", VK_TOKEN_URL, form=form, deadline=deadline)
    # Ответ на подменённый запрос: state обязан вернуться тем же, что мы выдали.
    if token.get("state") != state:
        raise OAuthProviderError("state_mismatch")
    access_token = token.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise OAuthProviderError("bad_token_response")

    info = _request(
        "vkid.user_info",
        VK_USER_INFO_URL,
        form={"client_id": _setting("VKID_CLIENT_ID"), "access_token": access_token},
        deadline=deadline,
    )
    user = info.get("user")
    if not isinstance(user, dict):
        raise OAuthProviderError("bad_profile")
    user_id = _clean_id(user.get("user_id"))
    if not user_id:
        raise OAuthProviderError("bad_profile")
    token_user_id = token.get("user_id")
    if token_user_id is not None and _clean_id(token_user_id) != user_id:
        # Токен выдан одному пользователю, а профиль — другого: не доверяем обоим.
        raise OAuthProviderError("user_mismatch")
    # Флага «почта подтверждена» у VK ID нет (поле verified — про верификацию
    # страницы, не про почту), поэтому почту по ней с аккаунтами не склеиваем.
    return ProviderProfile(
        provider=VKID,
        provider_user_id=user_id,
        email=_clean_email(user.get("email")),
        full_name=_full_name(user.get("first_name"), user.get("last_name")),
    )


def _yandex_profile(*, code: str, verifier: str, deadline: float) -> ProviderProfile:
    basic = base64.b64encode(
        f"{_setting('YANDEX_ID_CLIENT_ID')}:{_setting('YANDEX_ID_CLIENT_SECRET')}".encode()
    ).decode("ascii")
    token = _request(
        "yandex.token",
        YANDEX_TOKEN_URL,
        form={"grant_type": "authorization_code", "code": code, "code_verifier": verifier},
        headers={"Authorization": f"Basic {basic}"},
        deadline=deadline,
    )
    access_token = token.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise OAuthProviderError("bad_token_response")

    info = _request(
        "yandex.info",
        YANDEX_INFO_URL,
        headers={"Authorization": f"OAuth {access_token}"},
        deadline=deadline,
    )
    user_id = _clean_id(info.get("id"))
    if not user_id:
        raise OAuthProviderError("bad_profile")
    full_name = _full_name(info.get("first_name"), info.get("last_name"))
    if not full_name:
        for key in ("real_name", "display_name"):
            value = info.get(key)
            if isinstance(value, str) and value.strip():
                full_name = value.strip()[:255]
                break
    return ProviderProfile(
        provider=YANDEX,
        provider_user_id=user_id,
        email=_clean_email(info.get("default_email")),
        full_name=full_name,
    )


def _request(
    op: str,
    url: str,
    *,
    form: dict | None = None,
    headers: dict | None = None,
    deadline: float,
) -> dict:
    """HTTP к провайдеру → dict из JSON. В лог — только операция, статус и код ошибки."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        logger.warning("OAuth %s: исчерпан бюджет времени колбэка", op)
        raise OAuthProviderError("timeout")
    timeout = min(float(getattr(settings, "OAUTH_HTTP_TIMEOUT", 5)), remaining)

    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req_headers = {"Accept": "application/json"}
    if data is not None:
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"
    req_headers.update(headers or {})
    req = Request(url, data=data, headers=req_headers, method="POST" if data is not None else "GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read(_MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        # Тело ответа не логируем: у /token там бывают токены и код.
        provider_code = _error_code(_safe_read(exc))
        logger.warning("OAuth %s → HTTP %s (%s)", op, exc.code, provider_code or "-")
        raise OAuthProviderError(f"http_{exc.code}") from None
    except (URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        logger.warning("OAuth %s → сеть недоступна: %s", op, type(exc).__name__)
        raise OAuthProviderError("network") from None

    if len(raw) > _MAX_RESPONSE_BYTES:
        logger.warning("OAuth %s → слишком большой ответ", op)
        raise OAuthProviderError("bad_response")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        logger.warning("OAuth %s → ответ не JSON", op)
        raise OAuthProviderError("bad_response") from None
    if not isinstance(payload, dict):
        raise OAuthProviderError("bad_response")
    if payload.get("error"):
        # VK ID может вернуть ошибку и с кодом 200.
        logger.warning("OAuth %s → ошибка провайдера (%s)", op, _error_code(payload))
        raise OAuthProviderError("provider_error")
    return payload


def _safe_read(exc: HTTPError) -> dict:
    try:
        parsed = json.loads(exc.read(_MAX_RESPONSE_BYTES).decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 — тело ошибки нам только для кода
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _error_code(payload: dict) -> str:
    """Короткий код ошибки провайдера для лога: только [a-z_], не больше 40 символов."""
    value = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(value, str):
        return ""
    value = value[:40]
    return value if all(c.isascii() and (c.isalnum() or c == "_") for c in value) else "?"


def _clean_id(value) -> str:
    """ID пользователя у провайдера: строка из цифр/букв, не пустая, разумной длины."""
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or len(value) > 64 or not all(c.isascii() and c.isalnum() for c in value):
        return ""
    return value


def _clean_email(value) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or len(value) > 254:
        return ""
    try:
        validate_email(value)
    except ValidationError:
        return ""
    return value


def _full_name(first, last) -> str:
    parts = [p.strip() for p in (first, last) if isinstance(p, str) and p.strip()]
    return " ".join(parts)[:255]
