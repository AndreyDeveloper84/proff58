# Release Checklist

Чек-лист выкатки `dev → staging → main → production`.
Все шаги выполняются по порядку; не пропускать пункты, помеченные **[блокер]**.

> Связанные документы: [DEPLOY.md](DEPLOY.md) (настройка сервера),
> [regression-checklist.md](regression-checklist.md) (регрессионные тесты).

---

## 1. Подготовка релиза (до merge в main)

### 1.1 Код

- [ ] Все PR, входящие в релиз, влиты в `dev`
- [ ] CI зелёный на ветке `dev` (lint + pytest) **[блокер]**
- [ ] Нет открытых P0/P1 issues, блокирующих релиз
- [ ] Новые миграции проверены на обратимость (`migrate --plan`)

### 1.2 Секреты и конфигурация

- [ ] Все переменные из `.env.prod.example` заданы в prod `.env`
- [ ] `DJANGO_SECRET_KEY` — уникальный, длинный, не совпадает со staging
- [ ] `DJANGO_DEBUG=False` в production
- [ ] `DJANGO_ALLOWED_HOSTS` содержит `proff58.ru,www.proff58.ru`
- [ ] `ONEC_API_KEY` задан (непустой, длинный случайный ключ)
- [ ] `DJANGO_CREATE_SUPERUSER=false` (кроме первого деплоя)
- [ ] `SENTRY_ENVIRONMENT=production`
- [ ] Нет секретов, закоммиченных в репозиторий

### 1.3 Staging smoke

- [ ] Staging обновлён до текущего `dev` и работает
- [ ] Пройдена smoke-проверка staging (раздел 3 ниже)
- [ ] Миграции прошли без ошибок на staging

---

## 2. Деплой в production

### 2.1 Merge dev → main

- [ ] Создать PR `dev → main` с описанием изменений
- [ ] PR одобрен ревьюером **[блокер]**
- [ ] CI зелёный на PR **[блокер]**
- [ ] Merge PR — деплой запускается автоматически через `deploy.yml`

### 2.2 Мониторинг деплоя

- [ ] GitHub Actions job `deploy` завершился зелёным
- [ ] SSH на сервер: `docker compose -f docker-compose.prod.yml ps` — все сервисы `Up (healthy)`
- [ ] Лог web-контейнера без ошибок:
  ```bash
  docker compose -f docker-compose.prod.yml logs web --tail=50
  ```
- [ ] Миграции прошли (в логе `==> Применение миграций` без traceback)
- [ ] Статика собрана (в логе `==> Сбор статики`)

---

## 3. Smoke-проверка production

Выполнить **сразу после деплоя**. Не требует знания кода — только curl/браузер.

### 3.1 Инфраструктура

```bash
# Healthcheck: ожидаем 200 + {"status":"ok","db":"ok","redis":"ok"}
curl -s https://proff58.ru/healthz/ | python3 -m json.tool

# TLS сертификат: проверить срок действия
openssl s_client -connect proff58.ru:443 -servername proff58.ru 2>/dev/null \
  | openssl x509 -noout -dates

# Контейнеры: все должны быть Up
ssh taximeter@<HOST> 'cd /home/taximeter/proff58-prod && docker compose -f docker-compose.prod.yml ps'
```

- [ ] `/healthz/` → HTTP 200, status=ok, db=ok, redis=ok
- [ ] TLS сертификат валиден, срок > 14 дней
- [ ] Все контейнеры (web, db, redis, celery, celery-beat, nginx) — `Up`

### 3.2 Каталог (витрина)

```bash
# Дерево категорий
curl -s https://proff58.ru/api/catalog/categories/ | python3 -m json.tool | head -20

# Список товаров (с пагинацией)
curl -s 'https://proff58.ru/api/catalog/products/?limit=3' | python3 -m json.tool

# Карточка товара (подставить реальный slug)
curl -s https://proff58.ru/api/catalog/products/<slug>/ | python3 -m json.tool
```

- [ ] `GET /api/catalog/categories/` → 200, непустое дерево (если есть категории)
- [ ] `GET /api/catalog/products/` → 200, корректная пагинация (`count`, `results`)
- [ ] `GET /api/catalog/products/<slug>/` → 200, карточка с `breadcrumb`, `attributes`, `images`
- [ ] Фильтр по категории работает: `?category=<slug>`
- [ ] Только опубликованные товары видны (draft/imported не попадают)

### 3.3 Интеграция 1С

