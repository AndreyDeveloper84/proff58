# Roadmap v2: безопасный разбор и обогащение каталога

Дата: 2026-07-17
Статус: Proposed, ready for technical review
Приоритет: P1
Первый target: `tool_type`

## 1. Решение

Система обработки каталога строится вокруг одного catalog-owned контура:

```text
CatalogProcessingRun
  -> CatalogProcessingItem
  -> CatalogChange(status=proposed)
  -> validation
  -> moderation
  -> apply_catalog_change()
  -> applied | rejected | skipped | conflict | invalid | failed
```

Новые research-, rule- и AI-процессы не создают собственные параллельные
batch/audit-модели и не изменяют каталог напрямую.

Первый рабочий релиз решает одну задачу: назначение существующего значения
`tool_type` товарам в наличии, у которых оно отсутствует.

Категории, произвольные характеристики, названия и описания добавляются только
после успешного пилота `tool_type`.

## 2. Цель

Создать управляемый процесс, в котором:

1. Django выбирает небольшую группу товаров и фиксирует snapshot.
2. Правило, человек или Codex предлагает существующий `tool_type`.
3. Предложение сохраняется как отдельный `CatalogChange`.
4. Web/LLM-предложения проходят ручную модерацию.
5. Catalog-owned сервис атомарно применяет подтверждённое решение.
6. Baseline, source priority, `content_locked` и идемпотентность защищают каталог.
7. После изменения проверяются EAV и `attrs_cache`.
8. Каждое решение можно расследовать по run, item, evidence и инициатору.

## 3. Бизнес-результат первого релиза

Оператор может:

- сформировать batch из 20 товаров в наличии без `tool_type`;
- экспортировать их для исследования;
- получить предложения только из существующей taxonomy;
- выполнить безопасный dry-run импорта;
- увидеть current/proposed/evidence в Django Admin;
- подтвердить или отклонить каждое предложение;
- применить подтверждённые изменения;
- получить отчёт по результатам и конфликтам.

Первый релиз не считается завершённым, пока этот поток не проверен минимум на
двух реальных batch: 20 и 50 товаров.

## 4. Архитектурные границы

### `apps.catalog`

Владеет:

- `CatalogProcessingRun`;
- `CatalogProcessingItem`;
- `CatalogChange`;
- snapshot и baseline;
- проверкой taxonomy;
- модерационным состоянием изменения;
- применением решения;
- provenance, EAV и `attrs_cache`;
- audit trail.

### `apps.ai`

Может:

- подготовить предложение;
- приложить confidence, reason и evidence;
- вызвать публичный контракт `apps.catalog`.

Не может:

- напрямую изменять `Product`, `Category` или `ProductAttributeValue`;
- создавать taxonomy entities;
- обходить модерацию;
- импортироваться из `apps.catalog`.

Зависимость остаётся однонаправленной:

```text
apps.ai -> apps.catalog
```

## 5. Отношение к существующему `ContentFinding`

`ContentFinding` остаётся legacy-контрактом существующего AI-контура. Новый
research pipeline не обязан создавать цепочку:

```text
ContentFinding -> FindingApplicationAttempt -> CatalogChange
```

Новое предложение записывается непосредственно в
`CatalogChange(status=proposed)`.

Отдельный ADR после пилота должен решить судьбу `ContentFinding`:

1. мигрировать его use cases на `CatalogChange`; либо
2. оставить его только для наблюдений, которые не обязательно меняют каталог.

До ADR запрещено создавать второй универсальный apply/audit-контур.

## 6. Scope первого релиза

Входит:

- один target `tool_type`;
- только существующий `Attribute(slug="tool_type")`;
- только существующие `AttributeOption`;
- товары в наличии без `tool_type`;
- batch не более 20–50 товаров;
- snapshot и baseline;
- предложение, проверка, модерация и применение;
- источники `manual`, `rules`, `web`, `llm`;
- evidence для `web` и `llm`;
- DB queue;
- JSON export/result/import;
- dry-run по умолчанию;
- project-local `$catalog-research` skill;
- минимальный Django Admin;
- идемпотентность и защита от конкурирующей записи;
- reason codes, отчёт и тесты.

