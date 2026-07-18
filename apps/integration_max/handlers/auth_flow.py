"""Обработчики бота для потока «одноразовая попытка» (#492): старт по диплинку и
завершение попытки переданным контактом. Отделены от старого auth.py (совместимость).

Связь «какой контакт к какой попытке» держим в cache: при старте по диплинку
запоминаем chat_id → public_id, при получении контакта достаём попытку по chat_id.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

from .. import services
from ..models import MaxAccount
from ..verify import extract_phone_from_vcf, verify_contact_hash

logger = logging.getLogger(__name__)

_CHAT_ATTEMPT_TTL = 600  # чуть больше TTL попытки — на время диалога

_FAIL_TEXT = {
    "max_linked_to_other": "Этот MAX уже привязан к другому аккаунту. Войдите по номеру телефона.",
    "user_has_other_max": "К вашему аккаунту уже привязан другой MAX.",
    "phone_mismatch": "Номер MAX не совпадает с номером аккаунта.",
    "attempt_not_pending": "Ссылка недействительна или истекла. Начните вход заново.",
    "bad_phone": "Не удалось определить номер телефона.",
}
_SHARE_BUTTON = {
    "type": "inline_keyboard",
    "payload": {"buttons": [[{"type": "request_contact", "text": "Поделиться номером"}]]},
}


def _chat_key(chat_id: int) -> str:
    return f"max_attempt_chat:{chat_id}"


def handle_deeplink_start(chat_id: int, max_user_id: int | None, attempt) -> dict:
    """Старт бота по диплинку авторизации: запоминаем попытку, просим контакт.

    Если это повторный вход уже привязанного MAX (§5.3) — подтверждаем сразу,
    без запроса номера.
    """
    cache.set(_chat_key(chat_id), attempt.public_id.hex, _CHAT_ATTEMPT_TTL)
    if attempt.chat_id != chat_id:
        attempt.chat_id = chat_id
        attempt.save(update_fields=["chat_id"])

    if attempt.operation_type == services.Operation.LOGIN and max_user_id:
        linked = MaxAccount.objects.filter(max_user_id=max_user_id, is_active=True).exists()
        if linked:
            services.complete_confirm(attempt, max_user_id=max_user_id, chat_id=chat_id)
            cache.delete(_chat_key(chat_id))
            return {"chat_id": chat_id, "text": "Вход подтверждён. Вернитесь на сайт."}

    consent = (
        "Нажимая «Поделиться номером», вы разрешаете использовать номер телефона для "
        "регистрации, входа, оформления заказов и отправки сервисных уведомлений."
    )
    return {"chat_id": chat_id, "text": consent, "attachments": [_SHARE_BUTTON]}


def handle_attempt_contact(chat_id: int, contact_payload: dict, sender: dict | None) -> dict | None:
    """Контакт для активной попытки. None → нет попытки (передать в старый обработчик)."""
    public_hex = cache.get(_chat_key(chat_id))
    if not public_hex:
        return None
    attempt = services.get_attempt(public_hex)
    if attempt is None or attempt.status != services.Status.PENDING:
        return None

    token = getattr(settings, "MAX_BOT_TOKEN", "")
    vcf_info = contact_payload.get("vcf_info", "")
    received_hash = contact_payload.get("hash", "")
    # §11.5: номер подтверждён только штатной передачей контакта MAX (HMAC-подпись).
    if not verify_contact_hash(token, vcf_info, received_hash):
        logger.warning("MAX auth: HMAC verification failed")  # #521: без chat_id
        return {"chat_id": chat_id, "text": "Не удалось подтвердить номер. Попробуйте ещё раз."}

    phone = extract_phone_from_vcf(vcf_info)
    if not phone:
        return {"chat_id": chat_id, "text": _FAIL_TEXT["bad_phone"]}

    max_info = contact_payload.get("max_info") or {}
    max_user_id = max_info.get("user_id") or (sender or {}).get("user_id")
    profile = {
        "first_name": max_info.get("first_name") or (sender or {}).get("first_name"),
        "last_name": max_info.get("last_name") or (sender or {}).get("last_name"),
        "username": max_info.get("username") or (sender or {}).get("username"),
    }

    attempt = services.complete_from_contact(
        attempt, max_user_id=max_user_id, phone=phone, chat_id=chat_id, profile=profile
    )
    cache.delete(_chat_key(chat_id))

    if attempt.status == services.Status.COMPLETED:
        return {"chat_id": chat_id, "text": "Вход подтверждён. Вернитесь на сайт."}
    return {
        "chat_id": chat_id,
        "text": _FAIL_TEXT.get(attempt.failure_reason, "Не удалось подтвердить вход."),
    }
