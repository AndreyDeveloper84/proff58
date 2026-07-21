"""MAX-канал доставки уведомлений.

Классификация ошибок провайдера (#521): retryable (429/5xx/сетевые/таймаут) vs
permanent (остальные 4xx) — вызывающий (tasks.py) решает, ретраить ли и с каким
backoff. Логи — только HTTP-код/класс ошибки, без chat_id/текста сообщения
(#521 AC: "без phone/chat id/token/message body в обычных логах").
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


class MaxProviderError(Exception):
    """Базовая ошибка отправки в MAX. `retry_after` — секунды из заголовка
    провайдера (429), если он его прислал."""

    def __init__(self, message: str, *, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class MaxRetryableError(MaxProviderError):
    """429/5xx/сеть/таймаут — временная проблема, повтор осмыслен."""


class MaxPermanentError(MaxProviderError):
    """4xx (кроме 429) — запрос сам по себе некорректен, повтор бессмыслен
    (напр. чат заблокировал бота, невалидный chat_id)."""


def is_available() -> bool:
    return bool(getattr(settings, "MAX_BOT_TOKEN", ""))


def _classify_http_error(exc: urllib.error.HTTPError) -> MaxProviderError:
    if exc.code == 429 or exc.code >= 500:
        retry_after = None
        header = exc.headers.get("Retry-After") if exc.headers else None
        if header:
            try:
                retry_after = int(header)
            except ValueError:
                retry_after = None
        return MaxRetryableError(f"HTTP {exc.code}", retry_after=retry_after)
    return MaxPermanentError(f"HTTP {exc.code}")


def send_message(chat_id: int, text: str, **kwargs) -> bool:
    """Отправить сообщение в MAX. Возвращает True при успехе.

    Поднимает MaxRetryableError/MaxPermanentError (классификация — #521) вместо
    generic Exception, чтобы вызывающий (tasks.py) мог решить, ретраить ли.
    """
    token = getattr(settings, "MAX_BOT_TOKEN", "")
    api_url = getattr(settings, "MAX_BOT_API_URL", "https://platform-api2.max.ru")
    if not token:
        raise MaxPermanentError("MAX_BOT_TOKEN not configured")

    body: dict = {"text": text}
    if kwargs.get("format"):
        body["format"] = kwargs["format"]
    if kwargs.get("attachments"):
        body["attachments"] = kwargs["attachments"]

    req = urllib.request.Request(
        f"{api_url}/messages?chat_id={chat_id}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as exc:
        classified = _classify_http_error(exc)
        logger.error("MAX send failed: HTTP %s (%s)", exc.code, type(classified).__name__)
        raise classified from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        logger.error("MAX send failed: network error (%s)", type(exc).__name__)
        raise MaxRetryableError(f"network error: {type(exc).__name__}") from exc
    except Exception:
        logger.exception("MAX send failed: unexpected error")
        raise
