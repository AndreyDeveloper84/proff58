# Roadmap: Codex-assisted исследование и разбор каталога

## Статус

Proposed, 2026-07-16.

Первый implementation slice вынесен в отдельный developer-ready план:
[`2026-07-17-CATALOG_PROCESSING_AUDIT_FOUNDATION.md`](2026-07-17-CATALOG_PROCESSING_AUDIT_FOUNDATION.md).
Он вводит общий catalog-owned audit/apply фундамент до реализации research
queue и заменяет предлагаемые здесь параллельные batch/audit-сущности единым
`CatalogProcessingRun` / `CatalogProcessingItem` / `CatalogChange`.

## Цель

Реализовать временный контур разбора каталога без прямой интеграции с LLM API:

1. Django формирует управляемую очередь товаров в БД.
2. Очередь экспортируется в версионированный JSON.
3. Codex по явной команде пользователя исследует товары в вебе с помощью
   project-local skill `$catalog-research`.
4. Codex сохраняет структурированный результат и evidence в JSON.
5. Безопасный importer валидирует файл и создаёт только pending
   `ContentFinding`.
6. Модератор отдельно подтверждает применение через catalog-owned provenance.

Контур должен закрывать предложения по:

- категории товара;
- `tool_type`;
- характеристикам;
- названию и описанию, если они включены в конкретный research batch.

## Исходное состояние

В проекте уже существуют:

- `SourcingRun`, `ExternalCall`, `SourcingBudget`;
- `ContentFinding`, `FindingEvidence`, `FindingApplicationAttempt`;
- базовая модерация findings в Django Admin;
- защита `content_locked`;
- baseline conflict detection;
- source priority и транзакционное применение через `apps.catalog.provenance`;
- Celery-задачи, feature flags и Prometheus-метрики;
- 117 проходящих тестов `apps/ai/tests`.

Основные пробелы:

- нет DB-очереди для ручного Codex research;
- нет файлового контракта export/result;
- `ContentFinding` не моделирует category/tool-type решения явно;
- нет безопасного импортёра результатов Codex;
- нет `$catalog-research` skill;
- нет отдельного audit trail для export/import batch;
- sourcing adapters `web_search` и `marketplace` пока не реализованы.

## Scope

В первую версию входят:

- DB-очередь research batches/items;
- JSON export и import;
- JSON Schema и schema versioning;
- project-local `$catalog-research` skill;
- web research по явному запросу пользователя;
- identity matching по бренду, модели и артикулу;
- findings и evidence;
- dry-run по умолчанию;
- идемпотентность;
- baseline/conflict validation;
- модерация;
- метрики, тесты и runbook;
- пилот на товарах в наличии без `tool_type`.

## Non-scope первой версии

- вызов Codex из HTTP request Django;
- полностью unattended-режим;
- автоматический запуск `codex exec` из Celery;
- массовая обработка всего каталога одним запуском;
- изменение цены, остатков, публикации или данных заказа;
- применение результата во время import;
- обучение собственной ML-модели;
- автоматическое доверие данным маркетплейсов;
- произвольное создание новых категорий, типов, атрибутов или options.

## Архитектурные инварианты

1. БД является источником истины; JSON — транспортный артефакт.
2. Export содержит snapshot товара, а не живую ссылку на изменяемые поля.
3. Результат Codex считается недоверенным внешним вводом.
4. Importer не изменяет `Product`, `Category` или `ProductAttributeValue`.
5. Importer создаёт только pending findings и evidence.
6. Применение выполняется отдельным catalog-owned сервисом.
7. Изменение baseline после export блокирует применение устаревшего finding.
8. Значение без проверяемого evidence не получает высокий trust level.
9. Codex не создаёт новые taxonomy slugs.
10. Price, stock, availability и order state запрещены для research pipeline.
11. Все операции идемпотентны и имеют audit trail.
12. Любой batch можно отменить без изменения каталога.

## Целевой поток

```text
Catalog query
  -> ResearchBatch + ResearchItem
  -> export JSON + checksum
  -> $catalog-research
  -> web search and identity verification
  -> result JSON
  -> importer dry-run
  -> schema/domain/baseline validation
  -> ContentFinding + FindingEvidence
  -> moderation
  -> catalog provenance apply
  -> attrs_cache/search verification
```

