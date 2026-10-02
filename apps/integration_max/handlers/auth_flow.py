"""Обработчики бота для потока «одноразовая попытка» (#492): старт по диплинку и
завершение попытки переданным контактом. Ответы бота вне попытки — в auth.py.

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

_LINK_IN_ACCOUNT = (
    "Войдите на сайте по e-mail и паролю и подключите MAX в личном кабинете: "
    "блок «Вход через MAX» → «Подключить MAX»."
)
_FAIL_TEXT = {
    "max_linked_to_other": (
        "Этот MAX уже подключён к другому аккаунту на сайте. Чтобы подключить его "
        "сюда, сначала отключите MAX в том аккаунте."
    ),
    "user_has_other_max": "К аккаунту с этим номером уже подключён другой MAX.",
    "phone_mismatch": (
        "Номер этого MAX не совпадает с номером в профиле на сайте. Укажите в "
        "профиле номер этого MAX и повторите."
    ),
    "no_phone": (
        "В профиле на сайте не указан номер телефона. Укажите в профиле номер "
        "этого MAX и повторите подключение."
    ),
    # DRF-2735: номер вписан в аккаунт без проверки — по нему не впускаем.
    "phone_unverified": (
        "Этот номер указан в аккаунте на сайте, но не подтверждён, поэтому войти "
        f"по нему нельзя. {_LINK_IN_ACCOUNT} Если аккаунт не ваш — свяжитесь с магазином."
    ),
    "password_account": f"У аккаунта с этим номером вход по паролю. {_LINK_IN_ACCOUNT}",
    "attempt_not_pending": "Ссылка недействительна или истекла. Начните вход заново.",
    "bad_phone": "Не удалось определить номер телефона.",
    "reauth_mismatch": "Этот MAX не привязан к аккаунту, из которого вы подтверждаете действие.",
}
# Привязка из кабинета: аккаунт известен заранее, и эта проверка идёт ДО сверки
# номера — «аккаунт с этим номером» здесь было бы неправдой.
_LINK_FAIL_TEXT = {
    "user_has_other_max": (
        "К этому аккаунту уже подключён другой MAX. Сначала отключите его в личном "
        "кабинете на сайте."
    ),
}
# #520: track_order — гость без аккаунта, общие тексты выше про «аккаунт» не подходят.
_TRACK_ORDER_FAIL_TEXT = {
    "phone_mismatch": "Номер MAX не совпадает с номером заказа.",
    "no_target_order": "Заказ не найден. Откройте ссылку «Отслеживать в MAX» на странице заказа заново.",
    "order_already_claimed": "Заказ уже привязан к аккаунту — отслеживание через MAX недоступно.",
    "attempt_not_pending": "Ссылка недействительна или истекла. Начните заново со страницы заказа.",
    "bad_phone": "Не удалось определить номер телефона.",
}
_TRACK_ORDER_FAIL_FALLBACK = "Не удалось подключить отслеживание заказа."
_SHARE_BUTTON = {
    "type": "inline_keyboard",
    "payload": {"buttons": [[{"type": "request_contact", "text": "Поделиться номером"}]]},
}


def _chat_key(chat_id: int) -> str:
    return f"max_attempt_chat:{chat_id}"


def account_label(user) -> str:
    """Как назвать аккаунт в сообщении бота, не раскрывая его целиком.

    Привязку начинает тот, кто вошёл в аккаунт на сайте, а подтверждает тот, кто
    открыл ссылку в MAX, — и это может быть другой человек, которому ссылку
    прислали. Подпись даёт ему шанс заметить, что аккаунт не его.
    """
    email = (getattr(user, "email", "") or "").strip()
    if "@" in email:
        name, _, domain = email.partition("@")
        return f"{name[:1]}•••@{domain}"
    phone = (getattr(user, "phone", "") or "").strip()
    if len(phone) >= 4:
        return f"с номером •••{phone[-4:]}"
    return "без e-mail"


def handle_deeplink_start(chat_id: int, max_user_id: int | None, attempt) -> dict:
    """Старт бота по диплинку авторизации: запоминаем попытку, просим контакт.

    Если это повторный вход уже привязанного MAX (§5.3) — подтверждаем сразу,
    без запроса номера.
    """
    if attempt.operation_type == services.Operation.CONFIRM_LOGIN:
        # DRF-2497: подтверждение из кабинета — только привязанным MAX, контакт не
        # просим и попытку за чатом не запоминаем (присланный следом номер не должен
        # до неё дойти).
        attempt = services.complete_reauth(attempt, max_user_id=max_user_id, chat_id=chat_id)
        if attempt.status == services.Status.COMPLETED:
            return {"chat_id": chat_id, "text": "Подтверждено. Вернитесь на сайт."}
        return {
            "chat_id": chat_id,
            "text": _FAIL_TEXT.get(attempt.failure_reason, "Не удалось подтвердить."),
        }

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

    if attempt.operation_type == services.Operation.TRACK_ORDER:
        # #520: гость не регистрируется и не входит — только сверка номера с заказом.
        consent = (
            "Нажимая «Поделиться номером», вы разрешаете сверить его с номером заказа "
            "и присылать уведомления о статусе именно этого заказа."
        )
    elif attempt.operation_type == services.Operation.LINK and attempt.user is not None:
        # DRF-2735: привязку начинают в кабинете, а ссылку на бота можно переслать
        # другому человеку. Называем аккаунт: поделившись номером, человек привяжет
        # СВОЙ MAX к нему и дальше будет входить через MAX именно туда.
        consent = (
            f"Вы подключаете этот MAX к аккаунту {account_label(attempt.user)} на сайте "
            "магазина «Профессионал». После этого вход через MAX будет вести в этот "
            "аккаунт.\n\n"
            "Если вы не нажимали «Подключить MAX» в своём личном кабинете — не делитесь "
            "номером: ссылку вам прислал кто-то другой.\n\n"
            "Нажимая «Поделиться номером», вы разрешаете использовать номер телефона "
            "для входа, оформления заказов и отправки сервисных уведомлений."
        )
    else:
        consent = (
            "Нажимая «Поделиться номером», вы разрешаете использовать номер телефона для "
            "регистрации, входа, оформления заказов и отправки сервисных уведомлений."
        )
    return {"chat_id": chat_id, "text": consent, "attachments": [_SHARE_BUTTON]}


def handle_attempt_contact(chat_id: int, contact_payload: dict, sender: dict | None) -> dict | None:
    """Контакт для активной попытки. None → живой попытки нет (ответит ``auth.handle_contact``)."""
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
    is_track_order = attempt.operation_type == services.Operation.TRACK_ORDER

    if attempt.status == services.Status.COMPLETED:
        if is_track_order:
            text = "Отслеживание подключено. Вернитесь на сайт."
        elif attempt.operation_type == services.Operation.LINK and attempt.user is not None:
            text = f"MAX подключён к аккаунту {account_label(attempt.user)}. " "Вернитесь на сайт."
        else:
            text = "Вход подтверждён. Вернитесь на сайт."
        return {"chat_id": chat_id, "text": text}
    if is_track_order:
        text = _TRACK_ORDER_FAIL_TEXT.get(attempt.failure_reason, _TRACK_ORDER_FAIL_FALLBACK)
    elif attempt.operation_type == services.Operation.LINK:
        text = _LINK_FAIL_TEXT.get(attempt.failure_reason) or _FAIL_TEXT.get(
            attempt.failure_reason, "Не удалось подключить MAX."
        )
    else:
        text = _FAIL_TEXT.get(attempt.failure_reason, "Не удалось подтвердить вход.")
    return {"chat_id": chat_id, "text": text}
