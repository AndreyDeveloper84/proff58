"""Сервисный слой авторизации через MAX (#492): жизненный цикл одноразовой попытки
и правила поиска/создания пользователя (§10).

Границы: HTTP-слой (views) и webhook вызывают только эти функции; вся доменная
логика (создание/привязка пользователя, статусы попытки, идемпотентность) — здесь.
Секрет из диплинка хранится только в виде sha256-хэша (в БД — не сырой секрет).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts.phone import normalize_phone

from .models import MaxAccount, MaxAuthAttempt

logger = logging.getLogger(__name__)
User = get_user_model()

Operation = MaxAuthAttempt.Operation
Status = MaxAuthAttempt.Status


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _emit(event: str, *, user=None, session_id: str = "", **params) -> None:
    """Аналитическое событие MAX-авторизации (§15): структурный лог + запись в
    apps.analytics (за фиче-флагом, PII фильтруется в track())."""
    payload = {k: v for k, v in params.items() if v is not None}
    logger.info("max_auth_event=%s %s", event, payload)
    try:
        from apps.analytics.services import track

        track(event, user=user, session_id=session_id, payload=payload)
    except Exception:  # аналитика не должна влиять на поток авторизации
        logger.debug("analytics track skipped for %s", event, exc_info=True)


@dataclass
class StartedAttempt:
    attempt: MaxAuthAttempt
    deeplink: str
    token: str


def build_deeplink(token: str) -> str:
    """Диплинк бота с одноразовым токеном (§11.1: только случайный id, без PII)."""
    username = getattr(settings, "MAX_BOT_USERNAME", "") or "bot"
    return f"https://max.ru/{username}?start={token}"


def create_attempt(
    *, session_key: str, operation_type: str = Operation.LOGIN, user=None
) -> StartedAttempt:
    """Создать одноразовую попытку (§7.1). token = public_id.secret — уходит в диплинк."""
    secret = secrets.token_urlsafe(24)
    attempt = MaxAuthAttempt.objects.create(
        secret_hash=_hash_secret(secret),
        browser_session_key=session_key or "",
        operation_type=operation_type,
        user=user,
        expires_at=timezone.now() + MaxAuthAttempt.default_ttl(),
    )
    token = f"{attempt.public_id.hex}.{secret}"
    _emit(
        "max_auth_started",
        attempt=str(attempt.public_id),
        operation_type=operation_type,
        is_new_user=None,
    )
    return StartedAttempt(attempt=attempt, deeplink=build_deeplink(token), token=token)


def parse_token(token: str) -> tuple[str, str] | None:
    """Разобрать токен диплинка на (public_id_hex, secret)."""
    if not token or "." not in token:
        return None
    public_hex, _, secret = token.partition(".")
    if not public_hex or not secret:
        return None
    return public_hex, secret


def _refresh_expiry(attempt: MaxAuthAttempt) -> MaxAuthAttempt:
    """Пометить истёкшую pending-попытку как expired (§11.3) — ленивое протухание."""
    if attempt.status in (Status.PENDING, Status.CONFIRMATION_REQUIRED) and attempt.is_expired:
        attempt.status = Status.EXPIRED
        attempt.save(update_fields=["status"])
    return attempt


def get_attempt(public_id_hex: str) -> MaxAuthAttempt | None:
    try:
        attempt = MaxAuthAttempt.objects.get(public_id=public_id_hex)
    except (MaxAuthAttempt.DoesNotExist, ValueError):
        return None
    return _refresh_expiry(attempt)


def load_valid_attempt(token: str) -> MaxAuthAttempt | None:
    """Загрузить активную (pending, не истёкшую) попытку по токену + проверить секрет."""
    parsed = parse_token(token)
    if not parsed:
        return None
    public_hex, secret = parsed
    attempt = get_attempt(public_hex)
    if attempt is None:
        return None
    if not secrets.compare_digest(attempt.secret_hash, _hash_secret(secret)):
        return None
    return attempt


def cancel_attempt(public_id_hex: str, *, session_key: str) -> MaxAuthAttempt | None:
    """Отмена попытки пользователем (§13). Только из создавшей браузер-сессии (§11.2)."""
    attempt = get_attempt(public_id_hex)
    if attempt is None or not secrets.compare_digest(
        attempt.browser_session_key, session_key or ""
    ):
        return None
    if attempt.status in (Status.PENDING, Status.CONFIRMATION_REQUIRED):
        attempt.status = Status.CANCELLED
        attempt.save(update_fields=["status"])
        _emit("max_auth_cancelled", attempt=str(attempt.public_id))
    return attempt


def _fail(attempt: MaxAuthAttempt, reason: str) -> MaxAuthAttempt:
    attempt.status = Status.FAILED
    attempt.failure_reason = reason
    attempt.completed_at = timezone.now()
    attempt.save(update_fields=["status", "failure_reason", "completed_at"])
    _emit(
        "max_auth_failed",
        user=attempt.user,
        attempt=str(attempt.public_id),
        operation_type=attempt.operation_type,
        failure_reason=reason,
    )
    return attempt


def _complete(attempt: MaxAuthAttempt, user, *, max_user_id: int, chat_id, is_new: bool):
    attempt.status = Status.COMPLETED
    attempt.user = user
    attempt.max_user_id = max_user_id
    attempt.chat_id = chat_id
    attempt.completed_at = timezone.now()
    attempt.save(update_fields=["status", "user", "max_user_id", "chat_id", "completed_at"])
    _emit(
        "max_auth_completed",
        user=user,
        attempt=str(attempt.public_id),
        operation_type=attempt.operation_type,
        is_new_user=is_new,
    )
    return attempt


def _upsert_account(user, *, max_user_id, phone, chat_id, profile: dict) -> MaxAccount:
    now = timezone.now()
    acct, created = MaxAccount.objects.update_or_create(
        max_user_id=max_user_id,
        defaults={
            "user": user,
            "chat_id": chat_id,
            "phone": phone,
            "first_name": profile.get("first_name", "") or "",
            "last_name": profile.get("last_name", "") or "",
            "username": profile.get("username", "") or "",
            "phone_verified_at": now,
            "last_login_at": now,
            "is_active": True,
        },
    )
    _emit("max_account_linked", max_user_id=max_user_id)
    if created:
        # #515: приветственное сервисное сообщение — только на реально новую
        # привязку (created=True), не на re-link/re-login существующей записи;
        # только после commit — до него resolve_active_chat_id() ничего не найдёт.
        transaction.on_commit(lambda: _notify_max_connected(user))
    return acct


def _notify_max_connected(user) -> None:
    from apps.notifications.services import create_notification

    create_notification(user=user, event="max_connected")


@transaction.atomic
def complete_from_contact(
    attempt: MaxAuthAttempt,
    *,
    max_user_id: int,
    phone: str,
    chat_id: int | None = None,
    profile: dict | None = None,
) -> MaxAuthAttempt:
    """Завершить попытку по переданному из MAX контакту (§10). Идемпотентно (§11.4).

    Правила:
      - MAX уже привязан (по max_user_id) → вход этого пользователя;
      - link: привязать к текущему пользователю, если телефон совпал и нет конфликта;
      - иначе поиск по телефону: не найден → создать (passwordless, verified);
        найден без привязки → привязать + вход; найден с другой привязкой → конфликт.
    """
    profile = profile or {}
    # Идемпотентность: повторная доставка того же контакта не пересоздаёт.
    if attempt.status == Status.COMPLETED:
        return attempt
    attempt = _refresh_expiry(attempt)
    if attempt.status != Status.PENDING:
        return _fail(attempt, "attempt_not_pending")

    phone = normalize_phone(phone)
    if not phone:
        return _fail(attempt, "bad_phone")

    existing = (
        MaxAccount.objects.select_related("user")
        .filter(max_user_id=max_user_id, is_active=True)
        .first()
    )

    # --- Привязка из личного кабинета (§5.4) ---
    if attempt.operation_type == Operation.LINK:
        target = attempt.user
        if target is None:
            return _fail(attempt, "no_target_user")
        if existing and existing.user_id != target.pk:
            return _fail(attempt, "max_linked_to_other")  # §10: MAX у другого аккаунта
        if MaxAccount.objects.filter(user=target).exclude(max_user_id=max_user_id).exists():
            return _fail(attempt, "user_has_other_max")
        if normalize_phone(target.phone) != phone:
            return _fail(attempt, "phone_mismatch")
        self_link = existing.user_id == target.pk if existing else False
        _upsert_account(
            target, max_user_id=max_user_id, phone=phone, chat_id=chat_id, profile=profile
        )
        return _complete(
            attempt, target, max_user_id=max_user_id, chat_id=chat_id, is_new=not self_link
        )

    # --- Вход/регистрация (§5.1, §10) ---
    if existing:
        # MAX уже привязан → просто вход владельца привязки (повторный вход, §5.3).
        if chat_id:
            MaxAccount.objects.filter(pk=existing.pk).update(
                chat_id=chat_id, last_login_at=timezone.now()
            )
        return _complete(
            attempt, existing.user, max_user_id=max_user_id, chat_id=chat_id, is_new=False
        )

    user = User.objects.filter(phone=phone).first()
    if user is None:
        # §10: пользователь не найден → создаём аккаунт (без пароля/e-mail), телефон подтверждён.
        user = User.objects.create_user(
            phone=phone,
            password=None,
            full_name=" ".join(filter(None, [profile.get("first_name"), profile.get("last_name")])),
            phone_verified=True,
        )
        _upsert_account(
            user, max_user_id=max_user_id, phone=phone, chat_id=chat_id, profile=profile
        )
        return _complete(attempt, user, max_user_id=max_user_id, chat_id=chat_id, is_new=True)

    # Пользователь найден по телефону.
    if MaxAccount.objects.filter(user=user).exists():
        # У аккаунта уже есть другая привязка MAX (max_user_id иной) → конфликт (§10).
        return _fail(attempt, "user_has_other_max")
    if not user.phone_verified:
        user.phone_verified = True
        user.save(update_fields=["phone_verified"])
    _upsert_account(user, max_user_id=max_user_id, phone=phone, chat_id=chat_id, profile=profile)
    return _complete(attempt, user, max_user_id=max_user_id, chat_id=chat_id, is_new=False)


@transaction.atomic
def complete_confirm(attempt: MaxAuthAttempt, *, max_user_id: int, chat_id: int | None = None):
    """Повторный вход уже привязанного пользователя без передачи номера (§5.3)."""
    if attempt.status == Status.COMPLETED:
        return attempt
    attempt = _refresh_expiry(attempt)
    if attempt.status != Status.PENDING:
        return _fail(attempt, "attempt_not_pending")
    acct = (
        MaxAccount.objects.select_related("user")
        .filter(max_user_id=max_user_id, is_active=True)
        .first()
    )
    if not acct:
        return _fail(attempt, "not_linked")
    if chat_id:
        MaxAccount.objects.filter(pk=acct.pk).update(chat_id=chat_id, last_login_at=timezone.now())
    return _complete(attempt, acct.user, max_user_id=max_user_id, chat_id=chat_id, is_new=False)


def unlink_max(user) -> bool:
    """Отключить привязку MAX в ЛК (§5.4). True — если была и удалена."""
    acct = MaxAccount.objects.filter(user=user).first()
    if not acct:
        return False
    max_user_id = acct.max_user_id
    acct.delete()
    _emit("max_account_unlinked", max_user_id=max_user_id)
    # #517 AC: unlink не удаляет audit history подписок «сообщить о поступлении»,
    # но активные без привязки MAX бессмысленны (тихо не уведомят на fan-out) —
    # переводим явно в cancelled, а не оставляем зависший active.
    from apps.catalog.availability_subscriptions import cancel_active_for_user

    cancel_active_for_user(user)
    return True


def has_active_max_account(user) -> bool:
    """Есть ли у пользователя каноническая активная привязка MAX (#517).

    В отличие от `resolve_active_chat_id` — без fallback на legacy
    `User.max_chat_id`: это проверка для НОВОЙ фичи (подписка на поступление),
    легаси-флоу сознательно не считается «активной привязкой» для неё.
    """
    if user is None or not getattr(user, "pk", None):
        return False
    return MaxAccount.objects.filter(user=user, is_active=True, chat_id__isnull=False).exists()


def resolve_active_chat_id(user) -> int | None:
    """Единственный canonical resolver MAX-получателя пользователя (#514).

    Источник истины — `MaxAccount(is_active=True, chat_id задан)`: так его
    поддерживают link/login/confirm/unlink. Если привязки через новый flow нет,
    временно падаем на legacy `User.max_chat_id` (старый OTP-бот-флоу,
    `handlers/auth.py`, задепрекейчен) — только на чтение, новый код туда не
    пишет (без двух независимых write-path).
    """
    if user is None or not getattr(user, "pk", None):
        return None
    chat_id = (
        MaxAccount.objects.filter(user=user, is_active=True, chat_id__isnull=False)
        .values_list("chat_id", flat=True)
        .first()
    )
    if chat_id:
        return chat_id
    return getattr(user, "max_chat_id", None)
