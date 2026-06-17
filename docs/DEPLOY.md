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

## CI/CD: две среды (staging + production) на одном VPS

Пайплайн проверок вынесен в переиспользуемый `tests.yml` и используется и на PR,
и перед деплоем — без дублирования:

```
PR в dev/main        → ci.yml      → tests.yml (lint + pytest)
push/merge в dev     → deploy.yml  → tests.yml → деплой в environment "staging"
push/merge в main    → deploy.yml  → tests.yml → деплой в environment "production"
```

Деплой идёт **только при зелёных тестах**. Ветка выбирает среду, а среда
(`GitHub Environment`) подставляет свой набор секретов — staging и production
не пересекаются.

### Один VPS — два стека за ХОСТОВЫМ nginx

На сервере уже есть системный nginx на :80/:443 — он и работает reverse-proxy
(отдельный докер-proxy не нужен). Стеки слушают только `127.0.0.1`, хостовый
nginx терминирует TLS (cert reg.ru) и проксирует по домену:

```
                 ┌─ хостовый nginx (:80→:443, TLS reg.ru) ─┐
 proff58.ru ─────┤  → 127.0.0.1:8081  (prod-стек)           │
 dev.proff58.ru ─┤  → 127.0.0.1:8082  (staging-стек)        │
                 └──────────────────────────────────────────┘
```

Стеки `prod`/`staging` поднимаются из одного `docker-compose.prod.yml` в разных
каталогах со своим `.env`. Изоляция — через `COMPOSE_PROJECT_NAME` (свои
контейнеры/тома: отдельные БД/Redis/media). Наружу публичных портов нет — только
`127.0.0.1:WEB_HTTP_PORT`, доступный лишь хостовому nginx.

| | production (main) | staging (dev) |
|---|---|---|
| Каталог | `/home/taximeter/proff58-prod` | `/home/taximeter/proff58-staging` |
| `COMPOSE_PROJECT_NAME` | `proff58_prod` | `proff58_staging` |
| `WEB_HTTP_PORT` (127.0.0.1) | `8081` | `8082` |
| Домен | `proff58.ru` | `dev.proff58.ru` |

### Первичная подготовка сервера

```bash
# Пользователь taximeter должен уметь запускать docker:
#   sudo usermod -aG docker taximeter   # один раз, затем перелогиниться

# production
git clone https://ТОКЕН@github.com/AndreyDeveloper84/proff58.git ~/proff58-prod
cd ~/proff58-prod && git checkout main
cp .env.prod.example .env && nano .env   # COMPOSE_PROJECT_NAME=proff58_prod, WEB_HTTP_PORT=8081, домен, пароли

# staging
git clone https://ТОКЕН@github.com/AndreyDeveloper84/proff58.git ~/proff58-staging
cd ~/proff58-staging && git checkout dev
cp .env.prod.example .env && nano .env   # COMPOSE_PROJECT_NAME=proff58_staging, WEB_HTTP_PORT=8082, тестовые ключи
```

> `~` = `/home/taximeter`. Базы у стеков **разные** — staging никогда не трогает боевые данные.
> На staging интеграции в тестовом режиме (ЮKassa-песочница, заглушка SMS, свой `ONEC_API_KEY`).

### Хостовый nginx и сертификат (HTTPS)

```bash
# 1. Сертификат reg.ru на сервер (нужен root):
sudo mkdir -p /etc/ssl/proff58
#   /etc/ssl/proff58/fullchain.pem  (cat proff58.ru.crt intermediate.crt > fullchain.pem)
#   /etc/ssl/proff58/privkey.pem    (приватный ключ)
# Идеально — SAN-сертификат на proff58.ru + dev.proff58.ru.

# 2. Конфиги доменов в хостовый nginx (готовые лежат в docs/nginx/):
sudo cp ~/proff58-prod/docs/nginx/proff58.ru.conf      /etc/nginx/conf.d/
sudo cp ~/proff58-prod/docs/nginx/dev.proff58.ru.conf  /etc/nginx/conf.d/

# 3. Проверить и применить:
sudo nginx -t && sudo systemctl reload nginx
```

После этого: `https://proff58.ru` → prod-стек, `https://dev.proff58.ru` → staging.
При смене сертификата — заменить файлы и `sudo systemctl reload nginx`.

### GitHub Environments и секреты

Создайте два Environment (`Settings → Environments`): **production** и **staging**.
В каждом — свой набор секретов (одинаковые имена, разные значения):

| Secret | production | staging |
|---|---|---|
| `SSH_HOST` | IP сервера | тот же IP |
| `SSH_USER` | `taximeter` | `taximeter` |
| `SSH_KEY` | приватный SSH-ключ | тот же ключ |
| `DEPLOY_PATH` | `/home/taximeter/proff58-prod` | `/home/taximeter/proff58-staging` |
| `SSH_PORT` | если не 22 | если не 22 |

На production можно включить **Required reviewers** — тогда деплой в прод ждёт
ручного подтверждения (одна кнопка в Actions), а staging катится сам.

Сгенерировать ключ деплоя и положить публичную часть на сервер:

```bash
ssh-keygen -t ed25519 -f deploy_key -N ""
ssh-copy-id -i deploy_key.pub SSH_USER@SSH_HOST   # публичный — на сервер
# приватный deploy_key → в Secret SSH_KEY (в обоих Environment)
```

### Важно

- Рабочий поток: `feature → PR в dev` (CI) → мерж в `dev` (деплой на staging) →
  релизный PR `dev → main` → мерж (деплой на production).
- `git reset --hard origin/<ветка>` на сервере затирает локальные правки кода —
  руками там не редактируем (кроме `.env`, он в `.gitignore`).
- Миграции и `collectstatic` — автоматически в entrypoint контейнера `web`.
- Два домена с чистым HTTPS на одном хосте лучше развести через единый
  reverse-proxy (Caddy/Traefik с авто-TLS) — добавим, когда появится сервер.

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
