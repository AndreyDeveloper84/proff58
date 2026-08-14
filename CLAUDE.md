# CLAUDE.md

Рабочий справочник Claude Code по проекту «Профессионал»: границы модулей и
инварианты, которые нельзя нарушать. Подробности — по ссылкам в `docs/`.

## Общение
- Вести общение с командой **только на русском языке**.

---

## 1. Проект и принципы

«Профессионал» — кастомная e-commerce-платформа (B2B + B2C) для магазина
электро/ручного инструмента (Пенза и область). Django + DRF, витрина на Next.js,
интеграция с **1С 7.7**. Код — переиспользуемый движок, «Профессионал» — первый
инстанс.

- **Catalog-first.** Каталог (дерево категорий + EAV-характеристики) — критический
  путь; большая часть логики и тестов в `apps/catalog`.
- **1С — источник истины** по цене, остатку и `code_1c`. **Сайт — мастер по
  контенту** (названия, категории, характеристики, фото, публикация). Обмен
  **никогда** не перезаписывает контент сайта из 1С (ADR-0007).
- **Граница важнее реализации.** Модули общаются через `services.py` (синхронно) и
  доменные события `apps/core/events.py` (асинхронно). Запрещено читать чужие
  таблицы (`OtherApp.models.X.objects...` из чужого приложения).
- **Feature-флаги в `core`** (`apps/core/features.py`) включают/выключают модули.
- **AI — не источник истины**: управляемое обогащение поверх детерминированного ядра.

Ключевые документы: `README.md`, `docs/ARCHITECTURE.md`, `docs/ARCHITECTURE-AI.md`,
`docs/PROJECT-INDEX.md`.

## 2. Стек

Django 5.0 · DRF 3.15 · **PostgreSQL 16** (JSONB-фасеты + GIN + pg_trgm — **SQLite не
подойдёт даже для тестов**) · Celery 5 + Redis (worker `celery` + worker `onec` +
beat) · Next.js App Router/TS/Tailwind (`frontend/`) · ruff + black (line-length 100)
+ pre-commit · django-jazzmin, django-treebeard (MP_Node).

## 3. Структура репозитория

```
config/                 # settings (base/dev/prod, django-environ), celery, urls
apps/
  core/ accounts/                    # слой 0: события, фичефлаги, health, User/Profile
  catalog/ pricing/ orders/          # слой 1: каталог, цены (ADR-0006), заказы/корзина
  payments/ delivery/                # ЮKassa/инвойсы; методы, зоны, DeliverySlot
  notifications/ integration_max/    # каналы уведомлений; MAX webhook и уведомления
  integration_ship/ content/ reviews/
  ai/                                # слой 3: enrichment/sourcing за адаптером
  sync_1c/                           # слой 4: обмен с 1С
  crm_*/ analytics/ leads/           # включаются по мере роста
data/catalog_processing_rules/       # артефакты контура распознавания (см. §7)
docs/                   # ARCHITECTURE, 1c-api-spec, order-lifecycle, adr/, catalog/, plans/
frontend/ scripts/ tests/ requirements/
docker-compose.yml · docker-compose.prod.yml
```

## 4. Слои и границы (правило зависимостей)

Зависимости строго вниз (`docs/ARCHITECTURE.md` §2):

```
Слой 4  Интеграции   → sync_1c (знает обо всех, о нём — никто)
Слой 3  AI           → ai (за адаптером ai/services.py)
Слой 2  CRM          → каркас
Слой 1  Магазин      → catalog · pricing · orders · payments · delivery
Слой 0  Ядро         → core · accounts
```

Магазин не знает о CRM/AI/интеграциях — только сигналы. `sync_1c` — единственное
место, где встречаются 1С и каталог; каталог про 1С не знает.

События (`apps/core/events.py`): `user_registered`, `b2b_verified`,
`product_created/updated`, `order_created`, `order_paid`, `order_status_changed`,
`payment_succeeded/failed`, `price_changed`. Издавать через `transaction.on_commit`
с идентификаторами/снимком в payload.

## 5. Интеграция с 1С — кратко

Контракт: **`docs/1c-api-spec.md`** (финальный, для интегратора) и
`docs/1c-developer-task.md`. Что нельзя забывать:

- **1С сама стучится к сайту** (push, префикс `/api/1c/`), авторизация `X-Api-Key`;
  пустой `ONEC_API_KEY` на сервере ⇒ API закрыт.