## Модель данных

### `CatalogResearchBatch`

Назначение: единица планирования, экспорта, импорта и аудита.

Предлагаемые поля:

- `id: UUID`;
- `status`: `draft`, `ready`, `exported`, `partially_imported`, `imported`,
  `cancelled`, `failed`;
- `mode`: `classification`, `attributes`, `full`;
- `scope: JSON`;
- `schema_version`;
- `taxonomy_version`;
- `ruleset_version`;
- `export_checksum`;
- `created_by`;
- `created_at`, `exported_at`, `imported_at`;
- счётчики items/findings/errors.

### `CatalogResearchItem`

Назначение: один товар внутри batch.

Предлагаемые поля:

- `batch`;
- `product_ref`;
- `status`: `pending`, `exported`, `researched`, `invalid`, `imported`,
  `review`, `skipped`;
- `input_snapshot: JSON`;
- `input_hash`;
- `needed_targets: JSON`;
- `result_hash`;
- `error_code`, `error_detail`;
- timestamps;
- unique constraint `(batch, product_ref)`.

Snapshot должен содержать:

- product id;
- external id/article;
- original and normalized name;
- brand/model, если известны;
- текущую category и путь категории;
- текущий `tool_type`;
- существующие атрибуты с source/confidence;
- список допустимых category/tool-type candidates;
- список allowed/required attributes;
- baseline hashes.

### `CatalogResearchImport`

Назначение: аудит каждой попытки импорта.

Поля:

- `batch`;
- `file_name`;
- `file_checksum`;
- `schema_version`;
- `mode`: `dry_run`, `commit`;
- `status`;
- counters;
- структурированные validation errors;
- `created_by`;
- timestamps.

Один и тот же checksum в commit-режиме не должен импортироваться повторно.

### Связь с `ContentFinding`

Добавить nullable provenance-связь:

- `research_item`;
- либо нейтральные поля `origin_kind` + `origin_ref`.

Предпочтителен явный FK `research_item`, пока research queue находится внутри
`apps.ai`.

Расширить целевые значения:

- `category`;
- `tool_type`;
- `attribute`;
- существующие текстовые поля.

Для `tool_type` finding может хранить значение option slug, но применение должно
проходить через отдельный семантический handler, а не маскироваться под обычный
текстовый атрибут.

## Файловый контракт

### Размещение

Артефакты не должны попадать в git:

```text
var/catalog-research/
  outbox/
  inbox/
  reports/
  archive/
```

Каталог добавить в `.gitignore`, сохранив при необходимости `.gitkeep`.

### Export

Файл:

```text
outbox/<batch-uuid>.research.json
```

Обязательные верхнеуровневые поля:

```json
{
  "schema_version": "1.0",
  "batch_id": "uuid",
  "exported_at": "ISO-8601",
  "taxonomy_version": "string",
  "items": []
}
```

### Result

Файл:

```text
inbox/<batch-uuid>.result.json
```

Каждый item должен содержать:

- `product_id`;
- `input_hash`;
- identity decision;
- proposed category/tool_type;
- attributes;
- confidence per field;
- reason codes;
- evidence per field;
- status `researched`, `review` или `unknown`.

Evidence:

```json
{
  "source_type": "manufacturer",
  "url": "https://...",
  "title": "Product page",
  "observed_value": "800 W",
  "retrieved_at": "ISO-8601"
}
```

Полный JSON Schema хранить в:

```text
apps/ai/schemas/catalog_research_result_v1.json
```

## Правила web research

Порядок источников:

1. официальный сайт производителя;
2. официальный PDF/manual/catalog;
3. сайт официального дистрибьютора;
4. крупный специализированный магазин;
5. marketplace только как слабое подтверждение.

Identity gate:

- точное совпадение артикула; либо
- точное совпадение brand + model; либо
- несколько согласованных сильных признаков;
- похожее название без модели недостаточно для переноса характеристик.

Marketplace не может быть единственным evidence для автоматического применения
технической характеристики.

## `$catalog-research` skill

### Размещение

Project-local:

```text
.codex/skills/catalog-research/
  SKILL.md
  agents/openai.yaml
  references/
    source-policy.md
    result-contract.md
    taxonomy-routing.md
```

