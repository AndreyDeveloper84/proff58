"""Настройки для продакшн-окружения."""

from .base import *  # noqa: F401,F403
from .base import ALLOWED_HOSTS, env

DEBUG = False

# Для входа в админку за nginx/HTTPS Django требует доверенные origin-ы.
_public_hosts = [h for h in ALLOWED_HOSTS if h not in ("*", "localhost", "127.0.0.1")]
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in _public_hosts] + [
    f"http://{h}" for h in _public_hosts
]

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
