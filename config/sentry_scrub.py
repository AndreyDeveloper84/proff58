"""Скраб событий Sentry: секреты входа через VK ID / Яндекс ID из query.

Колбэк провайдера приходит на ``/api/oauth/<provider>/callback/`` с одноразовым
кодом авторизации, ``state``, ``device_id`` (VK) или всем этим в ``payload``. Код
живёт минуты, но в Sentry (ошибки и трейсы) ему делать нечего. Модуль без импортов
Django — подключается прямо из settings/prod.py.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

OAUTH_PATH = "/api/oauth/"
SENSITIVE_PARAMS = frozenset({"code", "state", "device_id", "payload"})
FILTERED = "[Filtered]"


def _scrub_query(query: str) -> str:
    pairs = parse_qsl(query, keep_blank_values=True)
    return urlencode([(k, FILTERED if k in SENSITIVE_PARAMS else v) for k, v in pairs])


def _scrub_url(url: str) -> str:
    parts = urlsplit(url)
    if OAUTH_PATH not in parts.path or not parts.query:
        return url
    return urlunsplit(parts._replace(query=_scrub_query(parts.query)))


def scrub_oauth_event(event, hint=None):
    """before_send / before_send_transaction: вычистить секреты колбэка OAuth."""
    request = event.get("request")
    if isinstance(request, dict) and OAUTH_PATH in str(request.get("url") or ""):
        request["url"] = _scrub_url(str(request["url"]))
        qs = request.get("query_string")
        if isinstance(qs, str):
            request["query_string"] = _scrub_query(qs)
        elif isinstance(qs, dict):
            request["query_string"] = {
                k: (FILTERED if k in SENSITIVE_PARAMS else v) for k, v in qs.items()
            }
        elif isinstance(qs, list):
            request["query_string"] = [
                (
                    [p[0], FILTERED if p[0] in SENSITIVE_PARAMS else p[1]]
                    if isinstance(p, list | tuple) and len(p) == 2
                    else p
                )
                for p in qs
            ]
    breadcrumbs = event.get("breadcrumbs")
    values = breadcrumbs.get("values") if isinstance(breadcrumbs, dict) else breadcrumbs
    for crumb in values or []:
        data = crumb.get("data") if isinstance(crumb, dict) else None
        if isinstance(data, dict):
            for key in ("url", "from", "to"):
                if isinstance(data.get(key), str):
                    data[key] = _scrub_url(data[key])
    return event
