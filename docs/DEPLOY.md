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

## Автодеплой (CD) через GitHub Actions

Workflow `.github/workflows/deploy.yml` запускается **после успешного CI на ветке
`main`** и по SSH разворачивает прод на сервере:

```
push/merge в main → CI (lint+tests) → если зелёный → deploy.yml → SSH на VPS →
git reset --hard origin/main → docker compose -f docker-compose.prod.yml up -d --build
```

### Что нужно один раз сделать на сервере

```bash
# Docker уже стоит (см. выше). Клонируем репозиторий в постоянный каталог:
git clone https://ВАШ_ТОКЕН@github.com/AndreyDeveloper84/proff58.git /opt/proff58
cd /opt/proff58
git checkout main
cp .env.prod.example .env && nano .env     # заполнить как при ручном деплое
```

### GitHub Secrets (Settings → Secrets and variables → Actions)

| Secret | Значение |
|---|---|
| `SSH_HOST` | IP или домен сервера |
| `SSH_USER` | пользователь для SSH (например, `deploy` или `root`) |
| `SSH_KEY` | приватный SSH-ключ этого пользователя (весь файл) |
| `DEPLOY_PATH` | путь к репозиторию на сервере, например `/opt/proff58` |
| `SSH_PORT` | порт SSH, если не 22 (опционально) |

Сгенерировать пару ключей и положить публичный на сервер:

```bash
ssh-keygen -t ed25519 -f deploy_key -N ""
ssh-copy-id -i deploy_key.pub SSH_USER@SSH_HOST   # публичный — на сервер
# приватный deploy_key → в GitHub Secret SSH_KEY
```

### Важно

- Деплой срабатывает **только на `main`**. Рабочий поток: `feature → PR в dev →`
  релизный PR `dev → main`. Мерж в `main` запускает CI, а за ним — автодеплой.
- `git reset --hard origin/main` на сервере: локальные правки в каталоге деплоя
  будут затёрты — там не редактируем код руками (кроме `.env`, он в `.gitignore`).
- Миграции и `collectstatic` выполняются автоматически в entrypoint контейнера `web`.

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
