"""MAX Bot webhook endpoint.

Принимает POST от MAX, маршрутизирует по update_type в нужный handler.
Некорректные запросы отвергаются без утечки деталей.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .handlers import auth

logger = logging.getLogger(__name__)

_SEEN_TTL = 60


def _is_duplicate(event_id: str) -> bool:
    if not event_id:
        return False
    cache_key = f"max_seen:{event_id}"
    if cache.get(cache_key):
        return True
    cache.set(cache_key, True, timeout=_SEEN_TTL)
    return False


def _verify_webhook_secret(request) -> bool:
    secret = getattr(settings, "MAX_WEBHOOK_SECRET", "")
    if not secret:
        return True
    provided = request.headers.get("X-Max-Webhook-Secret", "")
    return provided == secret


def _send_reply(reply: dict | None) -> None:
    if not reply:
        return
    token = getattr(settings, "MAX_BOT_TOKEN", "")
    api_url = getattr(settings, "MAX_BOT_API_URL", "https://platform-api.max.ru")
    if not token:
        logger.warning("MAX_BOT_TOKEN not set, reply not sent")
        return
    import urllib.request

    req = urllib.request.Request(
        f"{api_url}/messages",
        data=json.dumps(reply).encode("utf-8"),
        headers={"Authorization": token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        logger.exception("Failed to send MAX reply to chat_id=%s", reply.get("chat_id"))


@csrf_exempt
@require_POST
def webhook(request):
    if not _verify_webhook_secret(request):
        return JsonResponse({"ok": False}, status=403)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False}, status=400)

    update_type = payload.get("update_type")
    if not update_type:
        return JsonResponse({"ok": False}, status=400)

    message = payload.get("message", {})
    body = message.get("body", {})
    mid = body.get("mid", "")
    event_id = f"{update_type}:{mid}" if mid else f"{payload.get('timestamp', '')}:{update_type}"
    if _is_duplicate(event_id):
        return JsonResponse({"ok": True})

    reply = _dispatch(update_type, payload)
    if reply:
        _send_reply(reply)

    return JsonResponse({"ok": True})


def _dispatch(update_type: str, payload: dict) -> dict | None:
    if update_type == "bot_started":
        chat_id = payload.get("chat_id")
        user_info = payload.get("user", {})
        if chat_id:
            return auth.handle_bot_started(chat_id, user_info)

    elif update_type == "message_created":
        message = payload.get("message", {})
        chat_id = message.get("recipient", {}).get("chat_id")
        if not chat_id:
            return None

        body = message.get("body", {})
        attachments = body.get("attachments", [])
        for att in attachments:
            if att.get("type") == "contact":
                return auth.handle_contact(chat_id, att.get("payload", {}))

        text = (body.get("text") or "").strip()
        if text and text.isdigit() and len(text) == auth.OTP_LENGTH:
            return auth.handle_otp_confirm(chat_id, text)

    return None