## 7. Non-scope первого релиза

- изменение категории;
- произвольные EAV-атрибуты;
- числовые значения, units и диапазоны;
- название и описание товара;
- создание categories/attributes/options;
- price, stock, availability и order state;
- автоматический запуск Codex из Celery или HTTP request;
- unattended processing;
- массовый запуск на всём каталоге;
- полноценный rollback UI;
- bulk auto-apply web/LLM-решений;
- backfill выдуманной истории;
- универсальный policy engine;
- обязательные Prometheus-метрики до пилота.

## 8. Инварианты безопасности

1. БД — источник истины; JSON — транспорт.
2. Export содержит snapshot, а не только ссылку на живой товар.
3. JSON и web/LLM-результат считаются недоверенным вводом.
4. Import создаёт предложения, но не изменяет каталог.
5. Web/LLM-предложение нельзя применить без `approved`.
6. Codex использует только options из export.
7. Изменившийся baseline блокирует применение.
8. Более слабый source не затирает более сильный.
9. `content_locked` блокирует изменение.
10. Unknown option никогда не создаётся автоматически.
11. Одна команда с одним idempotency key не создаёт повторное изменение.
12. Цена, остаток, публикация и заказы недоступны pipeline.
13. Ошибка одного item не откатывает успешно обработанные соседние items.
14. Применение PAV и синхронизация `attrs_cache` атомарны.

## 9. Модель данных

### 9.1 `CatalogProcessingRun`

Один логический запуск обработки.

Ключевые поля:

| Поле | Назначение |
|---|---|
| `id: UUID` | Стабильный внешний ID |
| `kind` | `manual`, `rules`, `research`, `ai`, `import` |
| `mode` | В v1 только `tool_type` |
| `status` | `draft`, `running`, `completed`, `failed`, `cancelled` |
| `idempotency_key` | Уникальный ключ создания run |
| `scope` | Фильтры, limit, explicit IDs |
| `ruleset_version/hash` | Версия логики предложения |
| `taxonomy_hash` | Версия допустимых options |
| `stats` | Итоговые счётчики |
| `created_by` | Инициатор |
| timestamps | Создание и завершение |

Run в `completed`, `failed` или `cancelled` не принимает новые изменения.

### 9.2 `CatalogProcessingItem`

Один товар внутри run.

Ключевые поля:

| Поле | Назначение |
|---|---|
| `run` | Родительский запуск |
| `product` | Живая nullable/PROTECT-ссылка по решению миграции |
| `product_ref` | Стабильный audit ID |
| `status` | `pending`, `processing`, `needs_review`, `completed`, `failed` |
| `input_snapshot` | Фиксированный вход |
| `input_hash` | Hash канонического snapshot |
| `baseline_hashes` | В v1 только `tool_type` |
| `needed_targets` | В v1 строго `["tool_type"]` |
| `error_code/detail` | Без stack trace и секретов |
| timestamps | Создание и завершение |

Ограничение первого релиза: один item содержит ровно один target.

Подробный результат хранится на `CatalogChange`, а item содержит агрегатное
состояние.

### 9.3 `CatalogChange`

Audit-preserving запись одного предложения. Это не event-sourcing модель:
сервис может менять её status и итоговые поля, но Admin и внешние callers не
могут редактировать или удалять существующую запись.

Ключевые поля:

| Поле | Назначение |
|---|---|
| `id: UUID` | ID предложения |
| `item` | Товар и run |
| `product_ref` | Audit-safe ссылка |
| `target_kind/key` | В v1 `tool_type` |
| `status` | `proposed`, `approved`, `rejected`, `applied`, `skipped`, `conflict`, `invalid`, `failed`, `reversed` |
| `idempotency_key` | Уникальная защита от дубля |
| `before_value` | Состояние на момент предложения |
| `proposed_value` | `{"option_slug": "..."}` |
| `after_value` | Фактическое состояние после apply |
| `baseline_hash` | Baseline item |
| `source` | `manual`, `rules`, `web`, `llm` |
| `confidence` | `0..100` |
| `rule_ref/ruleset_hash` | Происхождение правила |
| `reason_code/detail` | Объяснение результата |
| `evidence` | URL/ref/hash, без полного ответа модели |
| `reviewed_by/at/comment` | Модерация |
| `applied_at` | Время применения |
| `reversal_of` | Ссылка для будущего обратного изменения |

Обязательные DB-ограничения:

- unique `idempotency_key`;
- unique proposal scope по принятому ADR, если нужен dedup разных import;
- confidence `0..100`;
- `approved` требует `reviewed_by` и `reviewed_at`;
- `applied` требует `after_value` и `applied_at`;
- `reversed` не переписывает историю исходного применения;
- индексы по `(product_ref, target_kind, created_at)` и `(status, created_at)`.

## 10. Snapshot и baseline `tool_type`

Audit snapshot содержит:

```json
{
  "attribute_slug": "tool_type",
  "option_id": 433,
  "option_slug": "sterzhni-kleevye",
  "option_value": "Клеевые стержни",
  "source": "manual",
  "confidence": 100
}
```

Пустое значение имеет стабильный envelope.

Для conflict hash используется operational baseline:

```json
{
  "attribute_slug": "tool_type",
  "option_slug": "sterzhni-kleevye",
  "source": "manual",
  "confidence": 100
}
```

`option_id` и отображаемый `option_value` сохраняются для аудита, но не входят в
conflict hash. Переименование отображаемого значения не должно создавать
ложный конфликт, если slug и provenance не изменились.

Канонический JSON сортирует ключи и хешируется SHA-256.

## 11. Сервисные контракты

Предложение и применение разделяются.

```python
create_catalog_change(command: CatalogChangeCommand) -> CatalogChangeResult

validate_catalog_change(change_id: UUID) -> CatalogValidationResult

review_catalog_change(
    change_id: UUID,
    decision: str,
    reviewer_id: int,
    comment: str = "",
) -> CatalogChangeResult

apply_catalog_change(
    change_id: UUID,
    actor_id: int | None = None,
) -> CatalogDecisionResult
```

### 11.1 Создание предложения

`create_catalog_change()`:

1. валидирует DTO;
2. возвращает прежний результат по idempotency key;
3. проверяет run/item/target;
4. сохраняет `before_value`, `baseline_hash`, source и evidence;
5. создаёт устойчивое состояние `proposed`;
6. не изменяет Product/PAV.

### 11.2 Модерация

- `web` и `llm` требуют `approved`;
- `manual` считается approved только при наличии реального actor;
- `rules` в v1 также проходят модерацию;
- `rejected` является финальным состоянием;
- reviewer не передаётся как произвольное доказательство в apply-команде:
  сервис читает сохранённое состояние модерации из БД.

### 11.3 Применение

`apply_catalog_change()` внутри `transaction.atomic()`:

1. блокирует change, item и Product;
2. проверяет допустимый статус run/change;
3. проверяет `content_locked`;
4. повторно снимает operational baseline;
5. сравнивает baseline hash;
6. находит `tool_type` и option строго по slug;
7. не создаёт option;
8. применяет через существующий `apply_sourced_value()`;
9. перестраивает/синхронизирует `attrs_cache`;
10. повторно читает snapshot и проверяет cache против EAV;
11. фиксирует status, after_value, reason и timestamps;
12. обновляет агрегатный status item.

На исключении изменения PAV/cache откатываются. Change переводится в `failed`
без потери информации о попытке.

Зависшие `proposed` не являются аварийным состоянием: они ожидают проверки или
модерации. Для зависших `approved` применяется отдельный отчёт, а не скрытый
автоматический retry.

## 12. DB queue

Команда:

```bash
python manage.py catalog_queue_create \
  --only-untyped \
  --in-stock \
  --limit 20 \
  --mode tool_type
```

