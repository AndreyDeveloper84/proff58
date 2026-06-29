"""Сервис записи аналитических событий.

Единая точка входа — ``track()``. Перед записью:
- проверяется feature-флаг ``analytics``;
- из payload вычищаются поля с персональными / платёжными данными (PII).
"""

from __future__ import annotations

import logging
from typing import Any

from apps.core.features import is_enabled

from .models import AnalyticsEvent, EventType  # noqa: F401 — реэкспорт EventType

logger = logging.getLogger(__name__)

#: Ключи payload, содержащие PII / платёжные данные — удаляются перед записью.
_PII_KEYS = frozenset(
    {
        "phone",
        "email",
        "password",
        "card_number",
        "cvv",
        "token",
    }
)


def _strip_pii(data: dict[str, Any]) -> dict[str, Any]:
    """Вернуть копию *data* без ключей из ``_PII_KEYS`` (рекурсивно)."""
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if key in _PII_KEYS:
            continue
        if isinstance(value, dict):
            cleaned[key] = _strip_pii(value)
        else:
            cleaned[key] = value
    return cleaned


def track(
    event_type: str,
    *,
    user=None,
    session_id: str = "",
    payload: dict[str, Any] | None = None,
) -> AnalyticsEvent | None:
    """Записать аналитическое событие.

    Возвращает созданный ``AnalyticsEvent`` или ``None``, если аналитика
    отключена флагом.
    """
    if not is_enabled("analytics"):
        return None

    safe_payload = _strip_pii(payload) if payload else {}

    try:
        event = AnalyticsEvent.objects.create(
            event_type=event_type,
            user=user if user and getattr(user, "is_authenticated", False) else None,
            session_id=session_id or "",
            payload=safe_payload,
        )
        logger.debug("analytics.track: %s (id=%s)", event_type, event.pk)
        return event
    except Exception:
        logger.exception("analytics.track() failed for event=%s", event_type)
        return None
