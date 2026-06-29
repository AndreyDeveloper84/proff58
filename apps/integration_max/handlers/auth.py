"""Обработчик авторизации через MAX: запрос контакта, привязка chat_id, OTP.

OTP и pending links хранятся в Django cache (Redis в проде, LocMem в dev).
"""

from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache

from ..verify import extract_phone_from_vcf, verify_contact_hash

logger = logging.getLogger(__name__)
User = get_user_model()

OTP_LENGTH = 4
OTP_TTL = 300
OTP_MAX_ATTEMPTS = 5


def generate_otp() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))


def handle_bot_started(chat_id: int, user_info: dict) -> dict | None:
    return {
        "chat_id": chat_id,
        "text": "Добро пожаловать в магазин «Профессионал»!\n\n"
        "Для привязки аккаунта поделитесь номером телефона:",
        "attachments": [
            {
                "type": "inline_keyboard",
                "payload": {"buttons": [[{"type": "request_contact", "text": "Отправить номер"}]]},
            }
        ],
    }


def handle_contact(chat_id: int, contact_payload: dict) -> dict | None:
    token = getattr(settings, "MAX_BOT_TOKEN", "")
    vcf_info = contact_payload.get("vcf_info", "")
    received_hash = contact_payload.get("hash", "")

    if not verify_contact_hash(token, vcf_info, received_hash):
        logger.warning("MAX contact: HMAC verification failed, chat_id=%s", chat_id)
        return {"chat_id": chat_id, "text": "Не удалось подтвердить номер. Попробуйте ещё раз."}

    phone = extract_phone_from_vcf(vcf_info)
    if not phone:
        return {"chat_id": chat_id, "text": "Не удалось определить номер телефона."}

    try:
        user = User.objects.get(phone=phone)
    except User.DoesNotExist:
        return {
            "chat_id": chat_id,
            "text": f"Аккаунт с номером {phone} не найден.\n"
            "Зарегистрируйтесь на сайте, затем вернитесь сюда.",
        }

    if getattr(user, "max_chat_id", None) == chat_id:
        return {
            "chat_id": chat_id,
            "text": "Ваш аккаунт уже привязан! Вы будете получать уведомления о заказах.",
        }

    otp = generate_otp()
    cache.set(
        f"max_otp:{chat_id}", {"otp": otp, "user_id": user.pk, "attempts": 0}, timeout=OTP_TTL
    )

    return {
        "chat_id": chat_id,
        "text": f"Для подтверждения привязки введите код **{otp}** на сайте "
        "или скопируйте его кнопкой ниже:",
        "format": "markdown",
        "attachments": [
            {
                "type": "inline_keyboard",
                "payload": {
                    "buttons": [[{"type": "clipboard", "text": "Скопировать код", "payload": otp}]]
                },
            }
        ],
    }


def handle_otp_confirm(chat_id: int, otp: str) -> dict | None:
    cache_key = f"max_otp:{chat_id}"
    pending = cache.get(cache_key)
    if not pending:
        return {"chat_id": chat_id, "text": "Нет ожидающей привязки. Нажмите /start чтобы начать."}

    attempts = pending.get("attempts", 0)
    if attempts >= OTP_MAX_ATTEMPTS:
        cache.delete(cache_key)
        return {"chat_id": chat_id, "text": "Превышено число попыток. Начните заново: /start"}

    if not secrets.compare_digest(otp.strip(), pending["otp"]):
        pending["attempts"] = attempts + 1
        cache.set(cache_key, pending, timeout=OTP_TTL)
        return {"chat_id": chat_id, "text": "Неверный код. Попробуйте ещё раз."}

    try:
        user = User.objects.get(pk=pending["user_id"])
    except User.DoesNotExist:
        cache.delete(cache_key)
        return {"chat_id": chat_id, "text": "Пользователь не найден."}

    User.objects.filter(pk=user.pk).update(max_chat_id=chat_id)
    cache.delete(cache_key)

    logger.info("MAX auth: linked chat_id=%s to user=%s", chat_id, user.pk)
    return {
        "chat_id": chat_id,
        "text": f"Аккаунт {user.phone} успешно привязан!\n"
        "Вы будете получать уведомления о заказах в этом чате.",
    }
