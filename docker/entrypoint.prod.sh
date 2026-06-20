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

echo "==> Прогрев воркеров в фоне (не блокирует старт)"
# Фоновый прогрев: дождётся gunicorn и дёрнет публичные URL, чтобы первый живой
# запрос после пересборки не ловил компиляцию шаблонов и установку соединения с БД.
python /app/docker/warmup.py &

echo "==> Запуск gunicorn"
# worker-class=gthread + threads: один медленный запрос (тяжёлая админка) или
# всплеск ботов-сканеров не блокирует весь сайт — внутри воркера есть потоки.
# ВНИМАНИЕ: --preload здесь НЕ используем. С постоянными соединениями БД
# (CONN_MAX_AGE) форки воркеров наследуют сокет к Postgres из мастера → под
# параллельными запросами соединение рушится и запросы виснут (ERR_TIMED_OUT).
# Прогрев выше даёт почти тот же выигрыш на холодном старте без этого риска.
# (Вернуть --preload можно только вместе с post_fork-хуком, закрывающим
# унаследованные соединения: django.db.connections.close_all().)
# access-logformat с %(D)s — время каждого запроса в микросекундах (видно тормоза).
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --worker-class "${GUNICORN_WORKER_CLASS:-gthread}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout 120 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile - \
    --access-logformat '%(h)s %(t)s "%(r)s" %(s)s %(b)s %(D)susec'
