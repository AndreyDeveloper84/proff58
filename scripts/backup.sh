#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/home/taximeter/backups/proff58}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

mkdir -p "$BACKUP_DIR"

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

timestamp="$(date +%F-%H%M)"
db_backup="$BACKUP_DIR/db-$timestamp.sql.gz"
media_backup="$BACKUP_DIR/media-$timestamp.tgz"
# Архив отклонённых кандидатов фото (§7.1) — отдельный том, не в media_volume.
# Тот же срок хранения, что у остального: решение о судьбе файлов — за
# владельцем, эта команда их не чистит, только резервирует наравне с прочим.
private_media_backup="$BACKUP_DIR/private-media-$timestamp.tgz"

docker compose -f "$COMPOSE_FILE" exec -T db \
    pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$db_backup"

docker compose -f "$COMPOSE_FILE" exec -T web \
    tar czf - -C /app/media . > "$media_backup"

docker compose -f "$COMPOSE_FILE" exec -T web \
    tar czf - -C /app/private_media . > "$private_media_backup"

find "$BACKUP_DIR" \
    \( -name "db-*.sql.gz" -o -name "media-*.tgz" -o -name "private-media-*.tgz" \) \
    -mtime +"$RETENTION_DAYS" \
    -delete

echo "Backup completed: $db_backup"
echo "Backup completed: $media_backup"
echo "Backup completed: $private_media_backup"
