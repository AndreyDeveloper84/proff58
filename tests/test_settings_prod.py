"""Прод-настройки должны падать на старте при небезопасном SECRET_KEY (#8).

Если DJANGO_SECRET_KEY не задан или равен публичному дефолту из base, прод
поднялся бы с общеизвестным ключом → подделка session-cookie и подписанных
токенов. Здесь проверяем fail-fast при импорте config.settings.prod.
"""

import importlib
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured

INSECURE_DEFAULT = "insecure-change-me-in-prod"


def _load_prod():
    """Импортировать config.settings.prod заново под текущим окружением.

    base.py тоже выгружается из кеша, иначе ALLOWED_HOSTS (и другие env-переменные
    из base) берутся из первого импорта, игнорируя monkeypatch.setenv.
    """
    sys.modules.pop("config.settings.prod", None)
    sys.modules.pop("config.settings.base", None)
    return importlib.import_module("config.settings.prod")


def test_prod_fails_without_secret_key(monkeypatch):
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    with pytest.raises(ImproperlyConfigured):
        _load_prod()


def test_prod_rejects_insecure_default(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", INSECURE_DEFAULT)
    with pytest.raises(ImproperlyConfigured):
        _load_prod()


@pytest.mark.parametrize(
    "weak", ["change-me", "", "short-key", "INSECURE-abcdefghijklmnopqrstuvwxyz"]
)
def test_prod_rejects_placeholder_or_short_key(monkeypatch, weak):
    """T9: заглушка из .env.example, пустой или короткий ключ не запускают прод."""
    monkeypatch.setenv("DJANGO_SECRET_KEY", weak)
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "proff58.ru")
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        _load_prod()


def test_prod_accepts_real_secret_key(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "x7-real-strong-secret-please-rotate")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "proff58.ru")
    prod = _load_prod()
    assert prod.SECRET_KEY == "x7-real-strong-secret-please-rotate"


def test_prod_fails_without_allowed_hosts(monkeypatch):
    """Без публичного домена prod падает при старте (#282)."""
    monkeypatch.setenv("DJANGO_SECRET_KEY", "x7-real-strong-secret-please-rotate")
    monkeypatch.delenv("DJANGO_ALLOWED_HOSTS", raising=False)
    with pytest.raises(ImproperlyConfigured, match="публичного домена"):
        _load_prod()


def test_prod_fails_with_wildcard_hosts(monkeypatch):
    """Wildcard '*' в ALLOWED_HOSTS запрещён в проде (#282)."""
    monkeypatch.setenv("DJANGO_SECRET_KEY", "x7-real-strong-secret-please-rotate")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "*")
    with pytest.raises(ImproperlyConfigured, match="запрещено"):
        _load_prod()


# ═══════════ почта сотрудникам (DRF-2296) ═══════════


@pytest.fixture
def _prod_ok(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "x7-real-strong-secret-please-rotate")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "proff58.ru")
    monkeypatch.setenv("SITE_URL", "https://proff58.ru")
    monkeypatch.setenv("DEFAULT_FROM_EMAIL", "site@proff58.ru")
    for var in ("STAFF_NOTIFICATION_EMAILS", "EMAIL_HOST", "EMAIL_BACKEND", "EMAIL_USE_SSL"):
        monkeypatch.delenv(var, raising=False)


def test_prod_without_recipients_does_not_require_smtp(_prod_ok):
    assert _load_prod().STAFF_NOTIFICATION_EMAILS == []


def test_prod_fails_with_recipients_but_no_smtp_host(_prod_ok, monkeypatch):
    monkeypatch.setenv("STAFF_NOTIFICATION_EMAILS", "m@proff58.ru")
    with pytest.raises(ImproperlyConfigured, match="EMAIL_HOST"):
        _load_prod()


def test_prod_fails_with_recipients_but_default_sender(_prod_ok, monkeypatch):
    monkeypatch.setenv("STAFF_NOTIFICATION_EMAILS", "m@proff58.ru")
    monkeypatch.setenv("EMAIL_HOST", "smtp.example.com")
    monkeypatch.setenv("DEFAULT_FROM_EMAIL", "webmaster@localhost")
    with pytest.raises(ImproperlyConfigured, match="DEFAULT_FROM_EMAIL"):
        _load_prod()


def test_prod_fails_with_recipients_but_no_site_url(_prod_ok, monkeypatch):
    monkeypatch.setenv("STAFF_NOTIFICATION_EMAILS", "m@proff58.ru")
    monkeypatch.setenv("EMAIL_HOST", "smtp.example.com")
    monkeypatch.setenv("SITE_URL", "")
    with pytest.raises(ImproperlyConfigured, match="SITE_URL"):
        _load_prod()


def test_prod_accepts_console_backend_with_recipients(_prod_ok, monkeypatch):
    """Отладочный backend без SMTP-хоста допустим — падать должен только smtp без хоста."""
    monkeypatch.setenv("STAFF_NOTIFICATION_EMAILS", "m@proff58.ru")
    monkeypatch.setenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
    prod = _load_prod()
    assert prod.STAFF_NOTIFICATION_EMAILS == ["m@proff58.ru"]


def test_prod_rejects_tls_and_ssl_together(_prod_ok, monkeypatch):
    monkeypatch.setenv("EMAIL_USE_SSL", "True")
    with pytest.raises(ImproperlyConfigured, match="взаимоисключающие"):
        _load_prod()
