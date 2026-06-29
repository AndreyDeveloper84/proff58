"""Webhook endpoint для ЮKassa (#8)."""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services import handle_webhook, verify_webhook_signature

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def yookassa_webhook(request):
    """Принимает уведомления от ЮKassa. Идемпотентно."""
    signature = request.headers.get("X-Yookassa-Signature", "")

    if not verify_webhook_signature(request.body, signature):
        return JsonResponse({"error": "invalid signature"}, status=403)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "invalid json"}, status=400)

    try:
        handle_webhook(payload)
    except Exception:
        logger.exception("YooKassa webhook processing error")

    return JsonResponse({"ok": True})
