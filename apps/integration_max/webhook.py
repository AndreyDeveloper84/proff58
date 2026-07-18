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
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import services
from .handlers import auth, auth_flow

logger = logging.getLogger(__name__)

_SEEN_TTL = 60
# #428 (M-04): верхняя граница тела webhook — защита от oversized payload.
_MAX_BODY_BYTES = 64 * 1024


def _is_duplicate(event_id: str) -> bool:
    if not event_id:
        return False
    cache_key = f"max_seen:{event_id}"
    if cache.get(cache_key):
        return True
    cache.set(cache_key, True, timeout=_SEEN_TTL)
    return False


def _verify_webhook_secret(request) -> bool:
    # #428 (M-04): fail-closed. Пустой секрет → webhook закрыт (а не «всё подлинно»).
    # Сравнение за константное время — без timing side-channel.
    secret = getattr(settings, "MAX_WEBHOOK_SECRET", "")
    if not secret:
        logger.error("MAX_WEBHOOK_SECRET не задан — webhook отклонён (fail-closed)")
        return False
    provided = request.headers.get("X-Max-Webhook-Secret", "")
    return constant_time_compare(provided, secret)


def _send_reply(reply: dict | None) -> None:
    if not reply:
        return
    token = getattr(settings, "MAX_BOT_TOKEN", "")
    api_url = getattr(settings, "MAX_BOT_API_URL", "https://platform-api.max.ru")
    if not token:
        logger.warning("MAX_BOT_TOKEN not set, reply not sent")
        return
    import urllib.request

    chat_id = reply.pop("chat_id", "")
    req = urllib.request.Request(
        f"{api_url}/messages?chat_id={chat_id}",
        data=json.dumps(reply).encode("utf-8"),
        headers={"Authorization": token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        # #521: без chat_id в логе — это ответ боту, идентификатор не нужен для
        # расследования (webhook сам по себе один на запрос).
        logger.exception("Failed to send MAX reply")


@csrf_exempt
@require_POST
def webhook(request):
    if not _verify_webhook_secret(request):
        return JsonResponse({"ok": False}, status=403)

    # #428 (M-04): отсекаем oversized payload до разбора JSON.
    if len(request.body) > _MAX_BODY_BYTES:
        logger.warning("MAX webhook: payload too large (%d bytes)", len(request.body))
        return JsonResponse({"ok": False}, status=413)

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
        if not chat_id:
            return None
        # #492: старт по диплинку авторизации несёт one-time token в payload/start_payload.
        token = payload.get("payload") or payload.get("start_payload") or ""
        if token:
            attempt = services.load_valid_attempt(token)
            if attempt is not None:
                return auth_flow.handle_deeplink_start(chat_id, user_info.get("user_id"), attempt)
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
                # #492: сначала пробуем завершить активную попытку авторизации;
                # если её нет — старый поток привязки по коду.
                res = auth_flow.handle_attempt_contact(
                    chat_id, att.get("payload", {}), message.get("sender", {})
                )
                if res is not None:
                    return res
                return auth.handle_contact(chat_id, att.get("payload", {}))

        text = (body.get("text") or "").strip()
        if text.lower() in ("/start", "start", "начать"):
            user_info = message.get("sender", {})
            return auth.handle_bot_started(chat_id, user_info)
        if text and text.isdigit() and len(text) == auth.OTP_LENGTH:
            return auth.handle_otp_confirm(chat_id, text)

    return None
