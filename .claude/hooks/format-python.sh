#!/usr/bin/env bash
# PostToolUse-хук: автоформат Python-файлов через ruff + black — инструменты
# стека проекта (CI гоняет `black --check`). Это замена JS-ориентированного
# post-edit-format (Biome/Prettier) из набора ecc-zh, неприменимого к Django.
#
# Безопасность: хук НИКОГДА не блокирует (всегда exit 0), правит только .py
# внутри проекта, ошибки инструментов гасятся.

input="$(cat)"

# Путь редактируемого файла из JSON, который Claude Code подаёт на stdin.
file="$(printf '%s' "$input" | python3 -c \
  'import sys,json; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' \
  2>/dev/null || true)"

case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

root="${CLAUDE_PROJECT_DIR:-.}"
ruff="$root/.venv/bin/ruff"; [ -x "$ruff" ] || ruff="$(command -v ruff || true)"
black="$root/.venv/bin/black"; [ -x "$black" ] || black="$(command -v black || true)"

[ -n "$ruff" ] && "$ruff" check --fix "$file" >/dev/null 2>&1 || true
[ -n "$black" ] && "$black" -q "$file" >/dev/null 2>&1 || true
exit 0
