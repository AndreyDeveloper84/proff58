"""Настройки для продакшн-окружения."""

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *  # noqa: F401,F403
from .base import ALLOWED_HOSTS, env

DEBUG = False

# Межсервисные запросы внутри Docker (Next SSR → Django по http://web:8000) приходят с Host "web".
# Добавляем внутренний хост точечно в prod (не глобально в base) — управляемо через env.
ALLOWED_HOSTS += env.list("INTERNAL_ALLOWED_HOSTS", default=["web"])

# Кэш — общий Redis для всех воркеров gunicorn. LocMem был бы у каждого процесса
# свой, и прогретое дерево каталога не переиспользовалось бы между воркерами.
# Отдельная БД Redis (2), чтобы не пересекаться с брокером (0) и result-backend (1)
# Celery.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_CACHE_URL", default="redis://redis:6379/2"),
        "TIMEOUT": env.int("DJANGO_CACHE_TTL", default=300),
    }
}

# Кэш фасетов каталога (#222, P1-2) включён в проде; TTL — бэкстоп поверх версионной
# инвалидации по сигналам изменения данных каталога (см. apps/catalog/facets.py).
FACETS_CACHE_TTL = env.int("FACETS_CACHE_TTL", default=300)

# Для входа в админку за nginx/HTTPS Django требует доверенные origin-ы.
_public_hosts = [h for h in ALLOWED_HOSTS if h not in ("*", "localhost", "127.0.0.1")]
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in _public_hosts] + [
    f"http://{h}" for h in _public_hosts
]

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^healthz/?$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=env("SENTRY_ENVIRONMENT", default="production"),
    )
