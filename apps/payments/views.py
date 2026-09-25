"""Приём уведомлений от касс.

ЮKassa (#8, #311): подлинность проверяется перезапросом объекта платежа к её API.

АТОЛ Pay: подписи у callback нет вовсе — уведомление это всего лишь сигнал
«сходи посмотри». Поэтому вход закрыт секретом в query (его касса возвращает из
``notificationUrl``, который мы сами задали при регистрации платежа), а состояние
строится по ответу ``GET /payments/{orderId}/status``, а не по телу запроса.

Ошибка обработки → 500: пусть касса повторит, чем мы потеряем оплату.
"""

import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .atolpay.service import handle_callback
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


@csrf_exempt
@require_POST
def atolpay_callback(request):
    """Принимает уведомления АТОЛ Pay (оплата, отмена, возврат, фискализация)."""
    if not getattr(settings, "PAYMENTS_ENABLED", True):
        return JsonResponse({"error": "payments disabled"}, status=503)

    expected = getattr(settings, "ATOLPAY_CALLBACK_TOKEN", "")
    # Пустой секрет — не «пускать всех», а «оплата не настроена»: открытый вход
    # позволил бы пометить чужой заказ оплаченным.
    if not expected or not constant_time_compare(request.GET.get("t", ""), expected):
        logger.warning("АТОЛ Pay callback с неверным секретом")
        return JsonResponse({"error": "forbidden"}, status=403)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "invalid json"}, status=400)

    try:
        handle_callback(payload)
    except Exception:
        logger.exception("АТОЛ Pay: ошибка обработки callback")
        return JsonResponse({"error": "processing error"}, status=500)

    return JsonResponse({"status": "success"})
