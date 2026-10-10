# Деплой proff58

## Схема окружений

- `dev` -> staging: `dev.proff58.ru`, стек `/home/taximeter/proff58-staging`, порт `8082`.
- `main` -> production: `proff58.ru`, стек `/home/taximeter/proff58-prod`, порт `8081`.
- TLS завершает хостовый nginx. Внутри каждого Docker-стека свой nginx отдает static/media и проксирует в gunicorn.

## GitHub Actions

Создать environments `staging` и `production` в `Settings -> Environments`.

Секреты для обоих environments:

| Secret | staging | production |
|---|---|---|
| `SSH_HOST` | IP сервера | IP сервера |
| `SSH_USER` | `taximeter` | `taximeter` |
| `SSH_KEY` | приватный deploy key | приватный deploy key |
| `SSH_PORT` | `22` или свой порт | `22` или свой порт |
| `DEPLOY_PATH` | `/home/taximeter/proff58-staging` | `/home/taximeter/proff58-prod` |

Для `production` включить Required reviewers. Для `main` включить branch protection: PR, минимум один approval, обязательный зеленый CI.

### Образ витрины собирается в Actions

`frontend` в `docker-compose.prod.yml` — это `image: proff58-frontend:latest`, без `build:`.
Workflow собирает образ на машине GitHub, копирует архив в `DEPLOY_PATH` и делает
`docker load` перед `docker compose build`. На VPS `next build` не выдерживал диск
(17.09.2026: четыре выкладки подряд упали на старте сборки фронта) и на время сборки
замедлял живой сайт.

Следствие для ручных действий на сервере: `docker compose up -d --build` **не пересоберёт
витрину**. Чтобы получить образ без workflow — собрать его руками
(`docker build -t proff58-frontend:latest ./frontend`, на VPS это долго) или перезапустить
нужную выкладку в Actions.

## Сервер

```bash
sudo apt-get update
sudo apt-get install -y fail2ban nginx
sudo systemctl enable --now fail2ban
sudo usermod -aG docker taximeter
```

После добавления пользователя в группу `docker` перелогиниться.

## Клонирование стеков

```bash
git clone https://github.com/AndreyDeveloper84/proff58.git /home/taximeter/proff58-prod
cd /home/taximeter/proff58-prod
git checkout main
cp .env.prod.example .env
```

Production `.env`:

```env
COMPOSE_PROJECT_NAME=proff58_prod
WEB_HTTP_PORT=8081
DJANGO_ALLOWED_HOSTS=proff58.ru,www.proff58.ru,localhost,127.0.0.1
SENTRY_ENVIRONMENT=production
DJANGO_CREATE_SUPERUSER=true
```

После первого успешного запуска вернуть `DJANGO_CREATE_SUPERUSER=false`.

Staging:

```bash
git clone https://github.com/AndreyDeveloper84/proff58.git /home/taximeter/proff58-staging
cd /home/taximeter/proff58-staging
git checkout dev
cp .env.prod.example .env
```

Staging `.env`:

```env
COMPOSE_PROJECT_NAME=proff58_staging
WEB_HTTP_PORT=8082
DJANGO_ALLOWED_HOSTS=dev.proff58.ru,localhost,127.0.0.1
SENTRY_ENVIRONMENT=staging
DJANGO_CREATE_SUPERUSER=true
```

Запуск:

```bash
cd /home/taximeter/proff58-prod
mkdir -p logs
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

## TLS и хостовый nginx

Production использует коммерческий сертификат reg.ru:

```bash
sudo mkdir -p /etc/ssl/proff58
sudo cp fullchain.pem /etc/ssl/proff58/fullchain.pem
sudo cp privkey.pem /etc/ssl/proff58/privkey.pem
sudo chmod 600 /etc/ssl/proff58/privkey.pem
sudo cp /home/taximeter/proff58-prod/docs/nginx/proff58.ru.conf /etc/nginx/conf.d/
sudo nginx -t
sudo systemctl reload nginx
```

`fullchain.pem` должен содержать сертификат домена и промежуточные сертификаты. SAN должен включать `proff58.ru` и `www.proff58.ru`.

Staging использует Let's Encrypt:

```bash
sudo apt-get install -y certbot
sudo mkdir -p /var/www/certbot
sudo cp /home/taximeter/proff58-prod/docs/nginx/dev.proff58.ru.conf /etc/nginx/conf.d/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/certbot -d dev.proff58.ru \
  --email admin@proff58.ru --agree-tos --no-eff-email
echo 'deploy-hook = systemctl reload nginx' | sudo tee -a /etc/letsencrypt/renewal/dev.proff58.ru.conf
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

