#!/usr/bin/env bash
# SessionStart-хук: активация внешних наборов Claude Code для проекта «Профессионал».
#
# Зачем: облачное окружение эфемерно — всё в ~/.claude обнуляется при пересоздании
# контейнера, а внешние marketplace (github) из-за сетевой политики недоступны (403).
# Поэтому наборы вендорятся в репозиторий (.claude/skills-library/...), а этот хук
# каждую сессию восстанавливает их активацию из репо. Безопасен: всегда exit 0,
# любые ошибки проглатываются, ничего в проекте не меняет.
set -uo pipefail

DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
LIB="$DIR/.claude/skills-library"
USER_SKILLS="${HOME}/.claude/skills"
mkdir -p "$USER_SKILLS" 2>/dev/null || true

# --- superpowers: ставим как плагин из вендоренного marketplace ---------------
# (скиллы используют ${CLAUDE_PLUGIN_ROOT} и собственные хуки — нужен именно плагин)
if [ -d "$LIB/superpowers/.claude-plugin" ] && command -v claude >/dev/null 2>&1; then
  claude plugin marketplace add "$LIB/superpowers" >/dev/null 2>&1 || true
  claude plugin install superpowers@superpowers-dev >/dev/null 2>&1 || true
fi

# --- gstack: отдаём 52 скилла «инженерной команды» через симлинки -------------
# Имя скилла берётся из frontmatter SKILL.md, не из имени папки. Конфликт имён с
# встроенными скиллами (например, review) не перезаписываем — пропускаем.
if [ -d "$LIB/gstack" ]; then
  for skill_dir in "$LIB/gstack"/*/; do
    [ -f "${skill_dir}SKILL.md" ] || continue
    base="$(basename "$skill_dir")"
    target="$USER_SKILLS/$base"
    [ -e "$target" ] || ln -sfn "$skill_dir" "$target" 2>/dev/null || true
  done
fi

exit 0
