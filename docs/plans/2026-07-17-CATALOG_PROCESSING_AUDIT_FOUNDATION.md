# План: фундамент аудита и безопасного применения решений каталога

Дата: 2026-07-17
Статус: Ready for implementation
Приоритет: P1
Оценка: 4–6 рабочих дней

## 1. Цель

Создать первый фундаментальный слой будущего сервиса AI-обогащения:

1. один логический запуск обработки каталога;
2. фиксированный входной snapshot товара;
3. неизменяемая запись каждого предложенного изменения;
4. единый catalog-owned сервис применения решения;
5. атомарное изменение `tool_type` с baseline conflict detection,
   provenance и синхронизацией `attrs_cache`;
6. идемпотентный повтор вызова без дублей и повторной записи.

После этого очередь, файловый importer, `$catalog-research`, Django Admin и
LLM-провайдеры смогут использовать один контракт вместо прямых ORM-записей.

## 2. Почему реализация принадлежит `apps.catalog`

`Product`, `AttributeOption`, `ProductAttributeValue`, правила приоритета
источников и `attrs_cache` принадлежат каталогу. Поэтому:

- новые audit-модели размещаются в `apps.catalog`;
- сервис применения размещается в `apps.catalog.processing`;
- `apps.ai` в следующих этапах вызывает catalog-owned контракт;
- `apps.catalog` не импортирует `apps.ai`;
- существующий `apps.catalog.provenance.apply_sourced_value()` переиспользуется,
  а не дублируется.

Это сохраняет действующую границу зависимостей `ai -> catalog`.

## 3. Scope первого шага

Входит:

- `CatalogProcessingRun`;
- `CatalogProcessingItem`;
- `CatalogChange`;
- additive-миграция;
- snapshot и baseline для `tool_type`;
- `apply_catalog_decision()` только для существующего
  `AttributeOption(attribute=tool_type)`;
- статусы `applied`, `skipped`, `conflict`, `invalid`, `failed`;
- provenance `source`/`confidence`;
- идемпотентность;
- read-only представление аудита в Django Admin;
- unit/integration/concurrency tests;
- документация контракта.

Не входит:

- DB-очередь автоматического выбора товаров;
- JSON export/import;
- `$catalog-research`;
- web/marketplace adapters;
- применение категории, текстов и произвольных характеристик;
- создание новых categories/attributes/options;
- Celery orchestration;
- изменение существующих `enrich_*` команд;
- backfill выдуманной исторической информации.

## 4. Целевой поток первого шага

```text
caller
  -> CatalogProcessingRun
  -> CatalogProcessingItem(input_snapshot + baseline)
  -> CatalogDecisionCommand(tool_type option slug)
  -> committed CatalogChange(status=proposed)
  -> transaction.atomic
       -> lock Product + CatalogChange
       -> validate run/item/baseline/option/source priority
       -> apps.catalog.provenance.apply_sourced_value()
       -> rebuild attrs_cache
       -> CatalogChange(status=applied|conflict|skipped|invalid)
       -> CatalogProcessingItem final status
  -> CatalogDecisionResult
```

Если внутри основной транзакции возникает исключение, изменение товара
откатывается, а ранее созданный committed attempt переводится отдельной короткой
транзакцией в `failed`.

## 5. Модель данных

### 5.1 `CatalogProcessingRun`

Один логический batch обработки.

Поля:

| Поле | Тип | Назначение |
|---|---|---|
| `id` | UUID, PK | Стабильный внешний идентификатор batch |
| `kind` | choices | `manual`, `rules`, `research`, `ai`, `import` |
| `mode` | choices | На первом шаге только `tool_type` |
| `status` | choices | `draft`, `running`, `completed`, `failed`, `cancelled` |
| `idempotency_key` | CharField, unique | Защита от повторного создания batch |
| `scope` | JSONField | Критерии выборки, лимит, явные ID |
| `ruleset_version` | CharField | Человеко-читаемая версия |
| `ruleset_hash` | CharField(64) | SHA-256 применённого набора правил |
| `taxonomy_hash` | CharField(64) | SHA-256 допустимой taxonomy |
| `stats` | JSONField | Счётчики результата |
| `created_by` | nullable FK User | Инициатор |
| `created_at` | DateTime | Начало |
| `finished_at` | nullable DateTime | Завершение |

Инварианты:

