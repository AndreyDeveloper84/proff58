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
