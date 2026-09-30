"""«Подтвердите, что это вы» — свежий вход перед опасными действиями (DRF-2497).

Удаление аккаунта, смена e-mail (это логин и адрес сброса пароля) и привязка
нового способа входа не должны удаваться одной украденной или оставленной
открытой сессией.

- У кого есть пароль — подтверждает паролем: вход по паролю в последние
  ``window_seconds()`` секунд или пароль прямо в запросе. Вход через MAX, VK ID
  или Яндекс ID для них не в счёт — иначе открытая в том же браузере сессия
  провайдера давала бы удалить аккаунт без пароля (решение владельца: у кого
  пароль — как раньше).
- У кого пароля нет (вход через MAX, VK ID, Яндекс ID) — входит ещё раз своим
  способом; отметка живёт в сессии.

Неверные пароли считаются по пользователю и общим счётчиком для всех мест
проверки — иначе каждое новое место стало бы неограниченным оракулом пароля.

Модуль в слое 0 и об интеграциях не знает: отметку ставит ресивер
``user_logged_in`` (любой ``login()``) и интеграции, которые подтверждают
личность без входа, через ``mark_verified``.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY
from django.contrib.auth.signals import user_logged_in
from django.core.cache import cache
from django.dispatch import receiver
from rest_framework import status
from rest_framework.response import Response

SESSION_KEY = "auth_verified"
PASSWORD = "password"
EXTERNAL = "external"
#: Вход через эти бэкенды — вход по паролю; остальные (MAX, OAuth) — внешний.
PASSWORD_BACKENDS = frozenset({"apps.accounts.auth_backends.EmailBackend"})
#: Допуск на расхождение часов процессов: отметка «из будущего» на пару секунд — не подделка.
_CLOCK_SKEW = 5

REAUTH_REQUIRED = "reauth_required"
REAUTH_DETAIL = "Подтвердите, что это вы: войдите ещё раз."
LOCKED = "reauth_locked"
LOCKED_DETAIL = "Слишком много неверных попыток. Попробуйте позже."
WRONG_PASSWORD = "Неверный пароль."


def window_seconds() -> int:
    return int(getattr(settings, "ACCOUNT_REAUTH_WINDOW_SECONDS", 600))


def _max_failures() -> int:
    return int(getattr(settings, "ACCOUNT_REAUTH_MAX_FAILURES", 5))


def _lock_seconds() -> int:
    return int(getattr(settings, "ACCOUNT_REAUTH_LOCK_SECONDS", 900))


def mark_verified(
    request,
    *,
    method: str,
    at: datetime | float | None = None,
    rotate: bool = True,
) -> None:
    """Отметить, что личность подтверждена способом ``method`` в момент ``at``.

    ``rotate`` меняет ключ сессии: кука, скопированная до подтверждения, после
    него перестаёт действовать. После ``login()`` ротировать не нужно — Django
    уже выдал новую сессию или оставил ту же для того же пользователя.
    """
    if isinstance(at, datetime):
        at = at.timestamp()
    at = int(at if at is not None else time.time())
    current = _mark(request)
    if current is not None and current["at"] > at:
        # Более свежую отметку не затираем старой (например, давно завершённой
        # попыткой MAX поверх только что введённого пароля).
        return
    request.session[SESSION_KEY] = {"at": at, "method": method}
    if rotate:
        request.session.cycle_key()


def _mark(request) -> dict | None:
    session = getattr(request, "session", None)
    value = session.get(SESSION_KEY) if session is not None else None
    if not isinstance(value, dict) or not isinstance(value.get("at"), int | float):
        return None
    return value


def is_recently_verified(request) -> bool:
    """Подтверждение свежее и годится этому пользователю (у кого пароль — только паролем)."""
    mark = _mark(request)
    if mark is None:
        return False
    age = time.time() - mark["at"]
    if not -_CLOCK_SKEW <= age <= window_seconds():
        return False
    user = request.user
    if user.has_usable_password() and mark.get("method") != PASSWORD:
        return False
    return True


def verified_until(request) -> datetime | None:
    """До какого момента действует подтверждение (для кабинета); None — не действует."""
    if not is_recently_verified(request):
        return None
    return datetime.fromtimestamp(_mark(request)["at"] + window_seconds(), tz=UTC)


def _failures_key(user) -> str:
    return f"reauth:pw_fail:{user.pk}"


def verify_password(request, password: str) -> Response | None:
    """Проверить пароль текущего пользователя со счётчиком неверных попыток.

    None — пароль верный (и отметка «подтверждено паролем» поставлена); иначе отказ:
    400 при неверном пароле, 429 ``reauth_locked`` после ``_max_failures()`` неудач
    подряд — до ``_lock_seconds()`` с последней неудачи.
    """
    user = request.user
    # Попытку засчитываем ДО проверки: иначе пачка параллельных запросов успевает
    # проверить пароль, пока счётчик ещё не вырос. Верный пароль счётчик сбрасывает.
    key = _failures_key(user)
    cache.add(key, 0, _lock_seconds())
    try:
        attempts = cache.incr(key)
    except ValueError:  # ключ истёк между add и incr
        cache.set(key, 1, _lock_seconds())
        attempts = 1
    cache.touch(key, _lock_seconds())
    if attempts > _max_failures():
        return Response(
            {"detail": LOCKED_DETAIL, "code": LOCKED}, status=status.HTTP_429_TOO_MANY_REQUESTS
        )
    if not isinstance(password, str) or not password or not user.check_password(password):
        return Response({"detail": WRONG_PASSWORD}, status=status.HTTP_400_BAD_REQUEST)
    cache.delete(key)
    mark_verified(request, method=PASSWORD)
    return None


def field(request, name: str) -> str | None:
    """Строковое поле тела запроса; не строка или тело не объект — None (а не 500)."""
    data = request.data
    value = data.get(name) if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None


def check(request, *, password: str | None = None) -> Response | None:
    """Проверка перед опасным действием. None — можно; иначе готовый ответ-отказ.

    Свежее подходящее подтверждение — можно. Иначе у кого пароль — пароль из
    запроса (со счётчиком неудач). Без пароля и без свежего входа — 403
    ``reauth_required``: кабинет предложит подтвердить личность.
    """
    if is_recently_verified(request):
        return None
    if request.user.has_usable_password() and isinstance(password, str) and password:
        return verify_password(request, password)
    return Response(
        {"detail": REAUTH_DETAIL, "code": REAUTH_REQUIRED}, status=status.HTTP_403_FORBIDDEN
    )


@receiver(user_logged_in, dispatch_uid="accounts.reauth.mark_on_login")
def _mark_on_login(sender, request=None, user=None, **kwargs) -> None:
    session = getattr(request, "session", None)
    if session is None:
        return
    backend = session.get(BACKEND_SESSION_KEY, "")
    method = PASSWORD if backend in PASSWORD_BACKENDS else EXTERNAL
    mark_verified(request, method=method, rotate=False)