Скрипты внутри skill не должны дублировать Django importer. Источником
валидационной логики остаётся backend.

### Trigger examples

- «Используй `$catalog-research`, обработай batch `<uuid>`».
- «Исследуй следующие 20 товаров без tool_type».
- «Найди характеристики товаров из research outbox».
- «Повтори web research для invalid items».

### Обязательный workflow skill

1. Проверить, что batch экспортирован и не отменён.
2. Прочитать export целиком.
3. Обрабатывать товары последовательно небольшими группами.
4. Искать только нужные target fields.
5. Выполнить identity gate до извлечения характеристик.
6. Сохранить URL/evidence для каждого предлагаемого значения.
7. Использовать только slugs/options из export.
8. Для неоднозначности вернуть `review` или `unknown`.
9. Записать result JSON.
10. Запустить importer в dry-run.
11. Исправить структурные ошибки result-файла.
12. Остановиться перед commit и запросить подтверждение пользователя.

Skill должен явно запрещать:

- прямой ORM update товаров;
- запуск importer с `--commit` без подтверждения;
- изменение price/stock;
- выдуманные источники и URL;
- значение без identity match;
- создание taxonomy entities.

## Management commands

### Создание batch

```bash
python manage.py catalog_research_create \
  --only-untyped \
  --in-stock \
  --limit 20 \
  --mode full
```

Команда создаёт DB batch/items, но не файл.

### Export

```bash
python manage.py catalog_research_export \
  --batch <uuid>
```

Повторный export при неизменном snapshot должен давать тот же checksum.

### Import

```bash
python manage.py catalog_research_import \
  --file var/catalog-research/inbox/<uuid>.result.json \
  --dry-run
```

Dry-run является режимом по умолчанию.

Commit:

```bash
python manage.py catalog_research_import \
  --file var/catalog-research/inbox/<uuid>.result.json \
  --commit
```

Commit создаёт pending findings/evidence, но не изменяет каталог.

### Status/report

```bash
python manage.py catalog_research_status --batch <uuid>
```

Показывает:

- items по статусам;
- validation errors;
- созданные findings;
- pending moderation;
- conflicts;
- checksum import/export.

## Валидация importer

### Файловый уровень

- максимальный размер файла;
- максимальное число items;
- UTF-8;
- JSON Schema;
- известная schema version;
- batch id совпадает с именем/содержимым;
- checksum;
- отсутствие duplicate product ids;
- защита от path traversal;
- ограничение длины строк и evidence excerpts.

### Domain-уровень

- batch и item существуют;
- товар существует;
- `input_hash` совпадает;
- category/tool-type slug существует;
- category разрешена текущей taxonomy;
- tool type разрешён для category;
- attribute разрешён для выбранного типа;
- option существует;
- тип значения совпадает;
- число находится в допустимом диапазоне;
- unit поддерживается и нормализуется;
- source type разрешён;
- URL использует HTTPS и проходит source safety policy;
- запрещённые targets отклоняются;
- confidence находится в диапазоне;
- identity status достаточен для предлагаемого значения.

### Persistence

- транзакция на один research item;
- ошибка одного item не откатывает валидные items всего batch;
- повторный commit не создаёт дубликаты;
- существующий аналогичный finding переиспользуется или supersede-ится;
- evidence прикрепляется к конкретному finding;
- baseline сохраняется в finding/evidence;
- importer пишет audit counters и error codes.

## Этапы реализации

### Phase 0. Контракты и ADR

Оценка: M, 1–2 дня. Приоритет: P0.

Задачи:

- утвердить DB-as-source-of-truth;
- утвердить JSON v1;
- утвердить state machine batch/item/import;
- определить связь research item с finding;
- определить taxonomy target handlers;
- задокументировать threat model.

Gate: JSON examples проходят schema validation до начала backend-разработки.

### Phase 1. DB queue

Оценка: L, 3–5 дней. Приоритет: P0.

Задачи:

- модели и миграции;
- constraints/indexes;
- admin read views;
- сервис создания batch;
- фильтры scope;
- snapshot builder;
- feature flag `catalog_research`.

Gate: batch из 20 товаров создаётся повторяемо и не меняет каталог.

