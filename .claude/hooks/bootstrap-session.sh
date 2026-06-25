#!/usr/bin/env bash
# SessionStart-хук: эфемерное облачное окружение теряет глобальные пакеты после
# пересоздания контейнера. Доустанавливаем рантайм TDD Guard — npm-CLI tdd-guard
# (нужен Node ≥22) и pytest-репортёр tdd-guard-pytest в venv проекта.
#
# Запускается ТОЛЬКО при включённом TDD Guard (TDD_GUARD_ENABLE=1), чтобы не
# тратить время старта сессии, пока проверка спит.
#
# Безопасность: всегда exit 0 — сетевые ошибки и отсутствие прав гасятся,
# чтобы НИКОГДА не блокировать старт сессии.

[ "${TDD_GUARD_ENABLE:-0}" = "1" ] || exit 0

root="${CLAUDE_PROJECT_DIR:-.}"

# npm-CLI tdd-guard (глобально), если ещё не стоит
if command -v npm >/dev/null 2>&1 && ! command -v tdd-guard >/dev/null 2>&1; then
  npm install -g tdd-guard >/dev/null 2>&1 || true
fi

# pytest-репортёр в venv проекта (Linux .venv/bin или Windows .venv/Scripts)
pip="$root/.venv/bin/pip"
[ -x "$pip" ] || pip="$root/.venv/Scripts/pip.exe"
[ -x "$pip" ] || pip="$(command -v pip3 || command -v pip || true)"
if [ -n "$pip" ] && ! "$pip" show tdd-guard-pytest >/dev/null 2>&1; then
  "$pip" install tdd-guard-pytest >/dev/null 2>&1 || true
fi

exit 0
