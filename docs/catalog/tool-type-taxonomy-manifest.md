# Canonical tool_type taxonomy manifest (Wave 7.1 / H1)

> Status: canonical, 2026-07-23. Manifest: `data/catalog_processing_rules/tool_type_taxonomy.v1.json` (manifest_version 1). Loader/validation/hashes: `apps/catalog/taxonomy_manifest.py`.

## Source-of-truth boundary

- **Canonical source operational taxonomy** (slug/value/sort_order для `Attribute(slug="tool_type")`) — только manifest. Чистая БД воспроизводит его детерминированно через `load_tool_types` (seed).
- **`data/tool_type_rules.json`** — legacy extraction rules (keywords, priority, recat-маркеры). Больше НЕ источник materialization options; его extraction semantics заморожены в H1.
- **БД (staging/production)** — downstream manifest, не источник. Drift измеряется `catalog_taxonomy_reconcile` (read-only). Инвариант: `live == manifest` (blocking drift = 0); отклонения — только versioned approved exceptions в manifest, не в БД.
- **`data/catalog_processing_rules/tool_type_taxonomy_export.v1.json`** (Phase 7A) — исторический evidence-снимок, superseded manifest'ом.

## Hash-контракты (не смешиваются с legacy `_taxonomy_hash`)

- `taxonomy_identity_hash` — runtime identity: sha256 канонического (code-point sorted) списка `{slug, value}`. sort_order/PK/display metadata не входят; environment-independent. Legacy `_taxonomy_hash` (`queue_contract`) order-sensitive и зависит от DB collation — остаётся в shadow/gate контуре до H2/H3 и с новыми hashes не смешивается.
- `manifest_semantic_hash` — audit: sha256 семантического содержимого (versions + полные записи options).
- `artifact_sha256` — байты файла (pinning для release manifest; в файле не хранится).

## Runtime-контракт

Seed/gate/apply используют только `{slug, value}`. Поля `origin_kind/origin_ref`, `review_status/review_reason/review_ref`, `legacy_aliases` — audit-only: в БД не загружаются, reslug/remapping не вызывают. Aliases не создаются как options.

## Операции

- **Seed**: `manage.py load_tool_types [--manifest PATH] [--update-display]`. Создаёт отсутствующие options по slug; идемпотентен; ничего не удаляет и не переслагивает; fail-closed при несовместимом slug/value; `sort_order` существующих — только с `--update-display`.
- **Reconciliation**: `manage.py catalog_taxonomy_reconcile [--manifest PATH] [--format text|json] [--fail-on blocking|any] [--ruleset PATH]`. Read-only. Blocking: `missing_in_live`, `unexpected_in_live`, `slug_value_mismatch`, `used_outside_manifest`, `ruleset_unknown_slug`. Advisory: `semantic_duplicate`, `manifest_unused_option`, `display_metadata_mismatch`, `pending_business_review`.
- **Runtime guards**: `enrich_tool_type` и `backfill_option_slugs` не создают options вне manifest (fail-closed / advisory-счётчик). Единственный путь новых option — manifest + seed.

## Изменение taxonomy

1. Правка manifest (новая `manifest_version`) + review.
2. `load_tool_types` на целевой среде.
3. `catalog_taxonomy_reconcile` → blocking drift = 0.

## Future evolution: immutable option identity

`option_uid` НЕ реализован (по owner decision). Путь эволюции: manifest_version 2 добавит каждой option стабильный `option_uid` (например UUIDv5 от namespace + slug на момент введения), неизменный при переименовании value или reslug. `taxonomy_identity_hash` при этом не меняется (slug/value остаются runtime contract). Consumers (provenance `CatalogChange.evidence`, release manifests, AI findings) начнут записывать `option_uid` рядом со slug; позднее `option_uid` станет primary reference для cross-release ссылок, slug останется operational key в БД.