- **Кодировка Windows-1251** на входе и выходе (`api/parsers.py` / `api/renderers.py`);
  свой HTTP-клиент обязан декодировать так же.
- Конверт всегда `{"items": [...]}`, непустой, ≤ `ONEC_MAX_ITEMS` (1000).
- Идемпотентность: матчинг `external_id`/`code_1c`, затем `sku`/`article`.
- `products/import|update` — асинхронно через очередь `onec` (worker `-c 1`,
  строго последовательно); `prices/update`, `stocks/update` — синхронно.
- **Заказы реализованы** (`use_cases.py`), это не заглушки 501; `orders/new` не меняет
  `sync_1c_status` (at-least-once до подтверждения от 1С).
- Проверка живого API: `python scripts/smoke_1c.py --base <url> --key <ключ>`
  (**пишет в БД — только staging**); симулятор round-trip: `manage.py demo_1c_orders`.

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
| `sales/upload` | POST | продажи магазина за день (источник «Хитов продаж», **синхронно**) | 200 + счётчики |

## 6. Статусы заказа

Три независимые оси (`docs/order-lifecycle.md` — источник истины):
`fulfillment_status` (двигают 1С/менеджер/кладовщик, forward-only по
`orders/transitions.py`), `payment_status` (только сайт, 1С не трогает),
`sync_1c_status` (выгрузка в 1С). Производный статус — `Order.display_status`.
Заказ хранит **снимки** покупателя, строк и цены.

## 7. Каталог: контур распознавания `tool_type` (текущая рабочая зона)

Детерминированный rules-engine, предлагающий `tool_type` для товаров из 1С.

⚠️ **Две таксономии каталога** (дерево сайта vs 1С-таксономия в ключах
`data/tool_type_rules.json`) расходятся по именам верхних категорий и ломают
`enrich_tool_type` — карта соответствия и грабли в [`docs/catalog_trees.md`](docs/catalog_trees.md).
С PR #628 часть расхождений закрыта слоем алиасов (`apps/catalog/tool_type_aliases.py`),
но **только в `--dry-run`/`--report-only`**; боевая запись (`_handle_write`) алиасы
не применяет и ведёт себя как раньше.

| Артефакт / модуль | Роль |
|---|---|
| `data/catalog_processing_rules/tool_type_taxonomy.v1.json` | **canonical manifest**, 328 options — единственный источник правды по словарю типов |
| `apps/catalog/taxonomy_manifest.py` | загрузка/валидация манифеста, оба хэша |
| `data/.../tool_type.v2.json` | default ruleset (v2 promoted, Phase 7D Stage 5); `.v1.json` — исторический |
| `data/.../applied_corpus_tool_type.v1.json` | applied corpus (54 items), из него выведены правила |
| `apps/catalog/rules_engine.py` | matcher: `load_ruleset`, `load_corpus`, `evaluate_product` |
| `apps/catalog/rules_gate.py` | **independent gate 2.0** — пересчитывает всё, declared-полям не доверяет |
| `apps/catalog/rules_release.py` | release manifest — детерминированная версия контура (входы + хэши + метрики пройденного gate) |
| `data/.../rules_release_manifest.v1.json` | зафиксированная версия контура; CI сверяет `--check` |
| `apps/catalog/tool_type_rollback.py` | откат применённого `tool_type`: снимок → план (`noop`/`write`/`conflict`) → запись одной транзакцией + post-audit |
| `apps/catalog/taxonomy_reverse.py` | reverse-map манифеста `N → N-1`: план понижения, fail-closed при неоднозначном откате |

Команды: `catalog_rules_shadow` (proposal-only прогон), `catalog_rules_gate_validate`
(gate, exit 0/1/2/3), `catalog_rules_release_manifest` (release manifest: генерация
и `--check`), `catalog_taxonomy_reconcile` (read-only дрейф манифест↔БД),
`load_tool_types` (seed из манифеста: fail-closed, no-delete),
`catalog_tool_type_snapshot` / `catalog_tool_type_rollback` (откат применённого,
dry-run по умолчанию), `catalog_taxonomy_downgrade` (понижение версии словаря).

CI-джоба `catalog-rules-gate` (`.github/workflows/tests.yml`) гоняет gate на
замороженном 7D sample против default ruleset + `release_manifest --check`; exit
code команды = статус джобы.

