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
docker compose -f docker-compose.prod.yml logs web --tail=100
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

```bash
cd /home/taximeter/proff58-prod
git log --oneline -5
git checkout <previous-good-commit>
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

Если проблема в миграции данных, сначала оценить обратимость миграции и наличие свежего бэкапа. Не откатывать базу без отдельного решения.