Она:

- создаёт `CatalogProcessingRun(kind=research)`;
- фиксирует ordered scope;
- создаёт items и snapshot;
- не создаёт файл;
- не изменяет каталог;
- повтор с тем же idempotency key возвращает существующий run.

## 13. Файловый контракт

Артефакты не попадают в git:

```text
var/catalog-processing/
  outbox/
  inbox/
  reports/
  archive/
```

### 13.1 Export v1

```json
{
  "schema_version": "1.0",
  "run_id": "uuid",
  "exported_at": "ISO-8601",
  "taxonomy_hash": "sha256",
  "target_kind": "tool_type",
  "allowed_options": [],
  "items": []
}
```

Item содержит:

- `product_ref`;
- article/external ID;
- original и normalized name;
- brand/model, если известны;
- category/path;
- input snapshot/hash;
- baseline hash;
- только необходимые target данные.

### 13.2 Result v1

```json
{
  "schema_version": "1.0",
  "run_id": "uuid",
  "taxonomy_hash": "0000000000000000000000000000000000000000000000000000000000000000",
  "export_checksum": "1111111111111111111111111111111111111111111111111111111111111111",
  "items": [
    {
      "product_ref": 123,
      "input_hash": "sha256",
      "identity": {
        "status": "matched",
        "brand": "Bosch",
        "model": "GSR 120-LI"
      },
      "status": "researched",
      "changes": [
        {
          "target_kind": "tool_type",
          "proposed_value": {"option_slug": "drill-driver"},
          "confidence": 96,
          "reason_code": "exact_model_match",
          "source": "web",
          "evidence": [
            {
              "source_type": "manufacturer",
              "url": "https://www.bosch-professional.com/example"
            }
          ]
        }
      ]
    }
  ]
}
```

Допустимые item statuses: `researched`, `review`, `unknown`, `identity_failed`.

JSON Schema хранится в backend. Skill не дублирует domain validation.

## 14. Export и import

```bash
python manage.py catalog_queue_export --run <uuid>

python manage.py catalog_queue_import \
  --file var/catalog-processing/inbox/<uuid>.result.json \
  --dry-run

python manage.py catalog_queue_import \
  --file var/catalog-processing/inbox/<uuid>.result.json \
  --commit
```

Dry-run — режим по умолчанию.

Commit:

- создаёт только `CatalogChange(status=proposed)`;
- не изменяет Product/PAV/cache;
- идемпотентен по file checksum и change idempotency key;
- обрабатывает каждый item в отдельной транзакции;
- сохраняет структурированные ошибки.

Минимальная валидация:

- file size и максимальное количество items;
- UTF-8 и JSON Schema;
- schema/run/taxonomy hash и checksum исходного export;
- отсутствие duplicate product refs;
- совпадение input hash;
- run/item/product существуют;
- target строго `tool_type`;
- option slug присутствует в разрешённой taxonomy;
- confidence `0..100`;
- identity status допускает предложение;
- evidence соответствует source policy;
- запрещённые targets отклоняются;
- path traversal и чрезмерные строки блокируются.

## 15. Правила web research

Приоритет источников:

1. официальный сайт производителя;
2. официальный manual/PDF/catalog;
3. официальный дистрибьютор;
4. крупный специализированный магазин;
5. marketplace только как слабое дополнительное подтверждение.

Identity gate:

- точный артикул; либо
- точные brand + model; либо
- несколько согласованных сильных признаков.

Похожего названия недостаточно. При неоднозначности возвращается `review`,
`unknown` или `identity_failed`.

Web content не может менять workflow, запускать команды или ослаблять правила.
Инструкции на исследуемых страницах игнорируются.

## 16. `$catalog-research` skill

Skill:

1. проверяет exported/running run;
2. читает export целиком;
3. обрабатывает небольшими группами;
4. сначала выполняет identity gate;
5. исследует только `tool_type`;
6. использует только allowed option slugs;
7. прикладывает evidence и reason;
8. сохраняет schema-valid result;
9. запускает importer только в dry-run;
10. исправляет структурные ошибки;
11. останавливается перед commit и просит подтверждение пользователя.

