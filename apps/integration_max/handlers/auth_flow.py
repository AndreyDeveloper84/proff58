"""Обработчики бота для потока «одноразовая попытка» (#492): старт по диплинку и
контакт. Ответы бота вне попытки — в auth.py.

С DRF-2740 бот попытку не завершает (кроме отслеживания заказа): он проверяет
данные, выдаёт шестизначный код и просит ввести его на сайте. Завершает попытку
``api.views.MaxAuthConfirmView`` — в том браузере, где код введён. Пересланная
ссылка сама по себе больше ничего не даёт.

Связь «какой контакт к какой попытке» держим в cache: при старте по диплинку
запоминаем chat_id → public_id, при получении контакта достаём попытку по chat_id.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

from .. import confirm, services
from ..verify import extract_phone_from_vcf, verify_contact_hash

logger = logging.getLogger(__name__)

_CHAT_ATTEMPT_TTL = 15 * 60  # не меньше HARD_TTL попытки — на время диалога с кодом

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
    "code_reissue_limit": ("Код уже выдавался несколько раз. Вернитесь на сайт и начните заново."),
    "inactive_account": "Аккаунт с этим номером заблокирован. Свяжитесь с магазином.",
    "no_max_user": "Не удалось определить ваш аккаунт MAX. Вернитесь на сайт и начните заново.",
    "foreign_contact": (
        "Это контакт другого человека. Поделитесь своим номером кнопкой "
        "«Поделиться номером» — и начните вход на сайте заново."
    ),
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

#: Ссылку открыл другой MAX, чем тот, кому уже выдан код.
FOREIGN_MAX_TEXT = (
    "Эта ссылка уже использована в другом аккаунте MAX. Если вход начинали вы — "
    "вернитесь на сайт и нажмите кнопку ещё раз."
)
#: Контакт прислали, когда код уже выдан.
CODE_ALREADY_SENT_TEXT = (
    "Код уже отправлен выше — введите его на сайте. Нужен новый код — нажмите «Начать» " "ещё раз."
)
#: Код набрали в чат бота.
CODE_GOES_TO_SITE_TEXT = (
    "Код вводится не здесь, а на сайте — на той странице, с которой вы начали вход. "
    "Никому его не сообщайте."
)


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


def _code_message(chat_id: int, attempt, code: str) -> dict:
    """Сообщение с кодом. Предупреждение — первой строкой: превью пуша показывает начало."""
    op = attempt.operation_type
    if op == services.Operation.LINK and attempt.user is not None:
        what = (
            f"Код подключает этот MAX к аккаунту {account_label(attempt.user)} на proff58.ru — "
            "его владелец сможет входить от вашего имени и видеть ваши заказы."
        )
    elif op == services.Operation.CONFIRM_LOGIN:
        what = (
            "Код подтверждает действие в личном кабинете на proff58.ru: удаление аккаунта, "
            "смену e-mail или подключение способа входа."
        )
    else:
        what = "Кто введёт этот код на proff58.ru, войдёт в ваш аккаунт."
    text = (
        f"Никому не сообщайте этот код — ни сотруднику магазина, ни доставке, ни по телефону. "
        f"{what}\n\n"
        f"Код: {code}\n\n"
        "Введите его на сайте — на той странице, с которой начали. Если вы только что не "
        "нажимали кнопку на сайте, вас обманывают: ничего не делайте.\n"
        "Нет поля для кода — обновите страницу и начните заново."
    )
    return {
        "chat_id": chat_id,
        "text": text,
        "attachments": [
            {
                "type": "inline_keyboard",
                "payload": {
                    "buttons": [[{"type": "clipboard", "text": "Скопировать код", "payload": code}]]
                },
            }
        ],
    }


def _issue_and_reply(chat_id: int, attempt, *, max_user_id, pending: dict | None) -> dict:
    if not max_user_id:
        # Без личности MAX код выдавать не на кого: ``issue_code`` зафиксировал бы None,
        # и следующий стартовавший стал бы «тем же» MAX.
        services._fail(attempt, "no_max_user")
        return _fail_reply(chat_id, attempt, "no_max_user")
    issued = confirm.issue_code(attempt, max_user_id=max_user_id, chat_id=chat_id, pending=pending)
    if issued.code is not None:
        return _code_message(chat_id, issued.attempt, issued.code)
    if issued.reason == "foreign_max":
        return {"chat_id": chat_id, "text": FOREIGN_MAX_TEXT}
    return {
        "chat_id": chat_id,
        "text": _FAIL_TEXT.get(issued.reason, _FAIL_TEXT["attempt_not_pending"]),
    }


def _fail_reply(chat_id: int, attempt, reason: str) -> dict:
    if attempt.operation_type == services.Operation.LINK:
        text = _LINK_FAIL_TEXT.get(reason) or _FAIL_TEXT.get(reason, "Не удалось подключить MAX.")
    else:
        text = _FAIL_TEXT.get(reason, "Не удалось подтвердить вход.")
    return {"chat_id": chat_id, "text": text}


def handle_deeplink_start(chat_id: int, max_user_id: int | None, attempt) -> dict:
    """Старт бота по диплинку: проверить, что можно сделать, и либо выдать код,
    либо попросить контакт, либо отказать.

    Попытка уже ждёт код (повторное «Начать»): тому же MAX — перевыпуск, другому —
    отказ, попытка не трогается.
    """
    if attempt.status == services.Status.CONFIRMATION_REQUIRED:
        return _issue_and_reply(chat_id, attempt, max_user_id=max_user_id, pending=None)

    cache.set(_chat_key(chat_id), attempt.public_id.hex, _CHAT_ATTEMPT_TTL)
    if attempt.chat_id != chat_id:
        attempt.chat_id = chat_id
        attempt.save(update_fields=["chat_id"])

    if attempt.operation_type == services.Operation.TRACK_ORDER:
        # #520: гость не регистрируется и не входит — только сверка номера с заказом,
        # кода нет даже у покупателя с привязанным MAX (иначе его некуда вводить).
        consent = (
            "Нажимая «Поделиться номером», вы разрешаете сверить его с номером заказа "
            "и присылать уведомления о статусе именно этого заказа."
        )
        return {"chat_id": chat_id, "text": consent, "attachments": [_SHARE_BUTTON]}

    decision = services.decide(attempt, max_user_id=max_user_id, phone=None)
    if decision.ok:
        # Привязанный MAX или подтверждение из кабинета: контакт не нужен, сразу код.
        cache.delete(_chat_key(chat_id))
        return _issue_and_reply(chat_id, attempt, max_user_id=max_user_id, pending={})
    if decision.reason != "need_contact":
        services._fail(attempt, decision.reason)
        cache.delete(_chat_key(chat_id))
        return _fail_reply(chat_id, attempt, decision.reason)

    if attempt.operation_type == services.Operation.LINK and attempt.user is not None:
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
            "для входа, оформления заказов и отправки сервисных уведомлений. После этого "
            "бот пришлёт код для ввода на сайте."
        )
    else:
        consent = (
            "Нажимая «Поделиться номером», вы разрешаете использовать номер телефона для "
            "регистрации, входа, оформления заказов и отправки сервисных уведомлений. "
            "После этого бот пришлёт код для ввода на сайте."
        )
    return {"chat_id": chat_id, "text": consent, "attachments": [_SHARE_BUTTON]}


def handle_attempt_contact(chat_id: int, contact_payload: dict, sender: dict | None) -> dict | None:
    """Контакт для активной попытки. None → живой попытки нет (ответит ``auth.handle_contact``)."""
    public_hex = cache.get(_chat_key(chat_id))
    if not public_hex:
        return None
    attempt = services.get_attempt(public_hex)
    if attempt is None:
        return None
    if attempt.status == services.Status.CONFIRMATION_REQUIRED:
        return {"chat_id": chat_id, "text": CODE_ALREADY_SENT_TEXT}
    if attempt.status != services.Status.PENDING:
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
    # Личность — тот, кто в чате (sender). ``max_info`` описывает владельца контакта:
    # для своего номера он тот же человек, а чужой контакт из книжки — другой, и
    # по нему код выдавать нельзя: номер подтверждал бы не его хозяин.
    sender_id = (sender or {}).get("user_id")
    max_user_id = sender_id or max_info.get("user_id")
    if sender_id and max_info.get("user_id") and max_info["user_id"] != sender_id:
        cache.delete(_chat_key(chat_id))
        services._fail(attempt, "foreign_contact")
        return _fail_reply(chat_id, attempt, "foreign_contact")
    profile = {
        "first_name": max_info.get("first_name") or (sender or {}).get("first_name"),
        "last_name": max_info.get("last_name") or (sender or {}).get("last_name"),
        "username": max_info.get("username") or (sender or {}).get("username"),
    }

    if attempt.operation_type == services.Operation.TRACK_ORDER:
        attempt = services.complete_track_order_from_contact(
            attempt, max_user_id=max_user_id, phone=phone, chat_id=chat_id
        )
        cache.delete(_chat_key(chat_id))
        if attempt.status == services.Status.COMPLETED:
            return {"chat_id": chat_id, "text": "Отслеживание подключено. Вернитесь на сайт."}
        text = _TRACK_ORDER_FAIL_TEXT.get(attempt.failure_reason, _TRACK_ORDER_FAIL_FALLBACK)
        return {"chat_id": chat_id, "text": text}

    decision = services.decide(attempt, max_user_id=max_user_id, phone=phone)
    cache.delete(_chat_key(chat_id))
    if not decision.ok:
        services._fail(attempt, decision.reason)
        return _fail_reply(chat_id, attempt, decision.reason)
    # Телефон и профиль — в кэш до ввода кода: в БД до подтверждения они не попадают.
    return _issue_and_reply(
        chat_id, attempt, max_user_id=max_user_id, pending={"phone": phone, "profile": profile}
    )
