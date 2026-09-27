"""Access-лог gunicorn без секретов в query (DRF-2482).

Одноразовый ``code`` колбэка входа через VK ID/Яндекс ID и постоянный токен вебхука
АТОЛ Pay (``?t=``) приходят в query. У этих путей query заменяется на ``[hidden]``;
остальные запросы логируются как есть — по query каталога и фасетов SSR-запросов
(они идут в gunicorn мимо nginx) ищут медленные запросы.

Подключение: ``gunicorn --logger-class config.gunicorn_logging.ScrubbedLogger``.
"""

from gunicorn.glogging import Logger

SENSITIVE_PREFIXES = ("/api/oauth/", "/api/payments/webhook/")
HIDDEN = "[hidden]"


class ScrubbedLogger(Logger):
    def atoms(self, resp, req, environ, request_time):
        atoms = super().atoms(resp, req, environ, request_time)
        path = environ.get("PATH_INFO") or ""
        if environ.get("QUERY_STRING") and path.startswith(SENSITIVE_PREFIXES):
            uri = f"{path}?{HIDDEN}"
            method, protocol = environ.get("REQUEST_METHOD"), environ.get("SERVER_PROTOCOL")
            atoms["r"] = f"{method} {uri} {protocol}"
            atoms["q"] = HIDDEN
            # Переменные окружения доступны формату как {имя}e — прячем и их, чтобы
            # секрет не вернулся при смене --access-logformat.
            for key, value in (
                ("{raw_uri}e", uri),
                ("{request_uri}e", uri),
                ("{query_string}e", HIDDEN),
            ):
                if key in atoms:
                    atoms[key] = value
        return atoms
