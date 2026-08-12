# Catalog Research — implementation index

Авторитетный план: `2026-07-17-CATALOG_RESEARCH_QUEUE_ROADMAP_V2.md` (catalog-owned `CatalogProcessingRun/Item/Change` в `apps.catalog`).
Первый slice: `2026-07-17-CATALOG_PROCESSING_AUDIT_FOUNDATION.md`.

Этот файл — индекс существующего кода, который нужен для реализации.

## 1. Что уже есть

### 1.1 Catalog — ядро обработки

| Файл | Роль | Что переиспользуем |
|------|------|--------------------|
| `apps/catalog/models.py` | `Category`, `Product`, `Attribute`, `AttributeOption`, `ProductAttributeValue`, `Source`, `ContentSource`, `EnrichStatus`, `ImportRun` | Все taxonomy entities. `Product.content_locked`, `category_is_manual`, `content_field_sources` — guard'ы. |
| `apps/catalog/provenance.py` | `apply_sourced_value()`, `SourcedValueCommand`, `value_hash()`, `attribute_baseline()`, `can_overwrite()` | Готовый применятор с source priority, baseline conflict и content lock. Для `tool_type` маппим в `attribute_slug="tool_type"`. |
| `apps/catalog/read_models.py` | `attr_value_to_json()`, `rebuild_attrs_cache()` | Сборка/пересборка `attrs_cache`. |
| `apps/catalog/enrichment.py` | `apply_ai_enrichment()`, `pending_for_enrichment()` | Паттерн "заполнять пробелы" и модерации по confidence. |
| `apps/catalog/attribute_extract.py` | `AttributeRules`, `AttrRule`, `AttrValue` | Reference для allowed attributes/options. |
| `apps/catalog/tool_type.py` | `ToolTypeRules`, `normalize()`, `transliterate()` | Генерация списка допустимых `tool_type` options. |
| `apps/catalog/admin.py` | Админка каталога | Добавить read-only `CatalogProcessingRun/Item/Change`. |

### 1.2 AI — существующий контур (legacy reference)

| Файл | Роль | Отношение к новому плану |
|------|------|--------------------------|
| `apps/ai/models.py` | `ContentFinding`, `FindingEvidence`, `SourcingRun`, `ExternalCall` | Остаётся legacy. Новый контур НЕ должен зависеть от `ContentFinding`. |
| `apps/ai/services.py` | `approve_and_apply_finding()`, `_persist_findings()` | Reference для idempotent get_or_create, но apply должен идти через `catalog.processing`. |
| `apps/ai/admin.py` | Moderation queue для `ContentFinding` | Не используется для нового контура. |
| `apps/ai/sourcing/guardrails.py` | `validate()` для `Finding` | Reference для source safety, forbidden targets, max text. |
| `apps/ai/sourcing/safety.py` | `host_allowed()` | Переиспользовать для evidence URL validation. |
| `apps/ai/metrics.py` | `SourcingCollector` | Reference; новые метрики для processing — отдельно. |

### 1.3 Data contracts

| Файл | Роль |
|------|------|
| `data/attribute_rules.json` | `source_priority` (`manual=100`, `regex=40`, `web/marketplace=25`, `llm=20`, `inferred=10`). Allowed attributes/options per tool_type. |
| `data/tool_type_rules.json` | Список допустимых tool_type категорий. |
| `data/group_mapping.json` | 1С group → site path. |

### 1.4 Docs / decisions

| Файл | Роль |
|------|------|
| `docs/ARCHITECTURE-AI.md` | Capability slice architecture, AiCallLog, guardrails. |
| `CLAUDE.md` | Правила репозитория: русский язык, catalog-first, границы модулей, Conventional Commits. |
| `docs/adr/ADR-0007-catalog-hierarchy-ownership.md` | Каталог — мастер сайта; `CategoryMappingRule`. |
| `docs/catalog-governance.md` | `content_locked` guard; цена/остаток — только 1С. |
| `docs/plans/catalog-taxonomy-redesign.md` | `tool_type` — вторая ось; бренд → `Product.brand`. |

### 1.5 Tests (паттерны)

| Файл | Роль |
|------|------|
| `apps/catalog/tests/test_provenance.py` | Baseline conflict, priority block, content lock, select option. |
| `apps/catalog/tests/test_enrichment_apply.py` | Fill-only-empty, moderation, attrs_cache rebuild. |
| `apps/ai/tests/test_sourcing_service.py` | Idempotency, content_locked, budget, baseline, error isolation. |
| `apps/ai/tests/test_sourcing_models.py` | Constraints/indexes tests. |

## 2. Что нужно создать/изменить

### 2.1 Foundation (Task 1–5 из `2026-07-17-CATALOG_PROCESSING_AUDIT_FOUNDATION.md`)

