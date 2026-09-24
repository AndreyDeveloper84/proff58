"""Публичные эндпоинты входа через VK ID / Яндекс ID (`/api/oauth/…`).

start и callback — ОБЫЧНЫЕ Django-views, не DRF: браузер приходит сюда
навигацией, и любой исход (ошибка, лимит, успех) — это 302 на страницу сайта с
``oauth_error``/``next``, а не JSON. Страница колбэка не отдаёт HTML вовсе
(требование VK ID: на ней не должно быть скриптов и встроенного контента).
"""

from __future__ import annotations

import json
import logging
import unicodedata
from urllib.parse import urlencode, urlsplit

from django.contrib.auth import login
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from rest_framework.settings import api_settings

from apps.core.throttling import AuthRateThrottle

from . import pending, providers, services
from .providers import PROVIDERS, VK_VIA, VKID, OAuthProviderError

logger = logging.getLogger(__name__)

# Единственный бэкенд, которому можно доверить «впустить без пароля» —
# ModelBackend (EmailBackend требует пароль); указываем явно, как MAX.
_AUTH_BACKEND = "django.contrib.auth.backends.ModelBackend"

DEFAULT_NEXT = "/account/profile"
LOGIN_PAGE = "/account/login"
PROFILE_PAGE = "/account/profile"
#: Куда после входа возвращать нельзя: API и сама страница входа (петля).
_FORBIDDEN_NEXT_PREFIXES = ("/api/", "/account/login")
_MAX_NEXT_LEN = 1024
_MAX_PAYLOAD_LEN = 4096


class OAuthStartRateThrottle(AuthRateThrottle):
    """Лимит старта входа по IP: ставка — как у входа паролем (scope ``auth``),
    а счётчик свой, чтобы попытки соцвхода не съедали лимит формы входа."""

    scope = "oauth_start"

    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES.get("auth")


# ═══════════ Вспомогательное ═══════════


def sanitize_next(raw) -> str:
    """Путь сайта, куда вернуть после входа, либо ``/account/profile``.

    Только относительный путь этого же сайта: начинается с одного "/", без
    управляющих и пробельных символов (браузер выкидывает \\t\\r\\n и превращает
    "/\\t/evil.com" в "//evil.com"), без обратных слэшей, не в API и не на страницу
    входа.
    """
    if not isinstance(raw, str) or not raw or len(raw) > _MAX_NEXT_LEN:
        return DEFAULT_NEXT
    for ch in raw:
        if ch.isspace() or unicodedata.category(ch).startswith("C") or ch == "\\":
            return DEFAULT_NEXT
    if not raw.startswith("/") or raw.startswith("//"):
        return DEFAULT_NEXT
    host = providers.site_host()
    if not host or not url_has_allowed_host_and_scheme(
        raw, allowed_hosts={host}, require_https=True
    ):
        return DEFAULT_NEXT
    path = urlsplit(raw).path.lower()
    if path == "/api" or any(path.startswith(p) for p in _FORBIDDEN_NEXT_PREFIXES):
        return DEFAULT_NEXT
    return raw


def _login_error(
    code: str, *, provider: str | None = None, next_url: str = ""
) -> HttpResponseRedirect:
    params = {"oauth_error": code}
    if provider in PROVIDERS and code in ("email_exists", "no_email"):
        params["provider"] = provider
    if next_url and next_url != DEFAULT_NEXT:
        params["next"] = next_url
    return HttpResponseRedirect(f"{LOGIN_PAGE}?{urlencode(params)}")


def _profile_redirect(**params) -> HttpResponseRedirect:
    return HttpResponseRedirect(f"{PROFILE_PAGE}?{urlencode(params)}")


def _fail(entry: dict, provider: str, code: str) -> HttpResponseRedirect:
    """Ошибка колбэка: привязка возвращает в профиль, вход — на страницу входа."""
    services.emit("oauth_login_failed", provider=provider, intent=entry.get("intent"), reason=code)
    if entry.get("intent") == "link":
        return _profile_redirect(oauth_error=code)
    return _login_error(code, provider=provider, next_url=entry.get("next") or "")


def _callback_params(request, provider: str) -> dict | None:
    """code/state/device_id/error из query. VK ID может прислать всё одним ``payload``
    (JSON) — принимаем оба варианта. None — payload битый."""
    params = {
        "code": request.GET.get("code", ""),
        "state": request.GET.get("state", ""),
        "device_id": request.GET.get("device_id", ""),
        "error": request.GET.get("error", ""),
    }
    raw = request.GET.get("payload")
    if provider == VKID and raw is not None:
        if len(raw) > _MAX_PAYLOAD_LEN:
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        for key in ("code", "state", "device_id"):
            value = data.get(key)
            if value is None:
                continue
            if not isinstance(value, str):
                return None
            params[key] = value
    return params


