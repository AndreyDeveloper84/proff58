"""Код подтверждения входа через MAX вводится на сайте (DRF-2740).

Раньше попытку завершал бот: нажал «Начать» или поделился номером — и браузер,
создавший попытку, получал сессию. Ссылку же можно переслать кому угодно: мошенник
создавал попытку у себя, слал ссылку покупателю, тот нажимал «Начать» — и мошенник
оказывался в его кабинете. Теперь бот только выдаёт **шестизначный код**, а
завершает попытку тот браузер, в котором этот код введут. Чтобы код сработал в
чужом браузере, его должен продиктовать сам покупатель — как с кодом из SMS.

Что хранится где:

- на попытке в БД — HMAC-хэш кода, счётчики выдач и неверных вводов, ``max_user_id``
  того, кто стартовал первым (другой MAX той же ссылки код не получит);
- телефон и профиль MAX до ввода кода — в кэше под ``public_id`` с TTL попытки: это
  ПДн человека, который с магазином, возможно, никаких отношений не имеет; в БД
  они не попадают, пока код не введён;
- сам код — нигде: ни в БД, ни в логах, ни в аналитике.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import MaxAuthAttempt

Status = MaxAuthAttempt.Status
Operation = MaxAuthAttempt.Operation

#: Шесть цифр и пять попыток: 1 шанс из 200 000 перебрать код из браузера попытки.
#: Четыре цифры давали 1 из 2000 — при рассылке ссылок это рабочая атака.
CODE_LENGTH = 6
MAX_FAILURES = 5
#: Перевыпуск кода (повторное «Начать» тем же MAX): код мог не дойти.
MAX_ISSUES = 3
CODE_TTL = timedelta(minutes=5)
#: Дальше этого срока от создания попытка не живёт, сколько бы кодов ни выдали.
HARD_TTL = timedelta(minutes=15)

_PENDING_KEY = "max_pending:{hex}"
_PENDING_LOST = object()
_HMAC_SALT = "integration_max.confirm_code"


def _hash(public_hex: str, code: str) -> str:
    return salted_hmac(_HMAC_SALT, f"{public_hex}:{code}").hexdigest()


def pending_key(attempt: MaxAuthAttempt) -> str:
    return _PENDING_KEY.format(hex=attempt.public_id.hex)


def load_pending(attempt: MaxAuthAttempt) -> dict | None:
    return cache.get(pending_key(attempt))


def drop_pending(attempt: MaxAuthAttempt) -> None:
    cache.delete(pending_key(attempt))


@dataclass(frozen=True)
class Issued:
    attempt: MaxAuthAttempt
    #: None — код не выдан (попытка закрыта, чужой MAX, исчерпаны перевыпуски).
    code: str | None
    reason: str = ""


def issue_code(
    attempt: MaxAuthAttempt, *, max_user_id: int, chat_id: int | None, pending: dict | None
) -> Issued:
    """Перевести попытку в «ждём код» и выдать код. Идемпотентно по статусу.

    Личность фиксирует первый стартовавший: ``max_user_id`` пишется один раз, и
    другой MAX по той же ссылке код не получает — иначе подглядевший QR подменил бы
    отложенную личность, а покупатель своим кодом вошёл бы в чужой аккаунт.
    """
    from . import services

    with transaction.atomic():
        attempt = MaxAuthAttempt.objects.select_for_update().get(pk=attempt.pk)
        attempt = services._refresh_expiry(attempt)
        if attempt.status not in (Status.PENDING, Status.CONFIRMATION_REQUIRED):
            return Issued(attempt, None, "attempt_not_pending")
        if attempt.status == Status.CONFIRMATION_REQUIRED and attempt.max_user_id != max_user_id:
            return Issued(attempt, None, "foreign_max")
        if attempt.code_issues >= MAX_ISSUES:
            return Issued(
                services._fail(attempt, "code_reissue_limit", force=True),
                None,
                "code_reissue_limit",
            )

        code = f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"
        now = timezone.now()
        attempt.status = Status.CONFIRMATION_REQUIRED
        attempt.max_user_id = max_user_id
        attempt.chat_id = chat_id
        attempt.confirm_code_hash = _hash(attempt.public_id.hex, code)
        attempt.code_issues += 1
        attempt.code_issued_at = now
        attempt.expires_at = min(now + CODE_TTL, attempt.created_at + HARD_TTL)
        attempt.save(
            update_fields=[
                "status",
                "max_user_id",
                "chat_id",
                "confirm_code_hash",
                "code_issues",
                "code_issued_at",
                "expires_at",
            ]
        )
        ttl = max(1, int((attempt.expires_at - now).total_seconds()))
        if pending is None:
            # Перевыпуск (повторное «Начать»): телефон уже в кэше — только продлить.
            # Записать пустой словарь нельзя: верный код тогда упёрся бы в
            # ``need_contact`` и попытка ушла бы в FAILED (ревью Б-1). Кэш потерян —
            # не трогаем: ввод кода честно ответит ``pending_lost``.
            pending = cache.get(pending_key(attempt))
            if pending is None:
                pending = _PENDING_LOST
        if pending is not _PENDING_LOST:
            cache.set(pending_key(attempt), pending, ttl)
    services._emit(
        "max_auth_code_issued",
        attempt=str(attempt.public_id),
        operation_type=attempt.operation_type,
        issue=attempt.code_issues,
    )
    return Issued(attempt, code)


@dataclass(frozen=True)
class ConfirmResult:
    attempt: MaxAuthAttempt
    #: Пользователь, которого впускать/подтверждать (только при COMPLETED).
    user: object | None = None
    attempts_left: int | None = None
    #: Код неверный, попытка ещё жива.
    wrong_code: bool = False


def confirm(attempt: MaxAuthAttempt, *, code: str) -> ConfirmResult:
    """Проверить код и исполнить отложенное решение. Вызывающий уже сверил сессию.

    Всё — одной транзакцией под ``SELECT … FOR UPDATE``: параллельные вводы кода
    из одной сессии выстраиваются в очередь, и каждый видит счётчик предыдущего.
    Иначе пачка одновременных запросов проверяла бы код, пока счётчик уже за
    лимитом, а отказ «исчерпаны попытки» перетирал бы параллельный верный ввод
    (ревью В-1). Счётчик коммитится и при ответе «неверный код»: ``ATOMIC_REQUESTS``
    выключен, транзакция закрывается здесь, а не вместе с HTTP-ответом.
    """
    from . import services

    code = (code or "").strip()
    with transaction.atomic():
        attempt = MaxAuthAttempt.objects.select_for_update().get(pk=attempt.pk)
        attempt = services._refresh_expiry(attempt)
        if attempt.status != Status.CONFIRMATION_REQUIRED:
            return ConfirmResult(attempt)
        if attempt.confirm_failures >= MAX_FAILURES:
            # Лимит уже выбран параллельным запросом, который ещё не успел закрыть попытку.
            return ConfirmResult(
                services._fail(attempt, "code_attempts_exceeded", force=True), attempts_left=0
            )
        attempt.confirm_failures += 1
        attempt.save(update_fields=["confirm_failures"])
        failures = attempt.confirm_failures

        valid = len(code) == CODE_LENGTH and constant_time_compare(
            _hash(attempt.public_id.hex, code), attempt.confirm_code_hash
        )
        if not valid:
            if failures >= MAX_FAILURES:
                return ConfirmResult(
                    services._fail(attempt, "code_attempts_exceeded", force=True),
                    attempts_left=0,
                )
            services._emit(
                "max_auth_code_rejected", attempt=str(attempt.public_id), failures=failures
            )
            return ConfirmResult(attempt, attempts_left=MAX_FAILURES - failures, wrong_code=True)

        pending = load_pending(attempt)
        if pending is None:
            # Кэш потерян (рестарт, истёк TTL) — телефона больше нет, исполнять нечего.
            return ConfirmResult(services._fail(attempt, "pending_lost", force=True))
        try:
            # Вложенный atomic = savepoint: ошибка уникальности откатывает только
            # исполнение, а не всю транзакцию — иначе следом ``_fail`` упал бы с
            # TransactionManagementError и ответ был бы 500 (ревью Б-3).
            with transaction.atomic():
                attempt = services.execute(
                    attempt,
                    max_user_id=attempt.max_user_id,
                    chat_id=attempt.chat_id,
                    phone=pending.get("phone"),
                    profile=pending.get("profile") or {},
                )
        except IntegrityError:
            # Параллельное создание того же пользователя/привязки: отказ, не 500.
            return ConfirmResult(services._fail(attempt, "race", force=True))
    drop_pending(attempt)
    user = attempt.user if attempt.status == Status.COMPLETED else None
    return ConfirmResult(attempt, user=user)
