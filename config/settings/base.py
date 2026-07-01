"""Базовые настройки проекта «Профессионал».

Значения, специфичные для окружения, читаются из переменных окружения
(см. .env.example). Разделение dev/prod — в одноимённых модулях.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-change-me-in-prod")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    # Современная тема админки (должна идти перед django.contrib.admin).
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # сторонние
    "rest_framework",
    "django_filters",
    "treebeard",
    # приложения проекта
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.sync_1c",
    "apps.pricing",
    "apps.orders",
    "apps.payments",
    "apps.leads",
    "apps.ai",
    "apps.integration_max",
    "apps.notifications",
    "apps.crm_clients",
    "apps.crm_sales",
    "apps.crm_tasks",
    "apps.analytics",
    "apps.delivery",
    "apps.content",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    # Дефолт — localhost: чтобы локальный pytest/manage работал без Docker (нужен
    # доступный Postgres на :5432, напр. `docker compose up -d db`). В Docker и CI
    # хост задаётся явно через DATABASE_URL (env/.env: `db`/`localhost`), дефолт не используется.
    "default": env.db("DATABASE_URL", default="postgres://proff:proff@localhost:5432/proff58"),
}
# По умолчанию Django открывает новое соединение с БД на КАЖДЫЙ запрос — заметная
# задержка, особенно «подвисание» первого клика после простоя. Держим соединение
# открытым между запросами; CONN_HEALTH_CHECKS отбраковывает протухшее соединение
# перед запросом (иначе первый запрос после простоя мог бы упасть на мёртвом сокете).
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DJANGO_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# Кэш приложения. По умолчанию — локальный, чтобы dev и CI не зависели от Redis.
# В проде переопределяется на общий Redis (см. config/settings/prod.py).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "proff58-default",
    }
}

# Кэш фасетов каталога (#222, P1-2). 0 → выключен (dev/CI: тесты не зависят от кэша и его
# межтестовой персистентности). В проде включается (см. config/settings/prod.py). Инвалидация —
# версионная, по сигналам изменения товаров/категорий/привязок атрибутов (apps/catalog/signals.py).
FACETS_CACHE_TTL = env.int("FACETS_CACHE_TTL", default=0)

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Тема админки django-jazzmin. Бренд «Профессионал».
JAZZMIN_SETTINGS = {
    "site_title": "Профессионал — админка",
    "site_header": "Профессионал",
    "site_brand": "Профессионал",
    "welcome_sign": "Панель управления «Профессионал»",
    "copyright": "Профессионал",
    "search_model": ["catalog.Product", "catalog.Category"],
    "show_ui_builder": False,
    "related_modal_active": True,
}

JAZZMIN_UI_TWEAKS = {
    "theme": "flatly",
    "dark_mode_theme": "darkly",
    "navbar_fixed": True,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary",
}

# Celery / Redis
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://redis:6379/1")
CELERY_TASK_TRACK_STARTED = True
CELERY_TIMEZONE = TIME_ZONE

# Задачи 1С — в выделенную очередь `onec` (worker -Q onec -c 1): обмены идут строго
# последовательно, что снимает гонку «одна актуальная цена» (#126). Остальные задачи —
# в дефолтной очереди `celery` (отдельный worker, параллельно).
CELERY_TASK_DEFAULT_QUEUE = "celery"
CELERY_TASK_ROUTES = {"apps.sync_1c.tasks.*": {"queue": "onec"}}

# Session/CSRF для SPA (#325): cookie читается JS (HTTPONLY=False), SameSite=Lax
# позволяет браузеру слать cookies при навигации. CSRF_COOKIE_SECURE и
# SESSION_COOKIE_SECURE переопределяются в prod.py на True.
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # JS должен читать csrftoken для X-CSRFToken заголовка
CSRF_COOKIE_SAMESITE = "Lax"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 24,
    # #279: глобальный анонимный лимит — защита каталога/фасетов от DoS.
    # Вьюхи с явным throttle_classes (1С, корзина, заказы) его не наследуют.
    "DEFAULT_THROTTLE_CLASSES": ["apps.core.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "inquiry": "20/hour",
        # #9: флуд чувствительных эндпоинтов. onec — поток валидным ключом 1С (по IP),
        # orders — оформление/добавление в корзину гостем. Настраиваются через env;
        # пусто/None отключает скоуп (в dev/тестах — выключено, см. dev.py).
        "onec": env("ONEC_THROTTLE_RATE", default="300/min"),
        "orders": env("ORDERS_THROTTLE_RATE", default="60/min"),
        # #279: лимит анонимных запросов к публичному API (каталог, фасеты, поиск).
        "anon": env("ANON_THROTTLE_RATE", default="200/min"),
    },
}

# Ключ для интеграции с 1С (заголовок X-Api-Key). Пустой = API для 1С закрыт.
ONEC_API_KEY = env("ONEC_API_KEY", default="")
# Максимум строк в одном пакете 1С (items). Превышение → 400.
ONEC_MAX_ITEMS = env.int("ONEC_MAX_ITEMS", default=1000)

# Надёжность фон-импорта 1С (#57): зависшие RUNNING + retry.
# Порог «зависшего» прогона: RUNNING без финализации дольше этого времени janitor
# (mark_stale_syncs) помечает ERROR. Закрывает дыру «воркер умер между стартом и финалом».
SYNC_STALE_TIMEOUT = env.int("SYNC_STALE_TIMEOUT", default=30 * 60)  # секунды
# Hard time_limit задачи импорта (SIGKILL воркера). soft_time_limit на минуту меньше —
# даёт задаче финализировать прогон в ERROR до жёсткого убийства.
SYNC_IMPORT_TIME_LIMIT = env.int("SYNC_IMPORT_TIME_LIMIT", default=15 * 60)  # секунды

# MAX Bot (мессенджер) — уведомления и авторизация (docs/max-bot-setup.md).
MAX_BOT_TOKEN = env("MAX_BOT_TOKEN", default="")
MAX_WEBHOOK_SECRET = env("MAX_WEBHOOK_SECRET", default="")
MAX_BOT_API_URL = env("MAX_BOT_API_URL", default="https://platform-api.max.ru")

# ЮKassa
# Kill-switch webhook'а оплаты. По умолчанию включён (локалка/тесты); на стенде
# выключается в prod.py до закрытия #311 (webhook без аутентификации).
PAYMENTS_ENABLED = env.bool("PAYMENTS_ENABLED", default=True)
YOOKASSA_SHOP_ID = env("YOOKASSA_SHOP_ID", default="")
YOOKASSA_SECRET_KEY = env("YOOKASSA_SECRET_KEY", default="")
YOOKASSA_WEBHOOK_SECRET = env("YOOKASSA_WEBHOOK_SECRET", default="")

# AI-источники контента (capability sourcing).
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
YANDEX_MARKET_API_KEY = env("YANDEX_MARKET_API_KEY", default="")
SOURCING_ALLOWLIST = {d.lower() for d in env.list("SOURCING_ALLOWLIST", default=[])}

# Feature-флаги. Инфраструктурные — здесь (через env, меняют разработчики).
# Бизнес-флаги (reviews/b2b/...) живут в SiteSettings. Проверка — через
# apps.core.features.is_enabled(); механизм поддерживает override любого флага
# через этот словарь.
FEATURES = {
    "crm": env.bool("FEATURE_CRM", default=False),
    "ai": env.bool("FEATURE_AI", default=False),
    "ai_sourcing": env.bool("FEATURE_AI_SOURCING", default=False),
    "eventbus": env.bool("FEATURE_EVENTBUS", default=True),
    "analytics": env.bool("FEATURE_ANALYTICS", default=False),
    "external_integrations": env.bool("FEATURE_EXTERNAL_INTEGRATIONS", default=True),
}


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "django_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "django.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "standard",
        },
        "onec_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "1c.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "standard",
        },
        "payments_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "payments.log",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "standard",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "django_file"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.sync_1c": {
            "handlers": ["console", "onec_file"],
            "level": "INFO",
            "propagate": False,
        },
        "payments": {
            "handlers": ["console", "payments_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
