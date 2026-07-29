# Wave 7.1 / Stage H2 — протокол исполнения (independent machine gate)

> По авторизации H2 (2026-07-23). Scope: gate validation/reporting + чистые helpers. Matcher semantics, v2 ruleset, corpus, canonical manifest, enrichment, apply pipeline, Phase 8 — не тронуты.

## 1. Implementation audit (подтверждено перед изменениями)

- `catalog_rules_gate_validate` (старая версия, 107 строк): только `validate_gate_labels` + проверка самодекларированных `corpus_overlap_checked`/`collision_count`; ruleset/corpus/taxonomy не загружались; `validate_gate_sample` существовал, но не вызывался. **Trust boundary:** на веру принимались ruleset_hash/taxonomy_hash/matcher_version (self-consistency пары), predictions, rule_refs, facts_hash, overlap, collisions; пересчитывалась только согласованность sample↔labels и precision.
- Негативная проба (Wave 7): fabricated sample 100×{product_id} + выдуманный ruleset_hash → `observed_precision=1.0`, `gate_passed=true` (воспроизведено: `scratchpad/wave7/bogus-*.json`).
- Реальные контракты, использованные в pipeline: `evaluate_product` → ProductVerdict (prediction/collision/no_match/excluded), facts_hash = `canonical_hash({name, original_name, brand, source_group, article})`, `load_ruleset` (schema+semantics), `load_corpus` (schema+counters+facts_hash), H1 `taxonomy_manifest.load_manifest`. Corpus: 54 items, 32 slugs, все ⊆ manifest (проверено 2026-07-23).

## 2. Commits

| # | SHA | Содержание |
|---|---|---|
| 1 | `4c55e38e77f60deede1f07aacc640f21c3551c29` | `apps/catalog/rules_gate.py` (независимый pipeline), `apps/catalog/tests/test_rules_gate.py` (28 тестов), versioned fixtures `apps/catalog/tests/fixtures/phase7d-gate-sample-official.json` + `phase7d-labels.json` (byte-identical 7D: `873ee2a1…`, `4cb05d36…`) |
| 2 | `193e35eb8941237352f8d733a9553138f4265997` | команда `catalog_rules_gate_validate` на pipeline (exit codes 0/1/2/3, `--ruleset/--corpus/--taxonomy-manifest/--allow-legacy-taxonomy-hash/--format/--out/--force`), переписанный `test_rules_gate_validate.py` (9 тестов), `docs/catalog/rules-gate-h2.md` |

## 3. Independent gate architecture

Primary inputs: ruleset, applied corpus, canonical taxonomy manifest. Derived (не доверяются, пересчитываются): predictions, rule_refs, facts_hash, overlap, collision_count, taxonomy/ruleset hashes, decisions summary, precision, Wilson 95%, gate_passed. Declared поля — structured mismatches (field_path/declared/recomputed/severity: blocking|warning|legacy_recipe).

Pipeline: manifest (H1 loader) → ruleset (schema/semantics/fixtures, ⊆ manifest) → corpus (schema/counters/facts, ⊆ manifest) → sample/labels (`validate_gate_sample`/`validate_gate_labels`) → hash binding → **matcher replay per row** (facts_hash → `evaluate_product` → slug/rule_refs/collisions) → overlap (computed) → metrics (precision unrounded + Wilson 95%) → declared comparison → policy → machine report (schema_version=1, gate_version=2.0).

Exit codes: 0 passed; 1 thresholds не пройдены; 2 invalid inputs/schema/hash/provenance/blocking; 3 internal.

## 4. Legacy taxonomy hash (D-H2.1)

`sample.taxonomy_hash` сверяется с canonical `taxonomy_identity_hash`. Frozen 7D sample несёт legacy DB-order hash (`b357be60…`): mismatch → blocking, **кроме** явного `--allow-legacy-taxonomy-hash <hash>` (severity `legacy_recipe`, warning). Semantic taxonomy coverage (все slugs ⊆ manifest) проверяется независимо в любом случае. Legacy и canonical hashes не смешиваются (owner direction).

## 5. Frozen sample — recomputed metrics (через pipeline)

- rows=103, correct=102, unverifiable=1; precision = 102/103 = 0.9902912621359223 (recomputed);
- Wilson 95% = [0.947042, 0.998284] (recomputed, совпадает с 7D stats);
- replay: 103/103 checked, predictions/rule_refs/facts_hash совпали, collisions_recomputed=0;
- overlap computed empty (corpus 54 items); blocking_errors=[]; gate_passed=true (с `--allow-legacy-taxonomy-hash b357be60…`).

## 6. Negative matrix (все → fail-closed, exit 2, кроме отмеченных)

tampered ruleset_hash / labels.sample_hash / taxonomy_hash (без флага) / facts_hash / predicted slug / rule_refs / declared slug вне manifest / ruleset slug вне manifest / duplicate rule_ref / corrupted manifest / overlap с corpus (при declared=true) / duplicate sample id / conflicting labels / missing ground truth / unknown decision / declared collision_count ≠ recomputed. Declared collision_count отсутствует → warning, exit 0 (recomputed авторитетно); declared corpus_overlap_checked=false → warning, exit 0. Thresholds: precision 0.97 → exit 1; rows=99 → exit 1. Permutation rows/labels — инвариант. Determinism: два прогона — идентичный report (кроме generated_at).

## 7. Regression

- Catalog suite: **321 passed, 1 skipped** (324 − 12 старых gate-тестов + 9 новых).
- `manage.py check` — 0 issues; `makemigrations --check --dry-run` — no changes; ruff/black clean.
- Полный suite — см. ниже (фон).

## 8. Оставшиеся риски

- P2: declared sample size поле отсутствует в контракте артефакта v1 (нет отдельного size-поля; покрыто rows=len + threshold + unique ids + coverage).
- P2: `generated_at` делает report не byte-stable (по контракту; canonical evidence исключает его).
- P2: pipeline DB-independent, но default ruleset — текущий RULESET_PATH; для исторических replay — явный `--ruleset`.

## Full regression suite

**2 failed, 1806 passed, 1 skipped (511.93s)** — только 2 известных environmental baseline failure (`tests/test_regression_mvp.py::test_healthcheck_returns_ok` — redis; `tests/test_deploy_release.py::test_release_script_is_executable` — Windows exec bit; сигнатуры идентичны pinned baseline). Catalog suite: 321 passed, 1 skipped.
