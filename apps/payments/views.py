"""Webhook endpoint для ЮKassa (#8, #311).

Верификация подлинности — через перезапрос к API ЮKassa (services.verify_webhook).
Ошибка обработки → 500 (ЮKassa сделает retry).
"""

import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services import handle_webhook

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def yookassa_webhook(request):
    """Принимает уведомления от ЮKassa."""
    if not getattr(settings, "PAYMENTS_ENABLED", True):
        return JsonResponse({"error": "payments disabled"}, status=503)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "invalid json"}, status=400)

    try:
        handle_webhook(payload)
    except Exception:
        logger.exception("YooKassa webhook processing error")
        return JsonResponse({"error": "processing error"}, status=500)

    return JsonResponse({"ok": True})
