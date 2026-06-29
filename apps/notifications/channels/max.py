"""MAX-канал доставки уведомлений."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def is_available() -> bool:
    return bool(getattr(settings, "MAX_BOT_TOKEN", ""))


def send_message(chat_id: int, text: str, **kwargs) -> bool:
    """Отправить сообщение в MAX. Возвращает True при успехе."""
    token = getattr(settings, "MAX_BOT_TOKEN", "")
    api_url = getattr(settings, "MAX_BOT_API_URL", "https://platform-api.max.ru")
    if not token:
        raise RuntimeError("MAX_BOT_TOKEN not configured")

    body: dict = {"chat_id": chat_id, "text": text}
    if kwargs.get("format"):
        body["format"] = kwargs["format"]
    if kwargs.get("attachments"):
        body["attachments"] = kwargs["attachments"]

    req = urllib.request.Request(
        f"{api_url}/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as exc:
        logger.error("MAX send failed: HTTP %s for chat_id=%s", exc.code, chat_id)
        raise
    except Exception:
        logger.exception("MAX send failed for chat_id=%s", chat_id)
        raise