| Файл | Изменение |
|------|-----------|
| `apps/catalog/models.py` | `CatalogProcessingRun`, `CatalogProcessingItem`, `CatalogChange` + choices. |
| `apps/catalog/migrations/0024_catalog_processing_audit.py` | Additive schema (имя может отличаться — проверить `makemigrations --check --dry-run`). |
| `apps/catalog/processing.py` | `CatalogDecisionCommand`, `CatalogDecisionResult`, `apply_catalog_decision()`, snapshot/hash helpers. |
| `apps/catalog/admin.py` | Read-only run/item/change admin. |
| `apps/catalog/tests/test_processing_models.py` | Constraints и state transitions. |
| `apps/catalog/tests/test_processing_service.py` | Apply behavior, baseline, priority, content lock, idempotency. |
| `apps/catalog/tests/test_processing_concurrency.py` | Lock/idempotency. |
| `docs/ARCHITECTURE.md` | Catalog-owned audit boundary. |
| `docs/catalog/operations/README.md` | Новый обязательный путь записи. |

### 2.2 Queue + JSON transport (Phase 3 V2)

| Файл | Изменение |
|------|-----------|
| `apps/catalog/services.py` или `apps/catalog/processing.py` | `create_run()`, `add_item()`, `build_snapshot()`, export helpers. |
| `apps/catalog/management/commands/catalog_queue_create.py` | `--only-untyped --in-stock --limit --mode tool_type`. |
| `apps/catalog/management/commands/catalog_queue_export.py` | `--run <uuid>`. |
| `apps/catalog/management/commands/catalog_queue_import.py` | `--file ... --dry-run/--commit`. |
| `apps/catalog/management/commands/catalog_queue_status.py` | `--run <uuid>`. |
| `apps/ai/schemas/catalog_research_result_v1.json` | JSON Schema result v1 (можно позже переместить в `apps/catalog/schemas/`). |
| `var/catalog-processing/{outbox,inbox,reports,archive}/` | Already gitignored via `var/`. |

### 2.3 Skill (Phase 4 V2)

| Файл | Изменение |
|------|-----------|
| `.claude/skills/catalog-research/SKILL.md` | Project-local skill. |
| `.claude/skills/catalog-research/agents/openai.yaml` | Agent config. |
| `.claude/skills/catalog-research/references/source-policy.md` | Priority of sources, identity gate. |
| `.claude/skills/catalog-research/references/result-contract.md` | JSON result contract. |
| `.claude/skills/catalog-research/references/taxonomy-routing.md` | Allowed options, category/tool_type mapping. |

## 3. Ключевые архитектурные ограничения из кода

- **Направление зависимости:** `apps.ai -> apps.catalog`. `apps.catalog` не импортирует `apps.ai`.
- **Apply path:** `CatalogChange` → `apply_catalog_decision()` → `provenance.apply_sourced_value()`.
- **Source priority:** `manual(100) > import_1c(60) > regex(40) > keyword(30) > web/marketplace(25) > llm(20) > inferred(10)`.
- **Baseline hash:** канонический JSON с сортировкой ключей → SHA-256. `option_id` и `option_value` НЕ входят в conflict hash.
- **Idempotency:** `CatalogChange.idempotency_key` unique; повтор команды возвращает прежний результат.
- **Content lock:** проверяется в `apply_sourced_value()`; нельзя обходить.
- **Select/multiselect:** option ищется по slug, затем по value. Codex result должен возвращать slug.
- **attrs_cache:** `rebuild_attrs_cache()` пересобирает read-model после apply.

## 4. Mapping foundation tasks → файлы

| Task | Главные файлы | Acceptance criteria (кратко) |
|------|---------------|------------------------------|
| 1. Models & constraints | `models.py`, migration, `admin.py`, `test_processing_models.py` | Unique keys, confidence check, read-only admin. |
| 2. Snapshot & baseline | `processing.py`, `test_processing_service.py` | Stable hash, empty value envelope, no N+1. |
| 3. `apply_catalog_decision()` | `processing.py`, `test_processing_service.py` | Apply empty→option, conflict on baseline change, skip on weak source/lock, idempotency, exception→failed audit. |
| 4. Concurrency & integration | `test_processing_concurrency.py`, `test_provenance.py`, `test_sourcing_service.py` | Two decisions → at most one applied; catalog doesn't import ai. |
| 5. Docs & rollout | `docs/ARCHITECTURE.md`, `docs/catalog/operations/README.md` | Catalog-owned boundary documented. |

## 5. Ближайшие next steps

1. Создать/утвердить ADR: `CatalogChange` как новый proposal/audit-контракт; legacy-статус `ContentFinding`.
2. Добавить модели `CatalogProcessingRun`, `CatalogProcessingItem`, `CatalogChange` в `apps/catalog/models.py`.
3. Сгенерировать additive migration.
4. Реализовать snapshot/baseline helpers для `tool_type` в `apps/catalog/processing.py`.
5. Реализовать `apply_catalog_decision()` через `provenance.apply_sourced_value()`.
6. Добавить read-only Admin.
7. Написать unit/concurrency tests.
8. Проверить: `pytest apps/catalog/tests/test_provenance.py apps/ai/tests/test_sourcing_service.py -q`.
