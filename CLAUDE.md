# CLAUDE.md

Указания и карта репозитория для Claude Code при работе над проектом
«Профессионал». Подробные контракты — в `docs/` и `README.md`; здесь — рабочий
справочник, чтобы быстро ориентироваться и не нарушать границы модулей.

## Общение
- Вести общение с командой **только на русском языке**.

---

## 1. Что это за проект

«Профессионал» — кастомная e-commerce-платформа (B2B + B2C) для магазина
электро/ручного инструмента с доставкой по Пензе и области. Backend на Django,
витрина-фронт на Next.js, интеграция с учётной системой **1С 7.7**.

Ключевые принципы (см. `README.md`, `docs/ARCHITECTURE.md`):

- **Catalog-first.** Каталог (дерево категорий + EAV-характеристики) — критический
  путь. Большая часть логики и тестов — в `apps/catalog`.
- **1С — источник истины** по цене, остатку и коду номенклатуры. **Сайт — мастер
  по контенту** (витринные названия, категории, характеристики, фото, описания,
  публикация). Связь — по `code_1c` / артикулу. Обмен **никогда** не перезаписывает
  контент сайта из 1С.
- **Граница важнее реализации.** Модули общаются через сервисный слой (`services.py`)
  синхронно и через доменные события (`apps/core/events.py`) асинхронно. Запрещено
  лазить в чужие таблицы (`OtherApp.models.X.objects...` из чужого приложения).
- **Feature-флаги в `core`** включают/выключают модули — это фундамент
  переиспользуемого движка (см. `apps/core/features.py`).

## 2. Стек

- **Backend:** Django 5.0 + Django REST Framework 3.15
- **БД:** PostgreSQL 16 (используются JSONB-фасеты + GIN + pg_trgm — **SQLite не
  подойдёт даже для тестов**)
- **Очереди/кэш:** Celery 5 + Redis (worker `celery` + worker `onec` + beat)
- **Фронт:** Next.js (App Router, TypeScript, Tailwind) — каталог `frontend/`
- **Качество:** ruff + black + pre-commit; CI на GitHub Actions
- **Админка:** django-jazzmin; дерево категорий — django-treebeard (MP_Node)

## 3. Структура репозитория

```
config/                 # Django-проект
  settings/             #   base.py / dev.py / prod.py (env-driven через django-environ)
  celery.py, urls.py, wsgi.py, asgi.py
apps/
  core/                 # ядро: события (events.py), фичефлаги (features.py), health, TimeStampedModel
  accounts/             # кастомный User (вход по телефону/e-mail), Profile, роли B2C/B2B
  catalog/              # ★ каталог: Category(MP_Node), Product, Attribute/EAV, фасеты, поиск, импорт-пайплайн
  pricing/              # цены (PriceRecord), ADR-0006; price_for() — единая точка расчёта цены
  orders/              # Order/OrderItem/Cart, 3 оси статусов, матрица переходов (transitions.py)
  sync_1c/              # ★ интеграция с 1С: API, импорт, заказы, Celery-задачи
  ai/                   # AI-слой за адаптером (рекомендации; assist — каркас под V2)
requirements/           # base.txt / dev.txt / prod.txt
docs/                   # ARCHITECTURE.md, 1c-api-spec.md, 1c-developer-task.md, order-lifecycle.md, adr/
frontend/               # Next.js витрина (своя CLAUDE.md и README)
scripts/                # smoke_1c.py (контракт-проверка 1С API), backup.sh
tests/                  # кросс-модульные regression/smoke тесты
docker-compose.yml      # dev: db, redis, web, celery, celery-onec, celery-beat
docker-compose.prod.yml # prod-стек (+ nginx, см. docker/nginx, docs/DEPLOY.md)
```

## 4. Слои и границы (правило зависимостей)

Зависимости направлены строго вниз (`docs/ARCHITECTURE.md` §2):

```
Слой 4  Интеграции   → sync_1c (знает обо всех, о нём — никто; вызывается по сигналам/Celery)
Слой 3  AI           → ai (за адаптером ai/services.py)
Слой 2  CRM          → (каркас, по мере)
Слой 1  Магазин      → catalog · pricing · orders
Слой 0  Ядро         → core · accounts
```

- Ядро не зависит ни от кого. Магазин зависит только от ядра.
- Магазин **не знает** о CRM/AI/интеграциях — общается с ними через сигналы.
- `sync_1c` — единственное место, где встречаются 1С и каталог; каталог про 1С не знает.