- `idempotency_key` уникален;
- completed/failed run имеет `finished_at`;
- изменение каталога запрещено для `draft`, `completed`, `failed`,
  `cancelled`;
- первый шаг не удаляет run физически через штатный UI.

### 5.2 `CatalogProcessingItem`

Snapshot одного товара внутри run.

Поля:

| Поле | Тип | Назначение |
|---|---|---|
| `run` | FK | Родительский batch |
| `product` | nullable FK Product, PROTECT/SET_NULL по решению миграции | Живой товар |
| `product_ref` | PositiveBigInteger | Стабильный audit ID даже после удаления |
| `status` | choices | `pending`, `applied`, `skipped`, `conflict`, `invalid`, `failed` |
| `input_snapshot` | JSONField | Имя, артикул, category, текущий tool_type |
| `input_hash` | CharField(64) | Хеш канонического snapshot |
| `baseline_hashes` | JSONField | На первом шаге `{"tool_type": "sha256"}` |
| `needed_targets` | JSONField | На первом шаге `["tool_type"]` |
| `error_code` | CharField | Машиночитаемая ошибка |
| `error_detail` | CharField/TextField | Без stack trace и секретов |
| timestamps | DateTime | Создание/завершение |

Ограничения:

- unique `(run, product_ref)`;
- `product_ref` не изменяется;
- `input_snapshot` после создания не редактируется;
- snapshot не содержит цену, остатки, персональные данные и секреты.

### 5.3 `CatalogChange`

Append-only попытка изменить одну цель товара.

Поля:

| Поле | Тип | Назначение |
|---|---|---|
| `id` | UUID, PK | Идентификатор попытки |
| `item` | FK | Товар и batch |
| `product_ref` | PositiveBigInteger | Audit-safe ссылка |
| `target_kind` | choices | Первый шаг: `tool_type` |
| `target_key` | CharField | `tool_type` |
| `status` | choices | `proposed`, `applied`, `skipped`, `conflict`, `invalid`, `failed`, `rolled_back` |
| `idempotency_key` | CharField, unique | Повтор команды возвращает прежний результат |
| `before_value` | JSONField | Канонический envelope старого значения |
| `proposed_value` | JSONField | `{"option_slug": "..."}` |
| `after_value` | JSONField | Фактически зафиксированное значение |
| `baseline_hash` | CharField(64) | Baseline из item |
| `source` | choices `Source` | `manual`, `regex`, `web`, `llm` и т.д. |
| `confidence` | SmallInteger 0–100 | Каноническая шкала каталога |
| `rule_ref` | CharField | Slug/id правила, если применимо |
| `ruleset_hash` | CharField(64) | Версия решения |
| `reason_code` | CharField | `baseline_changed`, `unknown_option` и т.д. |
| `reason_detail` | CharField | Без чувствительных данных |
| `evidence` | JSONField | URL/ref/hash, без полного ответа модели |
| `reviewed_by` | nullable FK User | Кто подтвердил |
| timestamps | DateTime | Создание/применение |

Ограничения:

- unique `idempotency_key`;
- индекс `(product_ref, target_kind, created_at)`;
- индекс `(status, created_at)`;
- DB check для confidence `0..100`;
- `applied` требует непустой `after_value`;
- существующие строки не редактируются через Admin;
- rollback в будущем создаёт новую запись со ссылкой `reversal_of`, а не
  переписывает исходную.

## 6. Канонический snapshot `tool_type`

Добавить чистые helpers:

```python
tool_type_snapshot(product) -> {
    "attribute_slug": "tool_type",
    "option_id": 433,
    "option_slug": "sterzhni-kleevye",
    "option_value": "Клеевые стержни",
    "source": "manual",
    "confidence": 100
}

canonical_hash(snapshot) -> sha256
```

Пустое значение имеет один стабильный envelope, например:

```json
{
  "attribute_slug": "tool_type",
  "option_id": null,
  "option_slug": "",
  "option_value": "",
  "source": "",
  "confidence": null
}
```

Нельзя хешировать только `value_option_id`: ID не объясняет значение и хуже
переносится между окружениями. Baseline должен строиться по каноническому JSON с
сортировкой ключей.

## 7. Контракт сервиса

Новый файл:

```text
apps/catalog/processing.py
```

DTO:

```python
@dataclass(frozen=True)
class CatalogDecisionCommand:
    item_id: int
    target_kind: str
    proposed_value: dict
    source: str
    confidence: int
    idempotency_key: str
    rule_ref: str = ""
    evidence: dict | None = None
    reviewer_id: int | None = None


@dataclass(frozen=True)
class CatalogDecisionResult:
    status: str
    change_id: UUID
    reason: str = ""
```

Публичный метод:

```python
apply_catalog_decision(cmd: CatalogDecisionCommand) -> CatalogDecisionResult
```

### 7.1 Алгоритм

1. Валидировать DTO без обращения к изменяемым моделям.
2. По `idempotency_key` вернуть существующий финальный результат, если он уже
   есть.
3. Создать committed `CatalogChange(status=proposed)`.
4. Открыть `transaction.atomic()`.
5. Заблокировать `CatalogChange`, `CatalogProcessingItem` и `Product`.
6. Проверить, что run находится в `running`.
7. Проверить `content_locked`.
8. Снять текущий канонический snapshot `tool_type`.
9. Сравнить его hash с `item.baseline_hashes["tool_type"]`.
10. Найти существующий `Attribute(slug="tool_type")`.
11. Найти существующий option строго по slug внутри этого атрибута.
12. Запретить создание option.
13. Адаптировать команду в существующий `SourcedValueCommand`.
14. Применить через `apply_sourced_value()`.
15. Повторно считать snapshot и проверить `attrs_cache["tool_type"]`.
16. Записать `before_value`, `after_value`, status и reason.
17. Обновить status item.
18. На exception откатить каталог и пометить committed change как `failed`.

### 7.2 Маппинг результатов

| `provenance.ApplyResult` | `CatalogChange.status` |
|---|---|
| `applied` | `applied` |
| `conflict` | `conflict` |
| `priority_blocked` | `skipped` |
| `skipped_locked` | `skipped` |
| `invalid` | `invalid` |
| `missing_product` | `invalid` |
| `missing_attribute` | `invalid` |
| exception | `failed` |

## 8. Изменения по файлам

| Файл | Изменение |
|---|---|
| `apps/catalog/models.py` | Три модели и choices |
| `apps/catalog/migrations/0024_catalog_processing_audit.py` | Additive schema |
| `apps/catalog/processing.py` | DTO, snapshots, hash, apply service |
| `apps/catalog/admin.py` | Read-only run/item/change admin |
| `apps/catalog/tests/test_processing_models.py` | Constraints и статусы |
| `apps/catalog/tests/test_processing_service.py` | Поведение применения |
| `apps/catalog/tests/test_processing_concurrency.py` | Lock/idempotency |
| `docs/ARCHITECTURE.md` | Catalog-owned audit boundary |
| `docs/catalog/operations/README.md` | Новый обязательный путь записи |

Миграцию создавать после проверки актуальных leaf migrations командой:

```bash
python manage.py makemigrations --check --dry-run
python manage.py makemigrations catalog
```

Имя `0024...` является ожидаемым по текущему дереву, но не должно задаваться
вручную, если к моменту реализации появился новый leaf.

## 9. Порядок реализации

### Task 1 — модели и constraints

Приоритет: P1
Оценка: M, 1–2 дня

Acceptance criteria:

- [ ] Миграция только добавляет таблицы/индексы/constraints.
- [ ] Существующие таблицы каталога не переписываются.
- [ ] Run нельзя создать дважды с одним idempotency key.
- [ ] Item уникален в пределах `(run, product_ref)`.
- [ ] Change уникален по idempotency key.
- [ ] Confidence вне `0..100` отклоняется БД.
- [ ] Модели отображаются в Admin только для чтения.

### Task 2 — snapshot и baseline helpers

Приоритет: P1
Оценка: S, 0,5–1 день

Acceptance criteria:

- [ ] Одинаковое состояние даёт одинаковый hash.
- [ ] Изменение option/source/confidence меняет hash.
- [ ] Пустой `tool_type` имеет стабильный envelope.
- [ ] Helper не изменяет БД.
- [ ] Нет N+1 при создании snapshot для заранее загруженного товара.

### Task 3 — `apply_catalog_decision()`

Приоритет: P1
Оценка: M, 1–2 дня

Acceptance criteria:

- [ ] Известный option применяется к пустому `tool_type`.
- [ ] PAV получает правильные `source` и `confidence`.
- [ ] `attrs_cache` совпадает с PAV после commit.
- [ ] Неизвестный option не создаётся.
- [ ] Изменившийся baseline возвращает conflict.
- [ ] Более слабый source не затирает более сильный.
- [ ] `content_locked` блокирует изменение.
- [ ] Повтор с тем же idempotency key не создаёт PAV/change повторно.
- [ ] Исключение откатывает PAV, но оставляет change=`failed`.

### Task 4 — тесты конкуренции и интеграции

Приоритет: P1
Оценка: S–M, 1 день

Acceptance criteria:

- [ ] Два решения по одному baseline не применяются оба.
- [ ] После первого commit второе получает conflict либо прежний
  идемпотентный результат.
- [ ] `apps.catalog` не импортирует `apps.ai`.
- [ ] Существующие тесты provenance и AI sourcing проходят без изменений
  внешнего поведения.

### Task 5 — документация и rollout

Приоритет: P1
Оценка: S, 0,5 дня

Acceptance criteria:

- [ ] Описана catalog-owned граница.
- [ ] Прямые write-пути отмечены как legacy.
- [ ] Описано, что исторический backfill является baseline, а не историей.
- [ ] Есть rollback миграции и проверочные команды.

## 10. Тестовая матрица

Обязательные сценарии:

1. empty -> known tool_type -> applied;
2. existing lower-priority -> stronger source -> applied;
3. existing manual -> regex/web -> skipped;
4. same baseline, unknown option -> invalid;
5. baseline changed after snapshot -> conflict;
6. content locked -> skipped;
7. missing product -> invalid;
8. same idempotency key twice -> one change;
9. two different decisions from one baseline -> at most one applied;
10. exception after PAV save -> PAV rollback, change failed;
11. cache equals EAV after commit;
12. unrelated product/attribute remains unchanged.

Команды проверки:

```bash
pytest apps/catalog/tests/test_processing_models.py -q
pytest apps/catalog/tests/test_processing_service.py -q
pytest apps/catalog/tests/test_processing_concurrency.py -q
pytest apps/catalog/tests/test_provenance.py apps/ai/tests/test_sourcing_service.py -q
python manage.py check
python manage.py makemigrations --check --dry-run
```

После локального набора — полный релевантный suite:

```bash
pytest apps/catalog apps/ai -q
```

## 11. Rollout

1. Применить additive-миграцию на staging.
2. Проверить пустые новые таблицы и индексы.
3. Не переключать существующие команды.
4. Создать один тестовый run/item без применения.
5. Применить одно заранее подтверждённое решение на staging.
6. Проверить PAV, cache, change и повтор вызова.
7. Выполнить точечный rollback тестового значения новой change-командой либо
   восстановить заранее записанный baseline.
8. Только после успешного пилота переходить к DB-очереди.

Откат первого релиза:

- код сервиса не используется существующими flow, поэтому достаточно отключить
  нового caller;
- additive-таблицы можно оставить без влияния на каталог;
- удаление таблиц отдельной reverse migration допустимо только после экспорта
  audit-данных;
- откат не должен удалять или изменять Product/PAV.

## 12. Backfill

В первой миграции backfill отсутствует.

После rollout можно создать один специальный run `kind=import`,
`mode=tool_type`, который зафиксирует текущий каталог как `legacy_baseline`.
Такие записи должны явно иметь:

```json
{
  "historical": false,
  "baseline_only": true
}
```

Round 1–5 можно импортировать отдельно по известным product ID, но нельзя
приписывать им отсутствующие timestamps, ruleset или evidence.

## 13. Definition of Done

- [ ] Additive migration применима и обратима.
- [ ] Новый сервис — единственный новый write-path первого шага.
- [ ] Все изменения `tool_type` через сервис имеют audit.
- [ ] Ошибки и конфликты не оставляют частичный PAV/cache.
- [ ] Идемпотентность подтверждена тестами.
- [ ] Конкурентная запись подтверждена тестом.
- [ ] Старые `provenance` и AI sourcing тесты зелёные.
- [ ] Admin позволяет расследовать run -> item -> change.
- [ ] Документация и rollback обновлены.
- [ ] Существующее поведение production/staging не переключено автоматически.

## 14. Следующий шаг

После принятия этого фундамента реализуется DB-очередь:

```text
catalog_queue_create
  -> CatalogProcessingRun
  -> CatalogProcessingItem snapshots
  -> catalog_queue_export
```

Она должна использовать эти модели и не создавать параллельную систему batch
или audit.