### Phase 2. Exporter

Оценка: M, 1–2 дня. Приоритет: P1.

Задачи:

- JSON serializer;
- deterministic ordering;
- checksum;
- atomic file write;
- management command;
- `.gitignore`;
- export tests.

Gate: два export одного snapshot побайтово идентичны.

### Phase 3. Safe importer

Оценка: XL, разбить на 3 задачи по M/L. Приоритет: P0.

Задачи:

1. JSON Schema/file validation.
2. Domain/taxonomy/identity validation.
3. Transactional findings/evidence persistence.

Gate:

- dry-run ничего не записывает;
- commit не меняет Product/PAV;
- повторный commit идемпотентен;
- malicious/oversized input отклоняется.

### Phase 4. Category/tool-type findings

Оценка: L, 3–5 дней. Приоритет: P0.

Задачи:

- расширить finding targets;
- category baseline resolver;
- tool-type baseline resolver;
- отдельные apply commands в `apps.catalog`;
- compatibility validation;
- admin diff.

Gate: category/tool-type proposal проходит весь путь до moderation без прямой
записи.

### Phase 5. `$catalog-research` skill

Оценка: M, 1–2 дня. Приоритет: P1.

Задачи:

- создать skill через `init_skill.py`;
- написать компактный `SKILL.md`;
- добавить три reference-файла;
- сгенерировать `agents/openai.yaml`;
- выполнить `quick_validate.py`;
- прогнать skill на synthetic batch.

Gate: новый Codex-сеанс по одной команде создаёт schema-valid result и
останавливается перед commit.

### Phase 6. Moderation UX

Оценка: L, 3–5 дней. Приоритет: P1.

Задачи:

- фильтры по batch/category/target/status;
- current/proposed diff;
- evidence links;
- reason codes;
- approve/reject;
- bulk approve только для policy-eligible findings;
- conflict/superseded status.

Gate: модератор может понять источник и причину каждого значения без чтения raw
JSON.

### Phase 7. Observability and runbooks

Оценка: M, 1–2 дня. Приоритет: P1.

Метрики:

- batches/items по статусам;
- import validation failures по error code;
- findings per batch;
- moderation acceptance/rejection;
- identity failures;
- source distribution;
- average research time;
- conflict rate.

Документы:

- create/export/import runbook;
- moderation runbook;
- rollback/cancel runbook;
- schema-version upgrade policy.

Gate: оператор может диагностировать batch без прямого SQL.

### Phase 8. Pilot rollout

Оценка: 3–5 рабочих дней наблюдения. Приоритет: P0.

Последовательность:

1. Synthetic batch: 5 фиктивных cases.
2. Real batch: 10 товаров, только dry-run.
3. Real batch: 20 товаров, findings + ручная модерация.
4. Batch: 50 товаров в наличии без `tool_type`.
5. После quality gate — оставшиеся товары в наличии без типа.
6. Затем товары без остатка.

Один batch первой версии: не более 20–30 товаров.

## Backlog

| ID | Задача | Priority | Estimate | Dependency |
|---|---|---|---|---|
| CR-01 | ADR и threat model | P0 | M | — |
| CR-02 | JSON Schema v1 + examples | P0 | M | CR-01 |
| CR-03 | ResearchBatch/Item/Import models | P0 | L | CR-01 |
| CR-04 | Snapshot builder | P0 | M | CR-03 |
| CR-05 | Batch create command | P1 | M | CR-04 |
| CR-06 | Deterministic exporter | P1 | M | CR-02, CR-04 |
| CR-07 | File/schema validator | P0 | M | CR-02 |
| CR-08 | Domain/taxonomy validator | P0 | L | CR-07 |
| CR-09 | Findings/evidence importer | P0 | L | CR-03, CR-08 |
| CR-10 | Category/tool-type finding targets | P0 | L | CR-03 |
| CR-11 | Catalog apply handlers | P0 | L | CR-10 |
| CR-12 | `$catalog-research` skill | P1 | M | CR-02, CR-06 |
| CR-13 | Moderation batch UI | P1 | L | CR-09, CR-10 |
| CR-14 | Metrics and reporting | P1 | M | CR-03, CR-09 |
| CR-15 | Runbooks | P1 | S | CR-05, CR-09 |
| CR-16 | Pilot and calibration | P0 | L | CR-11–CR-15 |