**Доменные события** (`apps/core/events.py`, Django Signals): `user_registered`,
`b2b_verified`, `product_created/updated`, `order_created`, `order_paid`,
`order_status_changed`, `payment_succeeded/failed`, `price_changed`. Издавать —
через `transaction.on_commit` с идентификаторами/снимком в payload (подписчик
читает закоммиченные данные).

## 5. Интеграция с 1С (`apps/sync_1c`) — ключевая зона

Направление обмена: **1С сама стучится к сайту** (push). Сайт ничего не забирает
из 1С напрямую. Авторизация — заголовок `X-Api-Key` (сверяется за константное время
с `settings.ONEC_API_KEY`; пусто на сервере ⇒ API закрыт).

Контракты: **`docs/1c-api-spec.md`** (для интегратора 1С, финальный контракт) и
`docs/1c-developer-task.md`. Эндпоинты под префиксом `/api/1c/`:

| Эндпоинт | Метод | Назначение | Ответ |
|---|---|---|---|
| `snapshot/` | GET | снимок позиций (code_1c+цена+остатки) для дельта-обмена; offset/keyset пагинация | 200 |
| `products/import` | POST | загрузка/создание номенклатуры (**асинхронно**) | 202 + `batch_uid` |
| `products/update` | POST | обновление существующих (новые не создаются, **асинхронно**) | 202 + `batch_uid` |
| `sync/<batch_uid>` | GET | опрос статуса фонового импорта | 200 / 404 |
| `prices/update` | POST | только цены (**синхронно**) | 200 + счётчики |
| `stocks/update` | POST | только остатки (**синхронно**) | 200 + счётчики |
| `orders/new` | GET | 1С забирает новые заказы (`sync_1c_status=pending`) | 200 + items |
| `orders/confirm` | POST | подтверждение приёма/резерва + движение `fulfillment_status` | 200 + per-item |

Важные детали реализации:

- **Кодировка.** 1С 7.7 шлёт/читает **Windows-1251**. Вход — `api/parsers.OneCJSONParser`
  (UTF-8 → CP1251), выход — `api/renderers.OneCJSONRenderer` (всегда cp1251). Любой
  свой HTTP-клиент к этому API должен декодировать ответ так же (иначе кириллица в
  `detail`/ошибках «ломается»).
- **Конверт** всегда `{"items": [...]}`, непустой, ≤ `ONEC_MAX_ITEMS` (1000). Числа —
  строкой или числом, точка/запятая; булево — `true/false`, `1/0`, `"да"/"нет"`.
