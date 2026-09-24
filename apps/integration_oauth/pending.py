"""Незавершённые входы в Django-сессии браузера.

``state`` — одноразовый ключ: колбэк достаёт запись через ``pop`` и второй раз ту
же запись не получит. Сессия — не БД: так попытка входа привязана к браузеру,
который её начал (чужой браузер с тем же ``state`` ничего не найдёт), а мусор
уходит вместе с сессией.

Запись: ``{provider, verifier, next, via, intent, user_id, ts}``. Висящих не больше
``MAX_PENDING`` (самые старые выкидываются), просроченные — при каждом обращении.
"""

from __future__ import annotations

import re
import secrets
import time

from django.conf import settings

SESSION_KEY = "oauth_pending"
DONE_KEY = "oauth_done"
MAX_PENDING = 5

#: state и verifier — алфавит base64url; VK требует для state ≥ 32 символов.
_STATE_RE = re.compile(r"^[A-Za-z0-9_-]{43,128}$")


def ttl_seconds() -> int:
    return int(getattr(settings, "OAUTH_STATE_TTL_SECONDS", 600))


def create(
    session,
    *,
    provider: str,
    intent: str,
    next_url: str,
    via: str | None = None,
    user_id: int | None = None,
) -> tuple[str, str]:
    """Завести запись и вернуть ``(state, code_verifier)``."""
    state = secrets.token_urlsafe(32)  # 43 символа
    verifier = secrets.token_urlsafe(64)[:96]  # 43..128 по RFC 7636
    now = int(time.time())
    pending = _alive(session.get(SESSION_KEY), now)
    pending[state] = {
        "provider": provider,
        "verifier": verifier,
        "next": next_url,
        "via": via,
        "intent": intent,
        "user_id": user_id,
        "ts": now,
    }
    if len(pending) > MAX_PENDING:
        oldest = sorted(pending.items(), key=lambda kv: kv[1].get("ts", 0))
        for key, _ in oldest[: len(pending) - MAX_PENDING]:
            pending.pop(key, None)
    session[SESSION_KEY] = pending
    session.modified = True
    return state, verifier


def pop(session, state: str, provider: str) -> dict | None:
    """Забрать запись по ``state`` (одноразово). None — нет, просрочена или не тот провайдер."""
    raw = session.get(SESSION_KEY)
    if not raw:
        return None
    now = int(time.time())
    pending = _alive(raw, now)
    entry = pending.pop(state, None) if _valid_state(state) else None
    session[SESSION_KEY] = pending
    session.modified = True
    if entry is None or entry.get("provider") != provider:
        return None
    return entry


def remember_done(session, *, state: str, redirect_to: str, user_id: int) -> None:
    """Запомнить завершённый вход — для повторного колбэка (двойной клик, «назад»)."""
    session[DONE_KEY] = {
        "state": state,
        "redirect": redirect_to,
        "user_id": user_id,
        "ts": int(time.time()),
    }


def get_done(session, state: str) -> dict | None:
    done = session.get(DONE_KEY)
    if not isinstance(done, dict) or not _valid_state(state):
        return None
    if not secrets.compare_digest(str(done.get("state", "")), state):
        return None
    if int(time.time()) - int(done.get("ts", 0)) > ttl_seconds():
        return None
    return done


def _valid_state(state) -> bool:
    return isinstance(state, str) and bool(_STATE_RE.match(state))


def _alive(raw, now: int) -> dict:
    if not isinstance(raw, dict):
        return {}
    ttl = ttl_seconds()
    return {
        k: v
        for k, v in raw.items()
        if isinstance(v, dict) and 0 <= now - int(v.get("ts", 0) or 0) <= ttl
    }
