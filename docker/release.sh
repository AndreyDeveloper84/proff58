#!/usr/bin/env bash
# Release-шаг прод-деплоя (#441/m-07): бэкап БД + миграции ДО подъёма web.
#
# Раньше web применял миграции на КАЖДОМ старте (docker/entrypoint.prod.sh) — опасно
# при rolling/повторных рестартах и тяжёлом DDL (гонки, долгий старт, откат невозможен).
# Теперь миграции — отдельный шаг с бэкапом БД для отката. Web на старте только
# проверяет применённость (migrate --check) и падает, если схема отстала.
#
# Вызывается из .github/workflows/deploy.yml перед `up -d`; можно запускать вручную
# (напр. отдельно от подъёма сервисов). Провал миграции ОСТАНАВЛИВАЕТ деплой — бэкап
# уже снят, откат по docs/DEPLOY.md.
set -euo pipefail

cd "$(dirname "$0")/.." # корень репозитория

# #576 (п.5): при РУЧНОМ запуске берём тот же лок, что и деплой-пайплайн, — чтобы
# не столкнуться с идущим деплоем. Из деплоя лок уже удержан (DEPLOY_LOCK_HELD=1),
# повторный flock на том же файле здесь заблокировал бы сам себя.
if [[ "${DEPLOY_LOCK_HELD:-0}" != "1" ]]; then
    exec 9>".deploy.lock"
    flock -w 300 9 || {
        echo "Не удалось взять .deploy.lock за 5 мин — идёт деплой/другая операция." >&2
        exit 1
    }
fi

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
compose="docker compose -f $COMPOSE_FILE"

# POSTGRES_* берём из .env (как scripts/backup.sh).
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

# 1. БД должна быть поднята и готова (для бэкапа и миграций).
echo "==> Поднимаем БД и ждём готовности"
$compose up -d db
for _ in $(seq 30); do
    if $compose exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done
$compose exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null

# 2. Бэкап БД ДО миграций (для отката). Только БД: миграции меняют схему, media не
#    трогают. Полный бэкап (БД+media) — scripts/backup.sh по cron/вручную.
backup_dir="${RELEASE_BACKUP_DIR:-${BACKUP_DIR:-/home/taximeter/backups/proff58}}"
mkdir -p "$backup_dir"
backup="$backup_dir/pre-migrate-$(date +%F-%H%M%S).sql.gz"
echo "==> Бэкап БД до миграций → $backup"
$compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip >"$backup"

# 3. Миграции одноразовым контейнером (web на старте их больше не применяет).
echo "==> Применение миграций"
$compose run --rm web python manage.py migrate --noinput

echo "==> Release готов: бэкап снят ($backup), миграции применены. Можно поднимать web."