```bash
# Без ключа — 403
curl -s -w '%{http_code}' -o /dev/null https://proff58.ru/api/1c/products/import

# С ключом — проверка доступности (пустой items → 400, значит auth прошёл)
curl -s -X POST https://proff58.ru/api/1c/products/import \
  -H 'Content-Type: application/json' \
  -H 'X-Api-Key: <PROD_KEY>' \
  -d '{"items": []}'
```

- [ ] Без ключа → 403
- [ ] С ключом, пустой items → 400 (валидация работает, auth прошёл)
- [ ] Заказы 1С: `GET /api/1c/orders/new` без ключа → 403, с ключом → 200

### 3.4 Админ-панель

- [ ] `https://proff58.ru/admin/` → редирект на login
- [ ] Логин суперпользователя работает
- [ ] Каталог, товары, категории — отображаются
- [ ] `SiteSettings` — доступен, singleton (одна запись)

### 3.5 Статика и медиа

- [ ] CSS/JS админки загружаются (страница не «голая»)
- [ ] Изображения товаров отдаются (если есть)

---

## 4. Откат

### 4.1 Быстрый откат (без миграций)

Если проблема в коде, но не в миграциях:

```bash
cd /home/taximeter/proff58-prod

# Посмотреть предыдущий рабочий коммит
git log --oneline -5

# Откатиться
git checkout <previous-good-commit>
docker compose -f docker-compose.prod.yml up -d --build

# Проверить
docker compose -f docker-compose.prod.yml ps
curl -s https://proff58.ru/healthz/
```

### 4.2 Откат с миграцией

Если проблема в миграции БД:

1. **Оценить обратимость**: проверить, есть ли у миграции `reverse` (Django
   `RunPython` без `reverse_code` необратим)
2. **Сделать бэкап ПЕРЕД откатом**:
   ```bash
   cd /home/taximeter/proff58-prod
   BACKUP_DIR=/home/taximeter/backups/prod bash scripts/backup.sh
   ```
3. **Откатить миграцию** (если обратима):
   ```bash
   docker compose -f docker-compose.prod.yml exec web \
     python manage.py migrate <app_label> <previous_migration_number>
   ```
4. **Откатить код** (как в 4.1)
5. **Если миграция необратима** — восстановить БД из бэкапа:
   ```bash
   # Остановить web/celery
   docker compose -f docker-compose.prod.yml stop web celery celery-beat

   # Восстановить БД
   gunzip -c /home/taximeter/backups/prod/db-<timestamp>.sql.gz | \
     docker compose -f docker-compose.prod.yml exec -T db \
       psql -U $POSTGRES_USER $POSTGRES_DB

   # Откатить код и запустить
   git checkout <previous-good-commit>
   docker compose -f docker-compose.prod.yml up -d --build
   ```

### 4.3 Откат staging

```bash
cd /home/taximeter/proff58-staging
git log --oneline -5
git checkout <commit>
docker compose -f docker-compose.prod.yml up -d --build
```

---

## 5. Известные риски

| Риск | Описание | Митигация |
|------|----------|-----------|
| **Секреты** | `.env` с паролями БД и API-ключами | Файл не в git (`.gitignore`); права `600`; разные ключи для staging/prod |
| **Миграции** | Необратимые миграции блокируют быстрый откат | Всегда делать бэкап перед деплоем; проверять `RunPython` на наличие `reverse_code` |
| **Статика** | `collectstatic` забывает файлы при смене `STATIC_ROOT` | Volume `static_volume` персистентен; entrypoint запускает `collectstatic --noinput` |
| **Media** | Потеря загруженных изображений | Volume `media_volume` персистентен; ежедневный бэкап через `scripts/backup.sh` |
| **TLS** | Просроченный сертификат | Мониторинг через Uptime Kuma (алерт за 14 дней); Let's Encrypt auto-renew для staging |
| **Gunicorn** | Долгий запрос блокирует воркер | `gthread` worker class + `timeout=120` + `threads=4` |
| **Redis** | Потеря очереди задач при рестарте | Celery retry policy; задачи идемпотентны (повторный импорт безопасен) |
| **Один сервер** | Staging и prod на одном VPS | Изолированы через `COMPOSE_PROJECT_NAME` (отдельные БД, Redis, volumes) |

---

## 6. Контакты и эскалация

| Ситуация | Действие |
|----------|----------|
| Сайт недоступен (healthz 503) | Проверить контейнеры → логи web → перезапустить стек |
| Сертификат истекает | Продлить на reg.ru (prod) или `certbot renew` (staging) |
| Ошибка миграции | Не деплоить дальше; откатить по разделу 4.2 |
| 1С не может подключиться | Проверить `ONEC_API_KEY` в `.env` и заголовок `X-Api-Key` |