# ═══════════ Эндпоинты ═══════════


@require_GET
def providers_list(request):
    """GET /api/oauth/providers/ — включённые провайдеры (для SSR страницы входа)."""
    return JsonResponse({"providers": [{"id": p} for p in providers.enabled_providers()]})


@require_GET
@never_cache
def start(request, provider: str):
    """GET /api/oauth/<provider>/start/?next=/path&via=mail_ru — уйти к провайдеру."""
    if not providers.is_enabled(provider):
        return _login_error("unavailable", next_url=sanitize_next(request.GET.get("next")))

    # Сессия (а с ней state) живёт на хосте SITE_URL — туда же вернётся провайдер.
    # Старт с другого хоста (www) переносим на канонический, иначе колбэк не найдёт state.
    host = providers.site_host()
    if request.get_host().lower() != host:
        return HttpResponseRedirect(f"{providers.site_origin()}{request.get_full_path()}")

    next_url = sanitize_next(request.GET.get("next"))
    if not OAuthStartRateThrottle().allow_request(request, None):
        return _login_error("rate_limited", next_url=next_url)

    via = request.GET.get("via")
    via = via if provider == VKID and via in VK_VIA else None
    state, verifier = pending.create(
        request.session, provider=provider, intent="login", next_url=next_url, via=via
    )
    services.emit("oauth_login_started", provider=provider, intent="login", via=via)
    return HttpResponseRedirect(
        providers.authorize_url(provider, state=state, verifier=verifier, via=via)
    )


@require_GET
@never_cache
def callback(request, provider: str):
    """GET /api/oauth/<provider>/callback/ — возврат от провайдера. Ответ всегда 302."""
    if provider not in PROVIDERS:
        return _login_error("unavailable")

    params = _callback_params(request, provider)
    if params is None:
        return _login_error("failed")

    # state сверяем ДО любых сетевых вызовов: чужой/повторный колбэк до провайдера
    # не доходит и код не обменивает.
    state = params["state"]
    entry = pending.pop(request.session, state, provider)
    if entry is None:
        done = pending.get_done(request.session, state)
        if (
            done is not None
            and request.user.is_authenticated
            and request.user.pk == done.get("user_id")
        ):
            # Повторный колбэк уже завершённого входа (двойной клик, «назад»).
            return HttpResponseRedirect(done["redirect"])
        return _login_error("cancelled" if params["error"] else "expired")

    if params["error"]:
        # access_denied и т.п. — пользователь отказался на стороне провайдера.
        return _fail(entry, provider, "cancelled")
    if not providers.is_enabled(provider):
        return _fail(entry, provider, "unavailable")

    is_link = entry.get("intent") == "link"
    if is_link and not (request.user.is_authenticated and request.user.pk == entry.get("user_id")):
        # Привязку начинал другой пользователь или сессия уже вышла — не обмениваем код.
        return _fail(entry, provider, "link_expired")

    if not params["code"] or (provider == VKID and not params["device_id"]):
        return _fail(entry, provider, "failed")

    try:
        profile = providers.fetch_profile(
            provider,
            code=params["code"],
            verifier=entry["verifier"],
            state=state,
            device_id=params["device_id"],
        )
    except OAuthProviderError as exc:
        logger.warning("OAuth %s: вход не удался (%s)", provider, exc.code)
        return _fail(entry, provider, "failed")

    if is_link:
        result = services.link_account(request.user, profile)
        if result.error:
            return _fail(entry, provider, result.error)
        services.emit(
            "oauth_account_linked", user=request.user, provider=provider, is_new=result.created
        )
        redirect_to = f"{PROFILE_PAGE}?{urlencode({'oauth_linked': provider})}"
        pending.remember_done(
            request.session, state=state, redirect_to=redirect_to, user_id=request.user.pk
        )
        return HttpResponseRedirect(redirect_to)

    result = services.resolve_login(profile)
    if result.error:
        return _fail(entry, provider, result.error)
    user = result.user
    login(request, user, backend=_AUTH_BACKEND)
    # claim_guest_orders не вызываем — см. docstring services.py (нет телефона).
    redirect_to = entry.get("next") or DEFAULT_NEXT
    pending.remember_done(request.session, state=state, redirect_to=redirect_to, user_id=user.pk)
    services.emit(
        "oauth_login_completed",
        user=user,
        provider=provider,
        via=entry.get("via"),
        is_new_user=result.created,
    )
    return HttpResponseRedirect(redirect_to)
