#!/usr/bin/env bash
# Обёртка над TDD Guard CLI (nizos/tdd-guard) для хуков SessionStart /
# UserPromptSubmit / PreToolUse(Write|Edit|MultiEdit|TodoWrite).
#
# TDD Guard перехватывает правки и БЛОКИРУЕТ написание реализации без падающего
# теста. Валидация делает LLM-вызов на каждую правку и требует API-ключ/клиент,
# поэтому по умолчанию проверка СПИТ. Активация — одной переменной окружения:
#
#   export TDD_GUARD_ENABLE=1
#   # и настроить валидатор TDD Guard (см. .claude/EXTRAS.md, раздел про TDD Guard)
#
# Безопасность: если выключено или бинарь не установлен — exit 0 (не блокируем
# работу). Stdin/stdout/exit-code прокидываются в реальный CLI без изменений.

[ "${TDD_GUARD_ENABLE:-0}" = "1" ] || exit 0

bin="$(command -v tdd-guard || true)"
[ -n "$bin" ] || exit 0

exec "$bin" "$@"
