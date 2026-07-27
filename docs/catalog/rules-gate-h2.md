# Independent machine gate (Wave 7.1 / H2)

> Status: canonical, 2026-07-23. Core: `apps/catalog/rules_gate.py`. Command: `catalog_rules_gate_validate`. Gate version: `2.0`.

## Проблема (Wave 7 finding B)

Старый gate доверял самодекларированным полям артефакта (`corpus_overlap_checked`, `collision_count`) и self-consistent паре sample↔labels: он не загружал ruleset/corpus/taxonomy и не пересчитывал predictions. Негативная проба (100 строк только с `product_id` + выдуманный `ruleset_hash`) давала `observed_precision=1.0`, `gate_passed=true`.

## Архитектура

Primary inputs (единственные доверенные): **ruleset**, **applied corpus**, **canonical taxonomy manifest (H1)**. Всё остальное — declared artifacts (sample, labels), чьи производные поля пересчитываются и сравниваются.

```
load primary inputs (schema + content validation)
  → ruleset ⊆ manifest, negative fixtures
  → corpus ⊆ manifest, facts_hash items
  → sample/labels (validate_gate_sample / validate_gate_labels)
  → hash binding: ruleset_hash == sample == labels; matcher_version; taxonomy_hash
  → matcher replay per row: facts_hash, evaluate_product → slug, rule_refs, collisions
  → overlap: sample ∩ corpus (вычисляемый, не доверенный)
  → metrics: decisions, precision (unrounded), Wilson 95%
  → declared mismatches (structured: field_path, declared, recomputed, severity)
  → gate policy → machine report
```

## Hash contract

- `ruleset_hash` — canonical_hash ruleset-файла (пересчитывается); sample и labels обязаны совпасть.
- `taxonomy_identity_hash` — из canonical manifest (H1). Declared `sample.taxonomy_hash`: mismatch → blocking; legacy samples (DB-order recipe, до H1) допускаются **только** явным `--allow-legacy-taxonomy-hash <hash>` (severity `legacy_recipe`). **С H4** замороженный 7D sample перевыпущен на canonical binding, поэтому штатный контур (и CI) флаг не использует; он остаётся исключительно для replay исторических артефактов.
- `manifest_semantic_hash`, `artifact_sha256` всех входов — в report для audit.

## Declared artifact policy

Declared-поля никогда не source of truth: `corpus_overlap_checked` и `collision_count` пересчитываются (overlap через corpus.product_ids; collisions через replay). Declared значение ≠ recomputed → blocking mismatch; declared поле отсутствует → warning, recomputed значение авторитетно. `corpus_overlap_checked` — вычисленный результат, не доверенный вход.

## Exit codes

- `0` — gate passed (blocking_errors=0 и recomputed metrics ≥ thresholds);
- `1` — валидная оценка, thresholds не пройдены (precision < 0.99 или rows < 100);
- `2` — invalid inputs/schema/hash/provenance/blocking;
- `3` — internal execution error.

## Использование

```bash
# frozen Phase 7D sample — canonical binding (H4), поблажка не нужна
python manage.py catalog_rules_gate_validate \
  --gate-sample apps/catalog/tests/fixtures/phase7d-gate-sample-official.json \
  --labels apps/catalog/tests/fixtures/phase7d-labels.json \
  --out report.json [--force] [--format json]

# произвольные входы
python manage.py catalog_rules_gate_validate \
  --gate-sample … --labels … \
  [--ruleset PATH] [--corpus PATH] [--taxonomy-manifest PATH]

# исторический артефакт с legacy DB-order binding — только явным флагом
python manage.py catalog_rules_gate_validate \
  --gate-sample … --labels … \
  --allow-legacy-taxonomy-hash b357be6048…326b
```

Команда не пишет в БД, не меняет feature flags, не применяет predictions.