**Инварианты:**
- Опции `tool_type` создаются **только** из манифеста; `enrich_tool_type` и
  `backfill_option_slugs` не создают типы вне манифеста.
- Gate не доверяет самодекларированным полям артефактов — всё пересчитывается
  (`docs/catalog/rules-gate-h2.md`).
- `taxonomy_identity_hash` = `ddf4b949…` (canonical; с ТТ-18A
  2026-08-05 — 360 options, новый тип `tsangi-i-tsangovye-patrony`
  (`Цанги и цанговые патроны`) и переименование `svar-cangi`:
  `Цанги` → `Цанги сварочные`;
  до этого `f7b73846…` TT-NEW-TYPES-BATCH-3 2026-08-01 — 359 options,
  пакет из 4 типов P2: `drovokoly`, `hoz-motygi`, `zerkala-dosmotrovye`,
  `zap-ognetushiteley`;
  до этого `8eba9631…` TT-NEW-TYPES-BATCH-2 — 355 options, пакет из 10 типов:
  `shtifty`, `nabory-uplotnitelnyh-kolets`, `nagruzochnye-vilki`,
  `krepleniya-ognetushiteley`, `kompressometry`, `zap-tarelki-opornye`,
  `prosekateli-profiley-gkl`, `shilya`, `izm-shchupy`, `siz-kremy-zashchitnye`;
  `voronki` не создан — дубликат `hoz-voronki` из TT-14;
  до этого `ea65486c…` TT-NEW-TYPES-BATCH — 345 options, `7ac7a9a2…` TT-14 —
  336 options, `887eea5d…` TT-07 — 334 options, `524d4e31…` TT-01, `fc13be78…`). Legacy DB-order hash
  `b357be60…` допустим только явным `--allow-legacy-taxonomy-hash` и в штатном
  контуре не используется: с Wave 7.1 H4 замороженный gate-sample перевыпущен на
  canonical binding, CI гоняет гейт без поблажки.
- Shadow-контур **ничего не пишет в БД**; apply — отдельная авторизация.
- **Карантин характеристик** (`data/attribute_quarantine.json`) запрещает
  `enrich_attributes` писать значения по товару/оси, но **никогда не удаляет уже
  записанные PAV** — гейт стоит в команде ДО prune-цикла, иначе строка в реестре
  молча стирала бы данные; уборка старого — отдельная команда. Реестр
  валидируется fail-closed (неизвестный `product_id` или ключ записи = отказ
  прогона), запись не удаляется — снятие только через `status: "lifted"`
  (`docs/catalog/attribute-quarantine.md`).
- Откат `tool_type` исполняется **парой снимков** (`--from` ожидаемое текущее,
  `--to` цель): live вне обоих состояний → `conflict`, а не молчаливая перезапись;
  план с любым конфликтом не применяется целиком (`docs/catalog/tool-type-reverse-migration.md`).
  Сверка baseline делается **дважды** — при построении плана и повторно внутри
  транзакции записи под `SELECT … FOR UPDATE` (H6), потому что план строится вне
  этой транзакции; чужая запись, прошедшая между планом и применением, даёт
  conflict, а не перезапись.
- **`WAVE 7.1 ACCEPTED` — объявлено владельцем 2026-07-27.** Заморозка Phase 8 снята,
  основание — сводный отчёт волны `docs/plans/2026-07-27-WAVE7_1_ACCEPTANCE_REPORT.md`.
  Phase 8 (pilot rollout) идёт ступенями из
  `docs/plans/2026-07-16-CATALOG_RESEARCH_QUEUE_ROADMAP.md` §Phase 8, **порядок менять
  нельзя**: synthetic batch (5 фиктивных cases) → real batch 10 (только dry-run) →
  real batch 20 (findings + ручная модерация) → batch 50 → после quality gate остальные
  товары в наличии → товары без остатка. Один batch первой версии — не более 20–30
  товаров, **одна ступень = одно окно**.

Документы: **план текущей волны — `docs/plans/2026-07-26-WAVE7_1_H3_H5_PLAN.md`**,
`docs/catalog/tool-type-taxonomy-manifest.md`, `docs/catalog/rules-gate-h2.md`,
`docs/catalog/rules-release-manifest.md`, `docs/catalog/tool-type-reverse-migration.md`,
`docs/plans/2026-07-*PHASE7*`; протоколы стадий — `scratchpad/wave7/wave7-h*-report.md`.