Skill запрещает:

- прямой ORM update;
- commit без подтверждения;
- изменение price/stock;
- создание taxonomy;
- выдуманные URL/evidence;
- перенос данных без identity match.

## 17. Минимальный Django Admin

Нужны экраны:

- список runs с counters;
- items конкретного run;
- current/proposed diff для change;
- source, confidence, reason и evidence links;
- approve/reject одного change;
- применение approved change;
- фильтры по run/status/source/reason;
- read-only audit после финального состояния.

Bulk approve и сложный dashboard не входят в первый релиз.

## 18. Этапы реализации

### Phase 0 — ADR и согласование контрактов

Оценка: 0,5–1 день.

- утвердить `CatalogChange` как новый proposal/audit-контракт;
- зафиксировать legacy-статус `ContentFinding`;
- утвердить state machines;
- утвердить operational baseline;
- утвердить JSON v1 и примеры;
- проверить schema examples.

Gate: в документах нет параллельных batch/apply моделей.

### Phase 1 — audit, proposal, moderation, apply

Оценка: 5–8 рабочих дней.

- модели и additive migration;
- snapshot/hash helpers;
- create/validate/review/apply services;
- минимальный Admin;
- idempotency/concurrency tests;
- provenance/EAV/cache integration.

Gate: вручную созданное предложение проходит полный путь до применения без
прямого ORM write.

### Phase 2 — ручной пилот без JSON

Оценка: 1 день.

- создать run на 10 staging-товаров;
- вручную предложить подтверждённые значения;
- approve/apply;
- проверить baseline, priority, cache, audit и повтор вызова.

Gate: 10/10 ожидаемых решений обработаны без частичных записей.

### Phase 3 — DB queue и JSON transport

Оценка: 4–6 рабочих дней.

- queue create;
- deterministic export;
- JSON Schema;
- dry-run importer;
- commit -> proposed changes;
- status/report command;
- file security tests.

Gate: create -> export -> synthetic result -> dry-run -> commit создаёт только
proposed changes.

### Phase 4 — `$catalog-research`

Оценка: 1–2 рабочих дня.

- project-local skill;
- source policy;
- identity gate;
- result contract;
- synthetic forward tests.

Gate: новый Codex-сеанс создаёт schema-valid result и останавливается перед
commit.

### Phase 5 — реальный пилот

Оценка: 2–3 рабочих дня плюс наблюдение.

1. 20 товаров: research + ручная модерация.
2. Разбор всех ошибок и rejected changes.
3. 50 товаров: повторный batch.
4. Сравнение точности и времени.

Gate:

- identity precision >= 99%;
- `tool_type` precision >= 98% на проверенной выборке;
- moderator acceptance >= 90% на двух batch;
- 0 прямых/неподтверждённых изменений;
- 100% конфликтов baseline заблокированы.

### Phase 6 — детерминированные массовые правила

После пилота Codex используется для выявления шаблонов:

- brand + model series;
- устойчивые слова/фразы в названии;
- исходная категория 1С;
- артикул/префикс;
- существующие атрибуты.

Правила сначала работают как proposals с модерацией. Codex research остаётся
для неоднозначного длинного хвоста.

### Phase 7 — расширение targets

Добавлять отдельными ADR и вертикальными срезами:

1. category;
2. option attributes;
3. numeric attributes + units/ranges;
4. title/description.

Нельзя включать несколько новых типов изменения одним релизом.

## 19. Обязательные тесты первого релиза

### Models и states

- unique run/item/change keys;
- DB confidence constraint;
- недопустимые переходы статусов;
- approved требует reviewer;
- applied требует after_value;
- финальные записи недоступны для редактирования через Admin.

### Apply

