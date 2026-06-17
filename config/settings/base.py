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
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # сторонние
    "rest_framework",
    "django_filters",
    "treebeard",
    # приложения проекта
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.sync_1c",
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
    "default": env.db("DATABASE_URL", default="postgres://proff:proff@db:5432/proff58"),
}

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

# Celery / Redis
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://redis:6379/1")
CELERY_TASK_TRACK_STARTED = True
CELERY_TIMEZONE = TIME_ZONE

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 24,
}

# Ключ для интеграции с 1С (заголовок X-Api-Key). Пустой = API для 1С закрыт.
ONEC_API_KEY = env("ONEC_API_KEY", default="")
# Максимум строк в одном пакете 1С (items). Превышение → 400.
ONEC_MAX_ITEMS = env.int("ONEC_MAX_ITEMS", default=1000)

# Feature-флаги. Инфраструктурные — здесь (через env, меняют разработчики).
# Бизнес-флаги (reviews/b2b/...) живут в SiteSettings. Проверка — через
# apps.core.features.is_enabled(); механизм поддерживает override любого флага
# через этот словарь.
FEATURES = {
    "crm": env.bool("FEATURE_CRM", default=False),
    "ai": env.bool("FEATURE_AI", default=False),
    "eventbus": env.bool("FEATURE_EVENTBUS", default=True),
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
