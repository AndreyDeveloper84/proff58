# PROD-ENV-01 — отделение production (`main`) от staging (`dev`): аудит и дизайн

**Дата:** 2026-09-21 · **Режим:** read-only, топология не менялась · **Основание:** OWNER DECISION
PF-SH-RELEASE-01 §27–§28.

## Зачем

После открытия индекса (PF-SH-RELEASE-01) `proff58.ru` индексируется, а обслуживает его стек, который
деплоится при каждом merge в `dev`. Любой merge в `dev` сразу попадает на индексируемый сайт.
Цель: `dev` → staging, `main` → production `proff58.ru`.

## Текущее состояние (факты)

| Компонент | Сейчас |
|---|---|
| GitHub Actions | `deploy.yml`: push в `dev` → environment `staging`, push в `main` → environment `production`. Оба environment существуют. Последний деплой `main` — 2026-06-17 (`fb35c5d`), успешный |
| Compose | Одна и та же `docker-compose.prod.yml` для обеих сред. Среды разделены только `DEPLOY_PATH` (секрет environment) и `.env` в каталоге |
| Каталоги на VPS | `~/proff58-staging` (живой, HEAD = `dev`); `~/proff58-prod` — checkout `fb35c5d` (PR #69, июнь), **контейнеры не запущены** |
| `COMPOSE_PROJECT_NAME` | staging `proff58_staging`, prod `proff58_prod` |
| Порт стек-nginx | `127.0.0.1:${WEB_HTTP_PORT}`: staging 8082, prod 8081 (не слушается) |
| Хостовый nginx | `proff58.ru` → `127.0.0.1:8082` (**staging**); `dev.proff58.ru` → 301 на `proff58.ru` |
| БД | Существует **только** том `proff58_staging_pgdata`. Томов `proff58_prod_*` нет. Старые дампы prod: `~/backups/prod_20260415…`, `prod_20260506`, `prod_20260514` |
| Redis | Свой контейнер на стек (`redis` в compose), не общий |
| Media / static | Именованные тома с префиксом проекта — у каждого стека свои. Все фото каталога (1 125 ProductImage) — в `proff58_staging_media_volume` |
| Образы | web / celery собираются в образы с префиксом проекта — раздельные. **Витрина — один тег `proff58-frontend:latest` на хост**: `docker load` из любой среды перезаписывает образ, который использует другая |
| Секреты | Раздельные GitHub Environments; `.env` у каждого каталога свой (в prod `.env` есть DB/SECRET_KEY/ONEC_API_KEY, но нет `SITE_URL`, `SSR_INTERNAL_TOKEN`, `SEO_INDEXING`) |
| 1С | `ONEC_API_KEY` задан в обоих `.env`, но 1С стучится в `proff58.ru` → пишет в staging-БД (`sync_1c_stockrecord` 47 226 записей, обновление 2026-09-19; `sync_1c_synclog` 1 242) |
| Заказы / платежи / пользователи | В staging-БД: 3 / 3 / 4 — похоже на тестовые |
| Бэкапы | cron 03:30 только для staging (`~/backups/staging`, 60 дней) |
| Миграции | `docker/release.sh` (pg_dump + migrate) в каждой среде на своей БД |

## Вывод

1. **Одна живая БД.** Staging и production не делят БД — prod-БД просто нет. Вся курированная за
   месяцы работа с каталогом (типы, характеристики, фото, allowlist индексации) и обмен с 1С живут в
   `proff58_staging_pgdata`. Фактически это production-данные под именем staging.
   **→ MIGRATION BLOCKER:** production нельзя «поднять из main»: чистая или июньская prod-БД потеряла бы
   каталог. Нужен перенос данных.
2. **Общий образ витрины** (`proff58-frontend:latest`) — **ISOLATION BLOCKER.** Два стека на одном хосте с
   одним тегом: деплой `dev` подменит витрину production при её следующем пересоздании.
3. **Внешние интеграции** (1С, ЮKassa/AtolPay webhooks, MAX webhook) смотрят на `proff58.ru`. Переключение
   хоста на prod-стек переносит их автоматически, но только если prod-БД к этому моменту содержит актуальные
   данные (иначе 1С начнёт писать в «пустую» базу, а заказы разойдутся).
4. **Индексация привязана к хосту, а не к стеку.** Код (PR #793) открывает robots только при
   `SEO_INDEXING=production` и Host = `proff58.ru`. После переезда флаг переносится в prod `.env`,
   staging-стек на другом хосте остаётся закрыт сам.

## Дизайн (предложение, не выполнено)

**Целевая топология:** `proff58.ru` → prod-стек (`main`, порт 8081); `dev.proff58.ru` → staging-стек
(`dev`, порт 8082, `SEO_INDEXING=off`, отдельная копия данных).

**Порядок (каждый шаг — отдельный GO):**

1. **Изоляция образа витрины (код).** Тег по среде: `proff58-frontend:${COMPOSE_PROJECT_NAME}` (или
   `:staging` / `:prod`) в `deploy.yml` и `docker-compose.prod.yml`. Без этого второй стек поднимать нельзя.
2. **Prod `.env`.** Добавить `SITE_URL=https://proff58.ru`, `SSR_INTERNAL_TOKEN` (новый секрет),
   `SEO_INDEXING=off` (включается только после проверок), сверить остальные ключи со staging.
3. **Выравнивание `main`.** `main` отстаёт от `dev` на всё с июня: сначала PR `dev` → `main` и зелёный
   деплой prod-стека с **пустым трафиком** (хост ещё смотрит на staging).
4. **Перенос данных (окно обслуживания):**
   заморозить обмен 1С → `pg_dump` staging → restore в `proff58_prod_pgdata` → копия media-тома
   → `release.sh` (migrate) → сверка счётчиков (Product, PAV, ProductImage, allowlist 74, заказы) →
   переключить хостовый nginx `proff58.ru` → 8081 → проверить 1С и платежи → разморозить 1С.
5. **Staging на свой хост.** `dev.proff58.ru` → 8082 (без 301 на `proff58.ru`), `SEO_INDEXING=off`.
   С этого момента staging-БД — копия, не источник истины: писать каталог на staging нельзя.
6. **Бэкапы prod.** Cron для `~/proff58-prod`, отдельный каталог и срок хранения.
7. **Процесс.** Каталожные операции (гейт-циклы, apply фото/характеристик, allowlist) идут на prod-БД
   с тем же протоколом (дамп → snapshot → sha → apply → verify); `dev` → `main` — по релизам.

**Откат переезда:** хостовый nginx `proff58.ru` обратно на 8082 (staging-стек и его БД остаются нетронутыми
до подтверждения prod) — минуты.

## Решения, нужные от владельца

1. Окно обслуживания для переноса (1С и приём заказов на 15–30 минут в паузе).
2. Где делать каталожную работу после разделения — только prod-БД (рекомендую) или staging с синхронизацией.
3. Нужен ли staging публично (`dev.proff58.ru` с Basic-auth) или только локально.
4. Порядок относительно BURY: переезд не пересекать с apply фото `bury` (одно окно — одна операция).
