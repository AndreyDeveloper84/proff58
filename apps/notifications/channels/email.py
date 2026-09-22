"""E-mail-канал доставки уведомлений (DRF-2296).

Штатный SMTP Django (`django.core.mail`): любой провайдер даёт SMTP, отдельную
библиотеку не тянем. Настройки транспорта — `EMAIL_*` в `config/settings/base.py`
из окружения. Получатели — всегда аргумент, не настройка: тот же канал будет
слать письмо конкретному покупателю (сброс пароля, DRF-2298).

Классификация ошибок — в терминах `channels.RetryableChannelError` /
`PermanentChannelError`: задача отправки решает, ретраить ли. В логах — только
класс ошибки и код SMTP, без адресов и текста письма.
"""

from __future__ import annotations

import logging
import smtplib

from django.conf import settings
from django.core.mail import EmailMessage

from . import PermanentChannelError, RetryableChannelError

logger = logging.getLogger(__name__)

# Отказ получателя/отправителя, неверные учётные данные, отвергнутое тело письма:
# повтор с теми же данными даст тот же ответ.
_PERMANENT = (
    smtplib.SMTPAuthenticationError,
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPSenderRefused,
    smtplib.SMTPDataError,
    smtplib.SMTPNotSupportedError,
)


def is_configured() -> bool:
    """Транспорт задан: не-SMTP backend (console/locmem) или SMTP с хостом."""
    backend = getattr(settings, "EMAIL_BACKEND", "")
    if not backend.endswith("smtp.EmailBackend"):
        return True
    return bool(getattr(settings, "EMAIL_HOST", ""))


def send_email(subject: str, body: str, recipients: list[str]) -> None:
    """Отправить одно письмо. Поднимает Retryable/PermanentChannelError."""
    if not recipients:
        raise PermanentChannelError("Нет получателей")
    if not is_configured():
        raise PermanentChannelError("EMAIL_HOST не задан — транспорт не настроен")

    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=list(recipients),
    )
    try:
        message.send(fail_silently=False)
    except _PERMANENT as exc:
        logger.error("E-mail send failed permanently: %s", type(exc).__name__)
        raise PermanentChannelError(_describe(exc)) from exc
    except smtplib.SMTPResponseException as exc:
        # Остальные коды: 4xx — временный отказ сервера, 5xx без явного класса — постоянный.
        kind = RetryableChannelError if 400 <= exc.smtp_code < 500 else PermanentChannelError
        logger.error("E-mail send failed: %s (SMTP %s)", type(exc).__name__, exc.smtp_code)
        raise kind(_describe(exc)) from exc
    except (smtplib.SMTPException, OSError) as exc:
        # Разрыв соединения, отказ подключения, таймаут (TimeoutError ⊂ OSError), DNS — временно.
        logger.error("E-mail send failed transiently: %s", type(exc).__name__)
        raise RetryableChannelError(_describe(exc)) from exc


def _describe(exc: Exception) -> str:
    """Короткое описание для журнала: класс и SMTP-код, без адресов."""
    code = getattr(exc, "smtp_code", None)
    return f"{type(exc).__name__}" + (f" (SMTP {code})" if code else "")
