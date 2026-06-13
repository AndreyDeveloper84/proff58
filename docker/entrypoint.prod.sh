#!/usr/bin/env bash
# Entrypoint для web-контейнера в production.
# Применяет миграции, собирает статику и запускает gunicorn.
set -euo pipefail

echo "==> Применение миграций"
python manage.py migrate --noinput

echo "==> Сбор статики"
python manage.py collectstatic --noinput

echo "==> Запуск gunicorn"
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
