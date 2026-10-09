#!/usr/bin/env bash
set -euo pipefail

umask 077

BACKUP_DIR="${BACKUP_DIR:-/home/taximeter/backups/proff58}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

retention_minutes=$((RETENTION_DAYS * 24 * 60))

find "$BACKUP_DIR"     -maxdepth 1 -type f     \( -name "db-*.sql.gz" -o -name "media-*.tgz" \)     -mmin +"$retention_minutes"     -delete