1. empty -> known option -> applied;
2. weaker existing source -> stronger -> applied;
3. manual existing -> rules/web/llm -> skipped;
4. unknown option -> invalid;
5. changed baseline -> conflict;
6. content locked -> skipped;
7. missing product -> invalid;
8. same idempotency key twice -> one change;
9. two decisions from one baseline -> at most one applied;
10. exception after PAV write -> rollback + failed audit;
11. cache equals EAV after commit;
12. unrelated fields remain unchanged;
13. unapproved web/LLM -> apply forbidden.

### Export/import

- deterministic ordering and checksum;
- no secrets or forbidden fields;
- invalid/oversized JSON;
- duplicate items;
- path traversal;
- unknown schema/taxonomy;
- changed input hash;
- unknown option;
- partial item failure;
- repeated commit creates no duplicates;
- import never changes Product/PAV/cache.

### Skill

- exact manufacturer match;
- similar models;
- missing article;
- conflicting sources;
- marketplace-only source;
- no suitable allowed option;
- attempted foreign slug;
- correct `unknown` result;
- prompt injection in page content.

## 20. Rollout

1. Применить additive migration на staging.
2. Проверить таблицы, constraints и индексы.
3. Не переключать существующие write flows.
4. Выполнить ручной пилот из Phase 2.
5. Проверить reverse/restore baseline на тестовом товаре.
6. Выполнить synthetic JSON flow.
7. Выполнить реальные batch 20 и 50.
8. Только после quality gates планировать оставшиеся товары в наличии.
9. Товары без остатка обрабатывать после активного ассортимента.

Откат:

- отключить нового caller/feature flag;
- не удалять audit-данные;
- восстановление applied значения выполнять новым reversal change;
- additive-таблицы можно оставить без влияния на каталог;
- JSON archive не является механизмом rollback.

## 21. Метрики после пилота

До пилота достаточно status/report команды и DB counters.

После подтверждения процесса добавить:

- items/change по статусам;
- identity failures;
- причины invalid/conflict/reject;
- acceptance rate;
- source distribution;
- research time;
- applied accuracy по контрольной выборке;
- долю товаров, закрытых rules и web research.

## 22. Оценка

Для одного разработчика:

| Блок | Оценка |
|---|---:|
| ADR и контракты | 0,5–1 день |
| Фундамент + модерация + apply | 5–8 дней |
| Ручной пилот | 1 день |
| Queue + JSON | 4–6 дней |
| Skill | 1–2 дня |
| Реальный пилот | 2–3 дня |
| Итого первая вертикаль | 12–18 рабочих дней |

Универсальная версия с категориями, характеристиками, расширенным UX,
метриками и runbooks оценивается отдельно после пилота.

## 23. Definition of Done

- [ ] Используются только `CatalogProcessingRun/Item/Change`.
- [ ] Новый контур не зависит от обязательного `ContentFinding`.
- [ ] Один item v1 содержит только target `tool_type`.
- [ ] Import создаёт только proposed changes.
- [ ] Web/LLM нельзя применить без сохранённого approve.
- [ ] Все writes проходят через catalog-owned сервис.
- [ ] Unknown taxonomy entities не создаются.
- [ ] Baseline/source priority/content lock работают.
- [ ] PAV и `attrs_cache` изменяются атомарно.
- [ ] Повторные create/import/apply идемпотентны.
- [ ] Конкурирующие решения не применяются оба.
- [ ] Admin показывает diff, evidence, reason и reviewer.
- [ ] Skill прошёл synthetic forward tests.
- [ ] Реальные batch 20 и 50 прошли quality gates.
- [ ] Существующие catalog/AI regression tests зелёные.
- [ ] Production flow не переключается автоматически.

## 24. Следующее решение после v1

По результатам пилота принять отдельное решение:

1. какие случаи покрываются массовыми правилами;
2. какие остаются для Codex research;
3. нужен ли auto-apply для строго детерминированных rules;
4. мигрируется ли `ContentFinding` на новый контракт;
5. какой target реализуется следующим.

До этого момента не начинать универсальный importer категорий и характеристик.
