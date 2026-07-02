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
        "auth": None,  # #427/M-03: отключено в dev/тестах (кумулятивный кэш ломал бы прогон)
    },
}

DEBUG = env("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware", *MIDDLEWARE]

INTERNAL_IPS = ["127.0.0.1"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Celery: в dev/тестах задачи выполняются inline (без воркера и Redis).
# В проде это не задаётся → работает реальный воркер.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)
CELERY_TASK_EAGER_PROPAGATES = True
