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
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.phone import normalize_phone

from .models import MaxAccount, MaxAuthAttempt, OrderTrackingGrant

logger = logging.getLogger(__name__)
User = get_user_model()

Operation = MaxAuthAttempt.Operation
Status = MaxAuthAttempt.Status


class MaxIntegrationUnavailable(RuntimeError):
    """MAX login cannot start because the bot is not configured."""


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


def _max_bot_username() -> str:
    bot_token = (getattr(settings, "MAX_BOT_TOKEN", "") or "").strip()
    username = (getattr(settings, "MAX_BOT_USERNAME", "") or "").strip().lstrip("@")
    if not bot_token or not username:
        # Не подставляем правдоподобную заглушку: QR и CTA с max.ru/bot внешне
        # выглядели рабочими, но MAX справедливо отклонял их как недействительные.
        raise MaxIntegrationUnavailable("MAX bot credentials are incomplete")
    return username


def build_deeplink(token: str) -> str:
    """Диплинк бота с одноразовым токеном (§11.1: только случайный id, без PII)."""
    username = _max_bot_username()
    return f"https://max.ru/{username}?start={token}"


def create_attempt(
    *, session_key: str, operation_type: str = Operation.LOGIN, user=None, order=None
) -> StartedAttempt:
    """Создать одноразовую попытку (§7.1). token = public_id.secret — уходит в диплинк.

    ``order`` — только для ``Operation.TRACK_ORDER`` (#520): привязка попытки к
    конкретному гостевому заказу, против телефона которого сверяется контакт из MAX.
    """
    secret = secrets.token_urlsafe(24)
    # Проверяем конфигурацию до INSERT, чтобы при выключенном/неполном MAX не
    # оставлять в БД заведомо бесполезные pending-попытки.
    _max_bot_username()
    # DRF-2740: прежние незавершённые попытки той же сессии и операции гаснут —
    # иначе после «Повторить» в чате два кода, и человек жжёт попытки старым.
    if session_key:
        from . import confirm as _confirm

        stale = MaxAuthAttempt.objects.filter(
            browser_session_key=session_key,
            operation_type=operation_type,
            status__in=(Status.PENDING, Status.CONFIRMATION_REQUIRED),
        )
        for old in stale:
            _confirm.drop_pending(old)  # отложенный телефон старой попытки — вслед за ней
        stale.update(status=Status.CANCELLED)
    attempt = MaxAuthAttempt.objects.create(
        secret_hash=_hash_secret(secret),
        browser_session_key=session_key or "",
        operation_type=operation_type,
        user=user,
        order=order,
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
    except (MaxAuthAttempt.DoesNotExist, ValueError, ValidationError):
        # ValidationError — от UUIDField на строке, которая не UUID: параметр
        # ``start`` диплинка задаёт кто угодно, и мусор в нём не должен ронять вебхук.
        return None
    return _refresh_expiry(attempt)


def load_valid_attempt(token: str) -> MaxAuthAttempt | None:
    """Загрузить попытку по токену и проверить секрет.

    Статус не проверяется: попытка может оказаться завершённой или истёкшей —
    решает вызывающий (вебхук на такую отвечает «ссылка не действует»).
    """
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
    if (
        attempt is None
        or not session_key
        or not secrets.compare_digest(attempt.browser_session_key, session_key)
    ):
        return None
    if attempt.status in (Status.PENDING, Status.CONFIRMATION_REQUIRED):
        attempt.status = Status.CANCELLED
        attempt.save(update_fields=["status"])
        from . import confirm as _confirm

        _confirm.drop_pending(attempt)  # отложенный телефон — вслед за попыткой
        _emit("max_auth_cancelled", attempt=str(attempt.public_id))
    return attempt


def _fail(attempt: MaxAuthAttempt, reason: str, *, force: bool = False) -> MaxAuthAttempt:
    """Закрыть попытку отказом.

    Попытку, которая уже ждёт код или завершена, обычный отказ не понижает: два
    события от MAX могут прийти одновременно, и второе не должно гасить попытку,
    по которой первое уже выдало код. ``force`` — для отказов самого контура кода
    (исчерпаны попытки, потерян кэш).
    """
    if attempt.status == Status.COMPLETED:
        return attempt
    if attempt.status == Status.CONFIRMATION_REQUIRED and not force:
        return attempt
    attempt.status = Status.FAILED
    attempt.failure_reason = reason
    attempt.completed_at = timezone.now()
    attempt.save(update_fields=["status", "failure_reason", "completed_at"])
    from . import confirm as _confirm

    _confirm.drop_pending(attempt)  # отложенный телефон не переживает попытку
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


def _notify_login(user, *, event: str) -> None:
    """«Выполнен вход на сайт» в чат владельца после ввода кода (DRF-2740): если код
    выманили, человек увидит чужой вход и успеет отключить MAX в кабинете."""
    from apps.notifications.services import create_notification

    transaction.on_commit(lambda: create_notification(user=user, event=event))


def _complete_track_order(
    attempt: MaxAuthAttempt, *, max_user_id: int, phone: str, chat_id: int | None
) -> MaxAuthAttempt:
    """Завершить track_order-попытку (#520): один грант — один заказ.

    Телефон, который MAX подтвердил HMAC-подписанным контактом, ДОЛЖЕН совпасть
    с ``customer_phone`` заказа — иначе жёсткий отказ без auto-claim и без
    раскрытия заказа (Security constraints тикета: phone mismatch не связывает
    заказ и не раскрывает его данные). Идемпотентно: повтор с тем же
    max_user_id обновляет тот же грант (``update_or_create``), не плодит дубли.
    """
    order = attempt.order
    if order is None:
        return _fail(attempt, "no_target_order")
    # TOCTOU-защита: заказ мог перестать быть гостевым между стартом попытки
    # (проверка в MaxTrackOrderStartView) и её завершением через webhook —
    # напр. владелец успел войти и claim_guest_orders() уже привязал заказ.
    if order.user_id is not None:
        return _fail(attempt, "order_already_claimed")
    if normalize_phone(order.customer_phone) != phone:
        return _fail(attempt, "phone_mismatch")

    _, created = OrderTrackingGrant.objects.update_or_create(
        order=order, defaults={"max_user_id": max_user_id, "chat_id": chat_id}
    )
    completed = _complete(attempt, None, max_user_id=max_user_id, chat_id=chat_id, is_new=created)
    # chat_id=0 — валидный id (см. resolve_active_chat_id ниже, #521): is not None,
    # не truthy-проверка.
    if chat_id is not None:
        transaction.on_commit(lambda: _send_order_tracking_snapshot(order, chat_id))
    return completed


def _send_order_tracking_snapshot(order, chat_id: int) -> None:
    """Разовое сообщение с текущим статусом сразу после выдачи гранта (Scope тикета
    #520: «отправить текущее состояние заказа один раз, будущие transitions — #516»).

    Через ``notifications.services.send()`` (не ``create_notification()`` — той
    нужен ``user`` для intent/preference-слоя, гостю без аккаунта он неприменим):
    получаем тот же outbox + Celery-доставку + retry/backoff/классификацию
    ошибок (#521) без дублирования этой инфраструктуры здесь.

    idempotency_key включает chat_id: если гость позже переподключит другой
    MAX-аккаунт к тому же заказу (грант перевыдан), новый чат должен получить
    своё «подключено» — ключ, завязанный только на order.pk, заблокировал бы
    это как «уже отправлено» первому чату.
    """
    from apps.notifications.services import send

    send(
        user=None,
        chat_id=chat_id,
        event="order_tracking_connected",
        payload={"order_number": order.order_number, "status_note": order.display_status},
        idempotency_key=f"track-order-connected-{order.pk}-{chat_id}",
    )


def resolve_tracking_grant_chat_id(order) -> int | None:
    """chat_id активного гранта отслеживания для гостевого заказа (#520), либо None.

    Аналог ``resolve_active_chat_id(user)`` для гостевой ветки — используется
    ресиверами заказов (#516), когда ``order.user is None``. ``values_list`` —
    не тянем лишние колонки/инстанс ради одного поля.
    """
    return OrderTrackingGrant.objects.filter(order=order).values_list("chat_id", flat=True).first()


@dataclass(frozen=True)
class Decision:
    """Что сделать с попыткой по данным из MAX — БЕЗ записи в БД (DRF-2740).

    Вызывается дважды: ботом как предпроверка (отказать сразу или выдать код) и
    при вводе кода как исполнение под блокировкой — состояние могло измениться.
    """

    ok: bool
    reason: str = ""
    #: login_linked | login_by_phone | register | link | reauth
    action: str = ""
    user_id: int | None = None

    @property
    def needs_phone(self) -> bool:
        return self.action in ("login_by_phone", "register", "link")


def decide(attempt: MaxAuthAttempt, *, max_user_id: int | None, phone: str | None) -> Decision:
    """Решение по операции попытки. ``phone`` — None, если контакт ещё не передан."""
    op = attempt.operation_type
    existing = (
        MaxAccount.objects.filter(max_user_id=max_user_id, is_active=True).first()
        if max_user_id
        else None
    )

    # --- Подтверждение личности из кабинета (DRF-2497) ---
    if op == Operation.CONFIRM_LOGIN:
        if existing is None or existing.user_id != attempt.user_id:
            return Decision(False, "reauth_mismatch")
        return Decision(True, action="reauth", user_id=existing.user_id)

    # --- Привязка из личного кабинета (§5.4) ---
    if op == Operation.LINK:
        target = attempt.user
        if target is None:
            return Decision(False, "no_target_user")
        if existing and existing.user_id != target.pk:
            return Decision(False, "max_linked_to_other")  # §10: MAX у другого аккаунта
        if MaxAccount.objects.filter(user=target).exclude(max_user_id=max_user_id).exists():
            return Decision(False, "user_has_other_max")
        target_phone = normalize_phone(target.phone or "")
        if not target_phone:
            # Регистрация по e-mail телефон не спрашивает: привязывать MAX не к чему.
            return Decision(False, "no_phone")
        if phone is None:
            return Decision(False, "need_contact")
        if target_phone != phone:
            return Decision(False, "phone_mismatch")
        return Decision(True, action="link", user_id=target.pk)

    # --- Отслеживание гостевого заказа (#520) ---
    if op == Operation.TRACK_ORDER:
        # Кода нет и входа нет: бот сверяет номер с заказом сам
        # (``complete_track_order_from_contact``). Привязанный MAX ничего не меняет —
        # иначе гость с привязкой получал бы код, который некуда ввести (ревью Б-2).
        return Decision(False, "need_contact")

    # --- Вход/регистрация (§5.1, §10) ---
    if existing:
        # MAX уже привязан → вход владельца привязки (повторный вход, §5.3).
        if not existing.user.is_active:
            return Decision(False, "inactive_account")
        return Decision(True, action="login_linked", user_id=existing.user_id)
    if phone is None:
        return Decision(False, "need_contact")
    user = User.objects.filter(phone=phone).first()
    if user is None:
        return Decision(True, action="register")
    if not user.is_active:
        return Decision(False, "inactive_account")
    # DRF-2735: номер в профиле — ещё не основание впускать. В аккаунт с паролем
    # телефон вписывается без проверки (``ChangePhoneView``). Поэтому:
    #   - неподтверждённый номер не даёт ни входа, ни привязки, ни флага;
    #   - аккаунт с паролем (и любой сотрудник) по номеру не привязывается вовсе:
    #     у него есть кабинет, MAX привязывают оттуда. Проверка номера — раньше
    #     проверки «другой MAX», чтобы владелец номера получил честный отказ.
    if not user.phone_verified:
        return Decision(False, "phone_unverified")
    if user.has_usable_password() or user.is_staff:
        return Decision(False, "password_account")
    if MaxAccount.objects.filter(user=user).exists():
        return Decision(False, "user_has_other_max")
    return Decision(True, action="login_by_phone", user_id=user.pk)


def execute(
    attempt: MaxAuthAttempt,
    *,
    max_user_id: int,
    chat_id: int | None,
    phone: str | None,
    profile: dict | None,
) -> MaxAuthAttempt:
    """Исполнить решение по попытке — после ввода верного кода, под блокировкой.

    Решение принимается заново по свежему состоянию: между выдачей кода и вводом
    MAX могли отвязать, номер — сменить. ``_upsert_account`` без повторной
    проверки молча перевесил бы чужую привязку.
    """
    profile = profile or {}
    decision = decide(attempt, max_user_id=max_user_id, phone=phone)
    if not decision.ok:
        return _fail(attempt, decision.reason, force=True)

    if decision.action == "reauth":
        user = User.objects.get(pk=decision.user_id)
        _notify_login(user, event="max_reauth")
        return _complete(attempt, user, max_user_id=max_user_id, chat_id=chat_id, is_new=False)
    if decision.action == "login_linked":
        if chat_id is not None:
            MaxAccount.objects.filter(max_user_id=max_user_id, is_active=True).update(
                chat_id=chat_id, last_login_at=timezone.now()
            )
        user = User.objects.get(pk=decision.user_id)
        _notify_login(user, event="max_login")
        return _complete(attempt, user, max_user_id=max_user_id, chat_id=chat_id, is_new=False)
    if decision.action == "register":
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

    user = User.objects.get(pk=decision.user_id)
    self_link = MaxAccount.objects.filter(max_user_id=max_user_id, user=user).exists()
    _upsert_account(user, max_user_id=max_user_id, phone=phone, chat_id=chat_id, profile=profile)
    if decision.action == "login_by_phone":
        _notify_login(user, event="max_login")
    return _complete(
        attempt,
        user,
        max_user_id=max_user_id,
        chat_id=chat_id,
        is_new=(decision.action == "link" and not self_link),
    )


@transaction.atomic
def complete_track_order_from_contact(
    attempt: MaxAuthAttempt, *, max_user_id: int, phone: str, chat_id: int | None = None
) -> MaxAuthAttempt:
    """Отслеживание гостевого заказа (#520) — единственная операция, которую бот
    завершает сам: гость не входит и ничего не привязывает, пересланная ссылка даёт
    чужому только уведомления о чужом заказе при совпадении номера. Идемпотентно."""
    if attempt.status == Status.COMPLETED:
        return attempt
    attempt = _refresh_expiry(attempt)
    if attempt.status != Status.PENDING:
        return _fail(attempt, "attempt_not_pending")
    if attempt.operation_type != Operation.TRACK_ORDER:
        return _fail(attempt, "attempt_not_pending")
    return _complete_track_order(attempt, max_user_id=max_user_id, phone=phone, chat_id=chat_id)


def unlink_max(user) -> bool:
    """Отключить привязку MAX в ЛК (§5.4). True — если была и удалена.

    #521: атомарно — delete() + cancel_active_for_user() либо оба, либо ничего;
    иначе сбой между ними оставил бы активные подписки «сообщить о поступлении»
    без привязки MAX (тихо не уведомят на fan-out, а должны были быть cancelled).
    """
    with transaction.atomic():
        acct = MaxAccount.objects.filter(user=user).first()
        if not acct:
            return False
        max_user_id = acct.max_user_id
        acct.delete()
        _emit("max_account_unlinked", max_user_id=max_user_id)
        # #517 AC: unlink не удаляет audit history подписок «сообщить о
        # поступлении», но активные без привязки MAX бессмысленны — переводим
        # явно в cancelled, а не оставляем зависший active.
        from apps.catalog.availability_subscriptions import cancel_active_for_user

        cancel_active_for_user(user)
    return True


def can_login_via_max(user) -> bool:
    """Может ли пользователь войти на сайт через MAX прямо сейчас.

    Нужна модулям входа (VK ID / Яндекс ID), чтобы не дать отвязать последний
    способ входа. Условия: активная привязка MAX И интеграция настроена
    (MAX_BOT_TOKEN + MAX_BOT_USERNAME — без них QR/диплинк входа не собрать).
    chat_id не требуется: для входа он не нужен, только для уведомлений.
    """
    if user is None or not getattr(user, "pk", None):
        return False
    try:
        _max_bot_username()
    except MaxIntegrationUnavailable:
        return False
    return MaxAccount.objects.filter(user=user, is_active=True).exists()


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
    падаем на legacy `User.max_chat_id` — его писал старый поток привязки по коду
    (удалён в DRF-2735). Только на чтение, для привязавшихся раньше: новый код
    туда не пишет.
    """
    if user is None or not getattr(user, "pk", None):
        return None
    chat_id = (
        MaxAccount.objects.filter(user=user, is_active=True, chat_id__isnull=False)
        .values_list("chat_id", flat=True)
        .first()
    )
    # #521: is not None, не truthy-проверка — chat_id=0 валиден и не должен
    # трактоваться как «нет привязки» с падением на legacy-fallback.
    if chat_id is not None:
        return chat_id
    return getattr(user, "max_chat_id", None)
