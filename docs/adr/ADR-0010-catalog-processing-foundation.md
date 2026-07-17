# ADR-0010: Catalog-owned processing foundation

- Статус: принято
- Дата: 2026-07-17
- Связано: `docs/plans/2026-07-17-CATALOG_PROCESSING_AUDIT_FOUNDATION.md`,
  `docs/plans/2026-07-17-CATALOG_RESEARCH_QUEUE_ROADMAP_V2.md`,
  `docs/ARCHITECTURE-AI.md`, ADR-0007, `apps/catalog/provenance.py`

## Контекст

Для Codex-assisted исследования каталога и будущих AI/rule-обогащений нужен
единый контур, в котором:

- каждое предложение по изменению каталога фиксируется до применения;
- применение проходит через catalog-owned сервис;
- audit trail независим от существующего AI-контура `ContentFinding`;
- слабые источники не затирают авторитетные;
- изменившийся baseline блокирует устаревшее предложение.

Существующий `ContentFinding` / `FindingApplicationAttempt` остаётся legacy для
текущего sourcing pipeline. Новый контур не должен от него зависеть, иначе
получится вторая параллельная система audit/apply.

## Решение

1. **Новые audit-модели живут в `apps.catalog`**:
   - `CatalogProcessingRun` — один логический batch;
   - `CatalogProcessingItem` — snapshot одного товара внутри batch;
   - `CatalogChange` — append-only запись предложения и результата.

2. **Сервис применения живёт в `apps.catalog.processing`**:
   - три фазы: `create_catalog_change()`, `review_catalog_change()`,
     `apply_catalog_change()`;
   - `create` только создаёт `CatalogChange(status=proposed)`, не меняя каталог;
   - `review` переводит `proposed -> approved/rejected` и фиксирует
     `reviewed_by/reviewed_at/comment`;
   - `apply` атомарно применяет только `approved`-решение через
     `provenance.apply_sourced_value()`;
   - `apps.catalog` не импортирует `apps.ai`.

3. **Первый target — только `tool_type`**:
   - значение должно быть существующим `AttributeOption(attribute__slug="tool_type")`;
   - новые options не создаются автоматически;
   - применение требует `approved` для `web`/`llm` (и `rules` в v1).

4. **Operational baseline**:
   - snapshot `tool_type` включает `attribute_slug`, `option_id`, `option_slug`,
     `option_value`, `source`, `confidence`;
   - conflict hash (operational baseline) строится по каноническому JSON без
     `option_id` и `option_value` (переименование отображаемого значения не даёт
     ложный конфликт);
   - provenance value_hash вычисляется от `option_id` непосредственно перед
     apply и не входит в operational baseline;
   - пустое значение имеет стабильный envelope.

5. **Идемпотентность**:
   - `CatalogProcessingRun.idempotency_key` unique;
   - `CatalogChange.idempotency_key` unique;
   - повтор команды возвращает прежний финальный результат.

6. **Безопасность**:
   - `content_locked` блокирует изменение;
   - source priority из `data/attribute_rules.json` не обходится;
   - равный приоритет (`allow_equal_override`) разрешается только для
     `approved`-решений;
   - применение PAV и синхронизация `attrs_cache` атомарны;
   - исключение откатывает PAV/cache, но оставляет `CatalogChange(status=failed)`;
   - DB-ограничения: `approved`/`rejected` требуют reviewer, `applied` требует
     `after_value`/`applied_at`;
   - удаление Run/Item защищено `PROTECT` для сохранения audit trail.

7. **Feature flag**:
   - инфраструктурный флаг `catalog_processing` в `config/settings/base.py`;
   - по умолчанию `False` на staging/prod до успешного пилота.

## Последствия

**Плюсы:**
- единый catalog-owned контур для rule/AI/research обогащений;
- чёткая граница `apps.ai -> apps.catalog` сохранена;
- переиспользование provenance и source priority;
- audit trail отделён от legacy `ContentFinding`;
- rollout безопасен: additive-таблицы не влияют на существующие flow.

**Минусы / компромиссы:**
- новые таблицы в `apps.catalog`;
- `ContentFinding` остаётся без миграции до отдельного ADR после пилота;
- v1 ограничен `tool_type`, другие targets — отдельными вертикальными срезами.

**Риски:**
- двойной контур, если кто-то продолжит писать новые обогащения через
  `ContentFinding` — смягчается явным legacy-статусом в ADR;
- массовое применение без модерации — смягчается feature flag и обязательным
  `approved` для web/llm;
- race condition при параллельном apply — смягчается `select_for_update()` и
  idempotency key.
