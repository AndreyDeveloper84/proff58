"""Настройки для продакшн-окружения."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import ALLOWED_HOSTS, env

DEBUG = False

# SECRET_KEY: fail-fast в проде (#8 код-ревью). Без дефолта — отсутствие env
# бросит ImproperlyConfigured; публичный дефолт из base отвергаем явно, иначе
# прод поднялся бы с общеизвестным ключом (подделка session-cookie и подписанных
# токенов сброса пароля вплоть до входа за is_staff).
SECRET_KEY = env("DJANGO_SECRET_KEY")
if SECRET_KEY == "insecure-change-me-in-prod":
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY равен небезопасному дефолту — задайте уникальный ключ в проде."
    )

# Оплата снова под env (#311 закрыт): webhook принимает только то, что подтвердил
# перезапрос к API ЮKassa, сумма и валюта сверяются с заказом, принадлежность —
# по metadata.order_id, терминальные статусы не откатываются (см. payments/services).
#
# По умолчанию ВЫКЛЮЧЕНО: включать осмысленно только там, где заданы боевые или
# тестовые ключи магазина (YOOKASSA_SHOP_ID/YOOKASSA_SECRET_KEY). Без них касса
# всё равно недоступна, и покупатель упрётся в ошибку уже после оформления.
PAYMENTS_ENABLED = env.bool("PAYMENTS_ENABLED", default=False)

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

# Fail-fast: без реального домена CSRF_TRUSTED_ORIGINS пуст → вход в админку сломан (#282).
_internal = {"*", "localhost", "127.0.0.1", "web"}
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS содержит '*' — в проде запрещено. Укажите явные домены."
    )
_public_hosts = [h for h in ALLOWED_HOSTS if h not in _internal]
if not _public_hosts:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS не содержит публичного домена — задайте его в env "
        "(напр. DJANGO_ALLOWED_HOSTS=proff58.ru)."
    )
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
    # Импортируем лениво: sentry-sdk нужен только в проде с заданным DSN, без него
    # модуль настроек импортируется и там, где пакет не установлен (dev/тесты).
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=env("SENTRY_ENVIRONMENT", default="production"),
    )
