#!/usr/bin/env bash
set -euo pipefail

DEPLOY_PATH="${1:?deploy path is required}"
BACKUP_DIR="${2:?backup dir is required}"
RETENTION_DAYS="${3:-14}"
MARKER="proff58-privacy-cleanup"
LOG_FILE="$BACKUP_DIR/backup.log"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "$current" | grep -v "$MARKER" || true)"
line="*/15 * * * * umask 077; cd $DEPLOY_PATH && BACKUP_DIR=$BACKUP_DIR BACKUP_RETENTION_DAYS=$RETENTION_DAYS bash ./scripts/cleanup_backups.sh >> $LOG_FILE 2>&1 # $MARKER"

{
    printf '%s\n' "$filtered"
    printf '%s\n' "$line"
} | awk 'NF' | crontab -

echo "backup_cleanup_cron=installed"
crontab -l | grep -F "$MARKER"
