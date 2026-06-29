"""Webhook endpoint для ЮKassa (#8)."""

import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services import handle_webhook, verify_webhook_signature

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def yookassa_webhook(request):
    """Принимает уведомления от ЮKassa. Идемпотентно."""
    # Kill-switch (#311): на стенде/проде оплата выключена, пока webhook не получит
    # нормальную аутентификацию. Без этого endpoint открыт на подделку «оплачено».
    if not getattr(settings, "PAYMENTS_ENABLED", True):
        return JsonResponse({"error": "payments disabled"}, status=503)

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
