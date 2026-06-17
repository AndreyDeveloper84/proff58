#!/usr/bin/env bash
# Entrypoint для web-контейнера в production.
# Применяет миграции, собирает статику и запускает gunicorn.
set -euo pipefail

mkdir -p /app/logs

echo "==> Применение миграций"
python manage.py migrate --noinput

echo "==> Сбор статики"
python manage.py collectstatic --noinput

if [[ "${DJANGO_CREATE_SUPERUSER:-false}" == "true" ]]; then
    echo "==> Проверка суперпользователя"
    python manage.py shell -c "
import os
from django.contrib.auth import get_user_model

User = get_user_model()
if User.objects.filter(is_superuser=True).exists():
    print('Суперпользователь уже есть, пропускаем создание.')
else:
    phone = os.environ.get('DJANGO_SUPERUSER_PHONE')
    password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
    if not phone or not password:
        raise SystemExit('DJANGO_SUPERUSER_PHONE и DJANGO_SUPERUSER_PASSWORD обязательны.')
    User.objects.create_superuser(phone=phone, password=password)
    print('Суперпользователь создан.')
"
fi

echo "==> Запуск gunicorn"
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