- **Идемпотентность.** Матчинг по `external_id`/`code_1c`, затем `sku`/`article`.
  Повторная отправка дублей не создаёт. Неизменившаяся цена → `skipped` (#111).
- **Асинхронный импорт.** `products/import|update` ставятся в Celery-очередь `onec`
  (worker `-c 1` — строго последовательно, без гонки «одна актуальная цена», #126).
  Зависшие RUNNING-прогоны добивает janitor `mark_stale_syncs` (#57).
- **Заказы реализованы (#50)** — это НЕ заглушки 501 (старые упоминания 501 в коде/доках
  устарели; актуально — заказы работают). Логика — в `use_cases.py`
  (`export_new_orders`, `confirm_orders`). `orders/new` не меняет `sync_1c_status`
  (at-least-once: заказ остаётся `pending`, пока 1С не подтвердит приём).

Карта файлов `sync_1c`: `api/` (views, serializers, permissions, parsers, renderers,
urls) · `use_cases.py` (оркестрация) · `normalizers.py` · `matching.py` ·
`product_writer.py` · `pricing.py` · `stock.py` · `bulk_import.py` · `importer.py` ·
`parsers.py` (файловый импорт) · `tasks.py` (Celery) · `models.py`
(`NomenclatureStaging`, `StockRecord`, `SyncLog`).

### Проверка работоспособности 1С-обмена

```bash
# Контракт-smoke живого API (HTTP, только stdlib; ПИШЕТ в БД — только staging!)
python scripts/smoke_1c.py --base https://dev.proff58.ru --key <ONEC_API_KEY>
python scripts/smoke_1c.py --base http://127.0.0.1:8000 --key <ключ>   # против локали

# Демо/симулятор полного round-trip обмена заказами (играет роль 1С, без HTTP)
python manage.py demo_1c_orders                       # confirmed + резерв
python manage.py demo_1c_orders --scenario reserve-failed
python manage.py demo_1c_orders --scenario shipped    # new→confirmed→ready→shipped
python manage.py demo_1c_orders --keep                # не удалять демо-заказ
```

## 6. Модель статусов заказа (3 независимых оси)

Источник истины — `docs/order-lifecycle.md`. Оси (`apps/orders/models.py`):

| Ось | Поле | Кто двигает |
|---|---|---|
| Обработка | `fulfillment_status` | 1С / менеджер / кладовщик (forward-only, матрица в `orders/transitions.py`) |
| Оплата | `payment_status` | сайт (ЮKassa / менеджер) — **1С не трогает** |
| Выгрузка в 1С | `sync_1c_status` | сайт (`exported`, когда 1С подтвердила приём) |

Производный человекочитаемый статус — `Order.display_status`. Заказ хранит **снимки**
(покупатель, строки, цена) — данные не «плывут» при изменении товара/цены.

## 7. Локальный запуск

### Через Docker (рекомендуется)
```bash
cp .env.example .env
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```
Сайт: http://localhost:8000 · Админка: http://localhost:8000/admin/

### Без Docker
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env                 # DATABASE_URL → localhost:5432
python manage.py migrate
python manage.py runserver
```

В dev (`config/settings/dev.py`): `DEBUG=True`, `ALLOWED_HOSTS=["*"]`, e-mail в
консоль, **Celery работает inline** (`CELERY_TASK_ALWAYS_EAGER=True`) — Redis/worker
для большинства задач не нужны (healthcheck `/healthz/` всё равно проверяет Redis и
вернёт 503 без него — это норма для локалки).

Ключевые env (см. `.env.example`): `DATABASE_URL`, `CELERY_BROKER_URL`,
`ONEC_API_KEY` (пусто = 1С-API закрыт), `ONEC_MAX_ITEMS`, `FEATURE_*`.

## 8. Тесты

Тестам **нужен PostgreSQL** (JSONB/GIN/trgm). Подключение по `DATABASE_URL`
(дефолт `localhost:5432`).

```bash
docker compose up -d db          # поднять только Postgres
pytest                           # из venv; --reuse-db включён в pyproject
pytest apps/sync_1c              # только 1С
docker compose run --rm web pytest   # альтернатива: всё внутри контейнера
```

`config.settings.dev` — настройки тестов (см. `pyproject.toml`). Тестов > 540;
покрытие 1С (≈109 в `apps/sync_1c`) и заказов — подробное.

## 9. Полезные management-команды

- **1С/обмен:** `import_1c`, `apply_stocks_1c`, `mark_stale_syncs`, `demo_1c_orders`
- **Каталог (импорт/обогащение):** `import_products`, `bootstrap_catalog`,
  `build_categories`, `load_tool_types`, `load_attributes`, `enrich_attributes`,
  `enrich_tool_type`, `publish_catalog`, `rebuild_attrs_cache`, `attribute_coverage`,
  `analyze_subgroup`, `tool_type_gaps`, `backfill_option_slugs`

(скилл `characterize-subgroup` помогает расставлять характеристики подгрупп каталога.)

## 10. Публичные API (для фронта)

- `/api/catalog/` — `categories/`, `categories/<slug>/facets/`, `products/`,
  `products/<slug>/`, `products/<slug>/compatible/`, `search/suggest/`
- `/api/ai/products/<slug>/recommendations/`
- `/api/` — `cart/`, `cart/items/`, `orders/`, `orders/<number>/`
- `/api/1c/` — обмен с 1С (см. §5)
- `/healthz/` — health (БД + Redis)

## 11. Поток работы и стиль

- Ветки: `main` (прод), `dev` (интеграция). Рабочие — от `dev`:
  `feature/<area>-<кратко>`, `fix/...`, `chore/...`, `design/...`. PR в `dev`
  (1 ревью + зелёный CI). **Коммиты — Conventional Commits** (`feat:`, `fix:`,
  `chore:`, `docs:`, `test:`).
- **Стиль кода:** ruff + black (line-length 100), `pre-commit` настроен
  (`.pre-commit-config.yaml`). Хук Claude `format-python.sh` гоняет ruff+black после
  правок `.py`. Миграции — исключены из линта.
- **CI:** `.github/workflows/ci.yml` (PR) → `tests.yml`; `deploy.yml` катит
  staging (push в `dev`) / production (push в `main`) после зелёных тестов.

> Текущая рабочая ветка задаётся заданием сессии. Не пушить в чужие ветки без
> явного разрешения. PR не создавать, пока не попросили.

## 12. Внешние наборы Claude Code
Подключённые плагины, агенты и скиллы (superpowers, ECC, gstack, agency-agents)
описаны в [`.claude/EXTRAS.md`](.claude/EXTRAS.md): что включено и как активировать
наборы «по запросу». Для фронта — отдельная `frontend/CLAUDE.md`.
