"""Настройки для локальной разработки."""

from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS, MIDDLEWARE, REST_FRAMEWORK, env

# В dev/тестах не троттлим onec/orders: кэш троттла кумулятивен между запросами,
# и реальные лимиты ломали бы прогон тестов. Прод берёт лимиты из base (#9).
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
        "onec": None,
        "orders": None,
        "anon": None,  # #279: отключено в dev/тестах
        "auth": None,
        "reviews": None,  # #427/M-03: отключено в dev/тестах (кумулятивный кэш ломал бы прогон)
        "password_reset_email": None,  # DRF-2298: то же — кэш по адресу переживал бы тесты
    },
}

DEBUG = env("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware", *MIDDLEWARE]

INTERNAL_IPS = ["127.0.0.1"]


def show_toolbar(request):
    """Показывать ли debug-toolbar. Штатный колбэк на КАЖДОМ запросе резолвит
    `host.docker.internal`; в контейнере на Linux имя не резолвится, и каждый
    запрос (даже /healthz/) ждал DNS-таймаут ~8 с. Здесь — только INTERNAL_IPS."""
    return DEBUG and request.META.get("REMOTE_ADDR") in INTERNAL_IPS


DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": "config.settings.dev.show_toolbar"}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Celery: в dev/тестах задачи выполняются inline (без воркера и Redis).
# В проде это не задаётся → работает реальный воркер.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)
# Stub-провайдер перевозчика разрешён только локально (T1: не 0 ₽ на проде).
SHIP_ALLOW_STUB = env.bool("SHIP_ALLOW_STUB", default=True)
CELERY_TASK_EAGER_PROPAGATES = True
