# Phase 5 — staging-пилот catalog processing pipeline

Статус: **принят и закрыт** (2026-07-18). Pipeline research queue → import →
moderation → apply прошёл end-to-end на staging; каталог изменён строго в
утверждённом объёме (15 значений `tool_type`). Run завершён со
`status=completed` (`outcome=completed_with_review`); состояние пилота
проверено на `dev@da6919c` до docs-only follow-up.

## Идентификаторы

- Run UUID: `f7fe5b29-9e2c-4dfb-898c-22859a0dcf35`
- Idempotency key run: `phase5-staging-20260718-v1` (kind=research, mode=tool_type)
- Код пилота: `dev@7b24aae` (PR #533 — processing foundation + research queue,
  PR #534 — fix перехода `review` → `needs_review`); закрытие: `dev@da6919c`
  (PR #535 — regression-тест identity guard, PR #536 — `catalog_queue_finalize`,
  PR #537 — первоначальный отчёт, PR #538 — фиксация закрытия)
- Export checksum (SHA-256): `4ca129e595fa5ddccd3e3b979d573854fbea4221558d20985a0cb61b63e5fb29`
- Result checksum (SHA-256): `a2ec6286f8f624b5c04a00d0bf3c4da596d80edfd3873e2c77f223c2fb7d1dc8`
- Finalize: 2026-07-18T21:59:11Z, `outcome=completed_with_review`; повторный
  вызов — безопасный no-op (`already_finalized=true`)
- Pre-finalize snapshot run/items/changes:
  `var/catalog-processing/snapshot-pre-finalize-20260718.json`, SHA-256
  `9763a406567ddb8ff0cad2db40a836f285d462925753ab5a1a789d9d18c5b9d8`
- Reviewer: user `id=1` (staging superuser); все решения только через
  `review_catalog_change` / `apply_catalog_change` (никаких прямых ORM-update)

## Backups (перед каждым write-блоком, pg_dump | gzip)

| Точка | Файл (`/home/taximeter/proff58-staging/backups/`) | Размер, байт | SHA-256 |
|---|---|---|---|
| pre-apply block 1 | `staging-phase5-pre-apply-block1-20260718-200202.sql.gz` | 21 367 620 | `1a553e184d3502b6a29f0400e887406fe1a04149481f625f7cce9c135a3f0506` |
| pre-apply block 2 | `staging-phase5-pre-apply-block2-20260718-201714.sql.gz` | 21 367 937 | `4f0cdd14cb0e57bdd2ac7d1080bcb7ef8c8f16f3a4daef28420897264364e12c` |
| pre-apply block 3 | `staging-phase5-pre-apply-block3-20260718-202326.sql.gz` | 21 367 664 | `4af144ea0fea35a9d62d1f48855763fbbe001b4dec94fe8f3505c2ba5a282e05` |

Backup блока 1 дополнительно проверен полным restore'ом во временную БД
(счётчики совпали с live); gzip integrity и маркер `\unrestrict` проверены у всех.

## Исходные когорты shortlist v2 и результаты

Когорты зафиксированы в исходном shortlist и не менялись после получения
результата.

| Когорта | Товары | Applied | Abstain | Доля applied |
|---|---|---|---|---|
| Clean (9) | 6682, 12957, 12959, 13936, 28891, 28901, 36377, 36713, 30870 | 8 | 1 (30870) | 88,9% |
| Medium (6) | 10537, 23255, 36304, 26863, 32407, 27250 | 3 | 3 | 50% |
| Adversarial (5) | 37594, 24523, 6681, 35076, 31109 | 4 | 1 (24523) | 80% |
| **Итого (20)** | | **15** | **5** | **75%** |

Abstention rate: **25%** (5/20). Все abstention — taxonomy gaps, ушли в
`needs_review` без создания CatalogChange (корректное поведение).

Confidence применённых: 95×5, 92×1, 90×4, 88×2, 85×2, 80×1.

## Применённые изменения (15)

| product | tool_type slug | conf | | product | tool_type slug | conf |
|---|---|---|---|---|---|---|
| 6681 | adaptery | 95 | | 23255 | krep-shaiby | 88 |
| 6682 | adaptery | 90 | | 28891 | bp-pnevmosteplery | 90 |
| 10537 | adaptery | 92 | | 28901 | bp-pnevmosteplery | 88 |
| 12957 | klyuchi-gaechnye | 85 | | 31109 | svar-reduktory | 80 |
| 12959 | klyuchi-gaechnye | 85 | | 35076 | trosorezy-kabelerezy | 95 |
| 13936 | otvertki | 95 | | 36304 | siz-ochki | 90 |
| 36377 | siz-ochki | 95 | | 36713 | sumki-poyasnye | 90 |
| 37594 | plitkorezy | 95 | | | | |

## Quality gates (все пройдены)

- 0 ошибок identity; 0 значений вне 325 allowed_options; 100% HTTPS evidence;
- 15/15 PAV совпали с approved changes (slug, source=web, confidence);
  `attrs_cache["tool_type"]` = отображаемому значению option;
- Product/PAV baseline без drift на каждом шаге (price, stock, category, name,
  прочие PAV и attrs_cache неизменны); итоговый PAV count: 60 842 → 60 857 (+15);
- идемпотентность: replay import безопасно отклонён; `idempotency_key` всех 15
  changes пересчитан и совпал;
- API spot-check (`/api/catalog/products/<slug>/`): tool_type отдаётся витриной;
- `/healthz/` HTTP 200 после каждого блока; apply-ошибок в логах нет.

## Unresolved taxonomy gaps (5)

| product | Предметная область |
|---|---|
| 24523 | Осветительные мачты |
| 32407 | Сантехнические/трубные ключи |
| 26863 | Шплинты |
| 27250 | Пусковые провода |
| 30870 | Сварочные кабели в сборе |

Options НЕ создавались. Соответствие product ↔ предметная область сверено с
названиями товаров в БД при закрытии пилота (2026-07-18): 32407 — «Ключ для
сантехнической арматуры…», 26863 — «Набор шплинтов…».

## Состояние после закрытия пилота

- run `f7fe5b29…`: `status=completed` (`outcome=completed_with_review`,
  `finished_at=2026-07-18T21:59:11Z`); items: 15 `completed` + 5 `needs_review`;
  changes: 15 `applied`. Product/PAV после finalize не изменились (PAV=60 857).
- staging: состояние проверено на `dev@da6919c` (до docs-only follow-up);
  миграции применены (`migrate --plan` пуст); контейнеры healthy,
  `/healthz/` → 200.
- `FEATURE_CATALOG_PROCESSING=False`: флаг временно включался только на время
  finalize (`.env.bak-20260718-finalize`), затем выключен, web пересоздан,
  `settings.FEATURES["catalog_processing"] is False` проверено, healthz 200.
  **До следующего пилотного запуска флаг не менять.**

## Follow-ups

1. ~~Regression-тест (параметризованный): `changes` при
   `identity.status ∈ {partial, unknown, mismatch}` отклоняются importer'ом.~~
   **Done**: PR #535.
2. ~~`catalog_queue_finalize` / `finalize_catalog_processing_run()`.~~
   **Done**: PR #536; run финализирован (см. выше).
3. ~~Gap analysis по всему каталогу.~~ **Done** (read-only): backlog — 1941
   активный товар без `tool_type`; по гэп-областям: шплинты 6 SKU (cat=367),
   пусковые провода 5 (27249, 27250, 27251, 27253, 27254; 27252 исключён —
   `is_active=False`), сварочный кабель 3 (8485, 30870, 31783), сантехнический
   ключ 1 (32407), осветительная мачта 1 (24523).
4. **Taxonomy changeset — отдельный PR** (создание/применение options, тесты,
   dry-run оценка затронутых товаров). Только после его ревью — временное
   включение processing и повторная обработка четырёх товаров. Маршрутизация
   (сверена с БД 2026-07-18):
   - новая option `krep-shplinty` → 26863 (+ оценка пула 6 SKU);
   - новая option для пусковых проводов → 27250 (+ пул 27249, 27251, 27253,
     27254; 27252 исключён — `is_active=False`);
   - reuse `spetsialnye-klyuchi` → 32407 (подтвердить на ревью changeset'а);
   - reuse `svar-klemmy` → 30870 (подтвердить на ревью changeset'а);
   - мачта 24523 — отложена.
5. **Инфраструктурный дефект** (к каталожному пилоту не относится): host nginx
   для `stg.formulatela58.ru` проксирует на `127.0.0.1:8002`, который не
   отвечает (прямой probe — timeout); project stack публикует nginx на
   `127.0.0.1:8082`. До внешнего staging-тестирования проверить port mapping и
   upstream в host-конфиге nginx.