Оценка первой рабочей версии:

- один разработчик: 4–6 недель;
- два разработчика: 2–3 недели;
- первый end-to-end dry-run: 7–10 рабочих дней.

## Test plan

### Models

- state transitions;
- unique constraints;
- cancelled/finished immutability;
- indexes and deletion behavior.

### Export

- stable ordering;
- stable checksum;
- snapshot completeness;
- no secret or protected data leakage;
- empty/invalid scope.

### Import security

- invalid JSON/schema;
- unknown schema version;
- oversized input;
- duplicate items;
- path traversal;
- non-HTTPS and disallowed host;
- excessively long strings;
- forbidden targets;
- unknown slugs/options.

### Domain behavior

- category/tool-type compatibility;
- attribute whitelist;
- unit/range validation;
- identity mismatch;
- changed input hash;
- changed baseline;
- content lock;
- duplicate findings;
- partial batch failure;
- importer idempotency.

### Integration

- create -> export -> result -> dry-run;
- create -> export -> commit -> pending findings;
- moderation approve/reject;
- apply through catalog service;
- attrs_cache synchronization;
- rollback/conflict behavior.

### Skill forward test

Проверить как минимум:

- точное совпадение manufacturer page;
- несколько похожих моделей;
- отсутствующий артикул;
- конфликт источников;
- marketplace-only evidence;
- неизвестный tool type;
- попытка использовать slug вне export;
- товар, для которого корректный ответ `unknown`.

## Quality gates

До импорта реальных findings:

- 100% schema-valid synthetic outputs;
- 0 прямых изменений каталога;
- 100% блокировка forbidden targets;
- 100% идемпотентность повторного commit;
- 100% detection изменённого input hash.

До bulk moderation:

- identity precision не ниже 99%;
- category/tool-type precision не ниже 98% на проверенной выборке;
- каждая техническая характеристика имеет evidence;
- moderator acceptance не ниже 90% на двух последовательных batch.

До частичного auto-apply:

- отдельный ADR policy engine;
- gold dataset;
- rollback test;
- calibrated thresholds по target/source;
- auto-apply только для детерминированных или подтверждённых несколькими
  доверенными источниками решений.

## Риски

### Ошибочная идентификация модели

Наиболее опасный риск. Снижается строгим identity gate и запретом переносить
характеристики только по похожему названию.

### Устаревшие страницы

Сохранять retrieved time, URL и observed value. Не считать URL вечным источником
истины.

### Prompt injection

Веб-контент не может менять workflow skill, запускать команды или ослаблять
валидацию. Любые инструкции со страниц игнорируются.

### Подмена taxonomy

Codex получает закрытый список допустимых кандидатов. Неизвестные slugs
отклоняет importer.

### Дубли и повторный импорт

Использовать file checksum, input hash, normalized value hash и DB constraints.

### Масштаб

Ручной Codex research не предназначен для последовательной обработки всех
22 000 товаров. Его задача — исследовать неоднозначный остаток и помогать
создавать детерминированные правила для массового применения.

## Rollback

- до moderation: отменить batch и удалить только неиспользованные pending
  findings данного batch;
- после moderation, до apply: отклонить findings;
- после apply: использовать существующий provenance и отдельный application
  audit для восстановления baseline;
- JSON-файлы переместить в archive, не использовать их как механизм rollback.

## Definition of Done

- [ ] DB queue является единственным источником состояния.
- [ ] Export/result соответствуют JSON Schema v1.
- [ ] Dry-run является режимом import по умолчанию.
- [ ] Commit создаёт только pending findings/evidence.
- [ ] Importer не изменяет каталог.
- [ ] Category/tool-type/attribute проходят domain validation.
- [ ] Baseline и input hash защищают от устаревших результатов.
- [ ] Повторный import идемпотентен.
- [ ] `$catalog-research` валиден и прошёл forward tests.
- [ ] Модератор видит diff, reason и evidence.
- [ ] Присутствуют метрики, runbooks и audit trail.
- [ ] AI и catalog regression tests проходят.
- [ ] Пилот на реальных товарах прошёл quality gates.