## Бэкапы

Production:

```bash
mkdir -p /home/taximeter/backups/prod
cd /home/taximeter/proff58-prod
BACKUP_DIR=/home/taximeter/backups/prod bash scripts/backup.sh
```

Cron:

```cron
30 3 * * * cd /home/taximeter/proff58-prod && BACKUP_DIR=/home/taximeter/backups/prod bash scripts/backup.sh >> /home/taximeter/backups/prod/backup.log 2>&1
```

Скрипт делает `pg_dump`, архивирует `/app/media` и удаляет архивы старше 14 дней.

## Миграции и релиз-шаг

PDF-счёт B2B (WeasyPrint) требует системных пакетов в образе `web` (`libpango-1.0-0`,
`libpangoft2-1.0-0`, `libharfbuzz-subset0`, `fonts-dejavu-core` — см. Dockerfile): после
этой правки нужна пересборка образа `web` (`docker compose build web`), одного перезапуска
контейнера недостаточно.

Миграции применяются **отдельным release-шагом** (`docker/release.sh`), а не на старте
`web` (#441/m-07). Раньше `web` мигрировал при каждом рестарте контейнера — риск гонок и
долгого/необратимого DDL.

После DRF-2972 HTTP-backend состоит из двух Django slot: `web` (slot A) и `web-b`
(slot B), перед которыми работает стабильный `backend-router`. Порядок live-deploy
в `deploy.yml`:

1. сборка backend/worker-образов;
2. `release.sh`: backup + миграции один раз;
3. обновить `web-b` и дождаться `healthy`;
4. поднять/перечитать `backend-router`;
5. перевести Next/BFF на router и graceful-reload stack nginx;
6. запустить availability probe (`/healthz/` = 200, `/api/1c/orders/new` без ключа = 403);
7. обновить `web` (slot A), пока slot B продолжает обслуживать трафик;
8. дождаться `healthy`, затем обновить worker'ы и выполнить post-deploy smoke.

**На живом сайте не использовать общий `docker compose up -d --build` для обновления
runtime-кода:** он может одновременно пересоздать оба Django slot и вернуть окно 502.
Общий `up -d` допустим для холодного старта или заранее принятого maintenance-окна.

### Совместимость миграций при rolling deploy

Пока новый slot запускается, второй slot может ещё несколько минут выполнять старый код
на уже обновлённой схеме БД. Поэтому автоматический rolling deploy допускает только
**backward-compatible** миграции: добавление nullable/default-полей, новых таблиц/индексов
и другие изменения, которые не ломают предыдущую версию приложения.

Переименование/удаление поля или таблицы, изменение контракта данных, несовместимое со
старым кодом, делается через expand/contract:

1. expand — добавить новую структуру, сохранив старую;
2. выкатить код, который умеет работать с переходной схемой;
3. перенести/проверить данные;
4. отдельным последующим релизом выполнить contract — удалить старую структуру.

Если expand/contract невозможен, нужен заранее объявленный maintenance-window; это уже
не zero-downtime deploy.

`docker/release.sh`:

1. поднимает `db` и ждёт готовности (`pg_isready`);
2. снимает бэкап БД **до** миграций → `pre-migrate-<дата>.sql.gz` в `BACKUP_DIR`
   (по умолчанию `/home/taximeter/backups/proff58`);
3. применяет миграции одноразовым контейнером (`compose run --rm web … migrate`).

`web` на старте миграции не применяет — только `migrate --check`: если схема отстала
(release не отработал), контейнер падает с понятной ошибкой, а не работает на рассинхроне.
Провал миграции в деплое **останавливает** выкат; бэкап уже снят для отката (см. ниже).

Ручной прогон только миграций (без замены живых application-контейнеров):

```bash
cd /home/taximeter/proff58-prod
bash docker/release.sh
```

Ручное rolling-обновление backend после уже выполненного release-step:

```bash
compose="docker compose -f docker-compose.prod.yml"

$compose up -d --no-deps web-b
# дождаться: docker inspect <web-b-container> -> Health.Status=healthy

$compose up -d --no-deps backend-router
$compose exec -T backend-router nginx -t
$compose exec -T backend-router nginx -s reload

$compose up -d --no-deps frontend
# дождаться health frontend

$compose exec -T nginx nginx -t
$compose exec -T nginx nginx -s reload

$compose up -d --no-deps web
# дождаться health web; web-b всё это время остаётся доступным
```

## Логи

Файлы лежат в `DEPLOY_PATH/logs`:

- `django.log`
- `1c.log`
- `payments.log`
- `nginx_access.log`
- `nginx_error.log`

Быстрая проверка:

```bash
tail -f /home/taximeter/proff58-prod/logs/django.log
docker compose -f docker-compose.prod.yml logs web web-b backend-router --tail=100
```

## Мониторинг

Рекомендуемый минимум:

```bash
docker run -d --restart=always --name uptime-kuma \
  -p 127.0.0.1:3001:3001 -v uptime-kuma:/app/data louislam/uptime-kuma:1
```

Мониторы:

- `https://proff58.ru/healthz/`, ожидаемый HTTP 200.
- `https://dev.proff58.ru/healthz/`, ожидаемый HTTP 200.
- Certificate expiry для `proff58.ru`, предупреждение за 14-30 дней.

Уведомления отправлять в Telegram.

## Проверка

```bash
curl -I https://proff58.ru/healthz/
curl -I https://dev.proff58.ru/healthz/
openssl s_client -connect proff58.ru:443 -servername proff58.ru | openssl x509 -noout -dates
docker compose -f docker-compose.prod.yml ps
```

`/healthz/` возвращает `200 {"status":"ok","db":"ok","redis":"ok"}`. При падении PostgreSQL или Redis вернет 503, чтобы Uptime Kuma поднял алерт.

## Откат

Для live-backend rollback **не** использовать общий `up -d --build`: откат также
выполняется по slot, чтобы хотя бы один Django instance оставался доступным.

```bash
cd /home/taximeter/proff58-prod
git log --oneline -5
git checkout <previous-good-commit>
compose="docker compose -f docker-compose.prod.yml"

# Собрать предыдущий backend image под тем же стабильным тегом.
$compose build web

# Сначала slot B; если старый код несовместим со схемой, migrate --check остановит
# только этот slot, а текущий web(A) останется жив.
$compose up -d --no-deps web-b
# дождаться Health.Status=healthy

# Затем slot A — только после успешного B.
$compose up -d --no-deps web
# дождаться Health.Status=healthy

$compose ps
```

`git checkout` откатывает **код**; старый backend выполнит `migrate --check` и
не станет healthy, если новые миграции уже несовместимы. В таком случае второй,
ещё не тронутый slot остаётся доступным, а дальнейший rollback останавливается до
решения по схеме БД.

Витрину backend-команда не пересобирает (frontend-образ приходит из Actions, см. выше):
для отката фронта перезапустить в Actions выкладку нужного коммита или собрать образ руками.

### Откат схемы БД

Бэкап снят release-шагом **до** миграций: `pre-migrate-<дата>.sql.gz` в `BACKUP_DIR`.
Сначала оцени обратимость — часто достаточно откатить одну миграцию без восстановления:

```bash
cd /home/taximeter/proff58-prod
compose="docker compose -f docker-compose.prod.yml"
$compose run --rm web python manage.py migrate <app> <предыдущая_миграция>
```

Полное восстановление из дампа (⚠️ данные, добавленные ПОСЛЕ бэкапа, теряются —
только осознанно; дамп плоский, поэтому БД пересоздаётся):

> Privacy gate (DRF-2964): до destructive restore экспортировать restore-manifest
> из текущей живой БД, хранить его ВНЕ восстанавливаемой БД с mode 0600. После
> restore web/celery/celery-onec/celery-beat остаются остановленными, пока
> reconciliation не вернёт состояние ранее обезличенных аккаунтов и retention-cleanup.
>
> ```bash
> manifest="/home/taximeter/backups/privacy-restore-$(date +%F-%H%M%S).json"
> $compose exec -T web python manage.py export_privacy_restore_manifest "$manifest"
> # Если команда запускается внутри контейнера, путь должен быть на bind-mounted
> # защищённом backup-контуре; иначе экспортировать через одноразовый контейнер
> # в host-mounted path.
> chmod 600 "$manifest"
> ```

```bash
ls -t /home/taximeter/backups/proff58/pre-migrate-*.sql.gz | head   # выбрать нужный
$compose stop web web-b frontend celery celery-onec celery-beat     # отсоединить писателей/HTTP
$compose exec -T db psql -U "$POSTGRES_USER" -d postgres \
    -c "DROP DATABASE \"$POSTGRES_DB\" WITH (FORCE);" \
    -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";"
gunzip -c <pre-migrate-файл> | $compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

# Обязательный privacy reconciliation ДО старта внешних сервисов.
$compose run --rm web python manage.py reconcile_privacy_restore "$manifest"

# Только после успешного reconciliation:
$compose up -d
```

Не откатывать базу без отдельного решения.
