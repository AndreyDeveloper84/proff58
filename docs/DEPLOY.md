# Деплой на сервер

Production-стенд поднимается одной командой `docker compose` и состоит из:
`nginx` (раздаёт статику и проксирует) → `web` (Django+gunicorn) → `db` (PostgreSQL), `redis`,
`celery` и `celery-beat` (фоновые задачи).

## Требования к серверу

- Linux-VPS (Ubuntu 22.04+ / Debian 12+), 1–2 vCPU, 2+ ГБ RAM.
- Установленные Docker и Docker Compose plugin.
- Открытый порт 80 (и 443, если будет HTTPS).

```bash
# Установка Docker (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sh
```

## Шаги развёртывания

```bash
# 1. Клонировать репозиторий
git clone https://github.com/AndreyDeveloper84/proff58.git
cd proff58
git checkout dev          # или main после релиза

# 2. Подготовить переменные окружения
cp .env.prod.example .env
nano .env                 # заполнить домен/IP, пароли, секретный ключ

# 3. Сгенерировать DJANGO_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
#   вставить результат в .env → DJANGO_SECRET_KEY

# 4. Собрать и запустить
docker compose -f docker-compose.prod.yml up -d --build

# 5. Создать суперпользователя (логин — телефон)
docker compose -f docker-compose.prod.yml exec web \
    python manage.py createsuperuser --noinput \
    --phone "$DJANGO_SUPERUSER_PHONE" || true
#   (миграции и collectstatic выполняются автоматически в entrypoint)
```

Админка: `http://ВАШ_ДОМЕН_ИЛИ_IP/admin/`

## Важные моменты `.env`

- `DJANGO_ALLOWED_HOSTS` — перечислить домен и/или IP через запятую, иначе Django вернёт 400.
- `DJANGO_SECURE_SSL_REDIRECT=False` — пока нет HTTPS; иначе будет бесконечный редирект.
- `POSTGRES_PASSWORD` в секции БД и пароль внутри `DATABASE_URL` должны совпадать.

## Обновление версии

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## HTTPS (после привязки домена)

Рекомендуется добавить отдельный контейнер с `certbot` или поставить домен за Cloudflare.
После включения HTTPS установить `DJANGO_SECURE_SSL_REDIRECT=True` и перезапустить `web`.

## Полезные команды

```bash
# Логи
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f celery

# Django shell
docker compose -f docker-compose.prod.yml exec web python manage.py shell

# Перезапуск
docker compose -f docker-compose.prod.yml restart web
```
