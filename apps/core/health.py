"""Healthcheck endpoints for containers and external monitoring."""

from __future__ import annotations

import logging

import redis
from django.conf import settings
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def _check_database() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return "ok"


def _check_redis() -> str:
    client = redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2)
    try:
        client.ping()
    finally:
        client.close()
    return "ok"


def healthz(_request):
    """Return 200 only when Django, PostgreSQL, and Redis are reachable."""
    checks = {"status": "ok"}
    status_code = 200

    for name, check in (("db", _check_database), ("redis", _check_redis)):
        try:
            checks[name] = check()
        except Exception as exc:  # noqa: BLE001 - healthcheck must not leak tracebacks.
            logger.warning("Healthcheck failed for %s: %s", name, exc)
            checks[name] = "error"
            checks["status"] = "error"
            status_code = 503

    return JsonResponse(checks, status=status_code)