Общий playbook изменений каталога (gate-cycle: read-only → preflight → dry-run →
pg_dump → write → post-audit) — `docs/catalog/operations/README.md`.

## 8. Запуск и тесты

```bash
docker compose up --build        # весь стек; либо: docker compose up -d db
docker compose exec web python manage.py migrate
pytest                           # нужен PostgreSQL; --reuse-db включён в pyproject
pytest apps/catalog              # только каталог (~350 тестов)
```

В dev (`config/settings/dev.py`): `DEBUG=True`, Celery inline
(`CELERY_TASK_ALWAYS_EAGER=True`), e-mail в консоль; `/healthz/` без Redis вернёт
503 — для локалки норма.

**Baseline полного прогона: `2 failed, 2615 passed, 1 skipped` (~17 мин), замер
2026-08-05.** Перечисленные падения — окружение, не регрессия:
`test_regression_mvp.py::test_healthcheck_returns_ok` (нет Redis) и
`test_deploy_release.py::test_release_script_is_executable` (Windows exec bit).
Любое падение сверх перечисленных — регрессия.

Ключевые env (`.env.example`): `DATABASE_URL`, `CELERY_BROKER_URL`, `ONEC_API_KEY`,
`ONEC_MAX_ITEMS`, `FEATURE_*`.

## 9. Management-команды каталога

- **Импорт/структура:** `import_products`, `bootstrap_catalog`, `catalog_build_section`,
  `catalog_build_skeleton`, `catalog_taxonomy_apply`, `catalog_v2_swap`, `publish_catalog`
- **Типы и атрибуты:** `load_tool_types`, `load_attributes`, `enrich_attributes`
  (флаг `--quarantine` — реестр карантина), `enrich_tool_type`,
  `backfill_option_slugs`, `rebuild_attrs_cache`,
  `catalog_attribute_cleanup_quarantine` (удаление ранее записанного по
  карантинным товарам; dry-run по умолчанию, `--apply` требует `--snapshot`)
- **Аудит:** `catalog_taxonomy_audit`, `catalog_taxonomy_reconcile`, `attribute_coverage`,
  `coverage_report`, `tool_type_gaps`, `analyze_subgroup`, `catalog_v2_report`,
  `discover_missing_rules` (read-only: какое правило характеристик писать
  следующим — Rule Impact Score и статусы вида `CREATE_RULE` /
  `BLOCKED_BY_CLASSIFICATION`; см. `docs/catalog/discover-missing-rules.md`)
- **Откат и обратимость (H5):** `catalog_tool_type_snapshot`, `catalog_tool_type_rollback`,
  `catalog_taxonomy_downgrade`
- **Очередь исследования:** `catalog_queue_create|export|import|status|finalize`
- **1С/обмен:** `import_1c`, `apply_stocks_1c`, `mark_stale_syncs`, `demo_1c_orders`

Скилл `characterize-subgroup` — плейбук расстановки характеристик подгрупп.

## 10. Публичный API

- `/api/catalog/` — `categories/`, `categories/<slug>/facets/`, `products/`,
  `products/<slug>/`, `products/<slug>/compatible/`, `search/suggest/`,
  `bestsellers/` (товары с реальными продажами за окно — см. `apps/catalog/sales.py`)
- `/api/ai/products/<slug>/recommendations/`
- `/api/` — `cart/`, `cart/items/`, `orders/`, `orders/<number>/`
- `/api/1c/` — обмен с 1С (см. §5)
- `/healthz/` — health (БД + Redis)

## 11. Поток работы и стиль

- Ветки: `main` (прод), `dev` (интеграция); рабочие — от `dev`:
  `feature/<area>-<кратко>`, `fix/…`, `chore/…`, `design/…`. PR в `dev` (1 ревью +
  зелёный CI). **Коммиты — Conventional Commits.**
- Стиль: ruff + black (line-length 100), `pre-commit`; миграции исключены из линта.
- CI: `.github/workflows/ci.yml` → `tests.yml`; `deploy.yml` катит staging (push в
  `dev`) / production (push в `main`).

> Рабочая ветка задаётся заданием сессии. Не пушить в чужие ветки без явного
> разрешения. **Push и PR — только по явной просьбе.**

## 12. Внешние наборы Claude Code

Плагины, агенты и скиллы (superpowers, ECC, gstack, agency-agents) — в
[`.claude/EXTRAS.md`](.claude/EXTRAS.md). Для фронта — отдельная `frontend/CLAUDE.md`.
