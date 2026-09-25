# TT-14 · Протокол: пакет из двух типов (триммерные головки + воронки)

Дата: 2026-07-31. Ветка `feature/tt-14-taxonomy-batch`, worktree `.worktrees/tt-14`
от свежего `origin/dev` (f6a99eb). Коммит пакета: **ee169b7** (amend c4a99ef:
опции в файле отсортированы по slug — `test_manifest_file_is_canonically_ordered`).

Образец процедуры — TT-07 (`scratchpad/catalog/tt-07-report.md`).

## 1. Состав пакета (утверждён владельцем до правки манифеста)

| slug | value | sort_order | ниша |
|---|---|---|---|
| `bp-golovki-trimmernye` | Головки триммерные | 23 | 108 SKU (стенд; локально 106) — 93× `prochaya-osnastka`, 6× `krep-gaiki`, 4× `krep-bolty`, 5× без типа |
| `hoz-voronki` | Воронки | 36 | 21 SKU — 19× без типа, 1× `obor-smazka`, 1× `svar-sopla` |

Проверка соседей перед утверждением: `bp-leska` (TT-07) и `bp-trimmery` — та же
ниша расходников к триммерам; существующие `golovki` (торцевые ключи),
`golovki-shlif` (шлифовальные), `siz-golovki` (пожарные) — другие ниши.
Воронок в словаре нет; 16/21 в группе 1С «Хозтовары, сад, огород» → префикс `hoz-`.
Владелец утвердил оба slug без изменений.

## 2. Манифест

```
options:                  334 → 336
taxonomy_identity_hash:   887eea5d442455fbb97c9eda888c0307f46a1f7e2e51bd56c2bd8a11d3949175
                       → 7ac7a9a26eeffcb6360993b3c1a5942ddee4da7c80b8e31ad9b47853e2a06ef9
manifest_semantic_hash:   2911b659f3d1079ec5e6a2b1ad185b9cf39efb7c8bcfb7c10ba9227027404d4f
                       → 9958cfcd520475572b346ecfcfd98cae005d4da8f0e00a8f179fda120b8f353d
```

- Опции добавлены скриптом с метаданными по образцу `bp-leska`
  (`origin_kind=manual_backport`, `origin_ref="phase8 step4 niches + owner decision
  2026-07-31 (TT-14)"`, `review_status=approved`, `review_ref=tt-14`) и вставлены
  в каноническую позицию по slug (инвариант `test_manifest_file_is_canonically_ordered`;
  identity_hash от порядка не зависит, semantic_hash пересчитан после сортировки).
- Хэши пересчитаны штатными `taxonomy_identity_hash()` / `manifest_semantic_hash()`
  из `apps/catalog/taxonomy_manifest.py`, не руками; `validate_manifest_doc()` — 0 violations.
- Диф манифеста: +24 строки (2 опции) и 2 изменённые hash-строки. Множества slug
  до/после: удалено — ∅, добавлено — {bp-golovki-trimmernye, hoz-voronki}.
- Технический нюанс: первая запись из Windows Python перевела LF→CRLF
  (`.gitattributes`: `-text` для `data/catalog_processing_rules/*.json`),
  переписано байтово в LF — итоговый диф чистый.

## 3. Gate-артефакты — ровно две строки, разметка не тронута

- `phase7d-gate-sample-official.json`: строка `taxonomy_hash` → `7ac7a9a2…`;
- `phase7d-labels.json`: строка `sample_hash` → `a68ff6b37edc3d1dff7e31c7cdef10776fe81feba2594b01eb44c774119cac50`
  (`canonical_hash(sample)` пересчитан после правки; sanity ДО: старый
  `sample_hash` == `canonical_hash` старого sample — True, `acc7c83df1a8…`).

Диф фикстур: **2 файла × 1 строка = ровно две строки** (у фикстур нет trailing
newline — сохранено байтово). Множество `product_id`, ground truth, `decision`,
`rationale`, `reviewer_id`, `reviewed_at` — идентичны.

## 4. Гейт и release manifest

```bash
python manage.py catalog_rules_gate_validate \
  --gate-sample apps/catalog/tests/fixtures/phase7d-gate-sample-official.json \
  --labels apps/catalog/tests/fixtures/phase7d-labels.json
# rows=103 correct=102 unverifiable=1, precision=0.9903 (0.9902912621359223),
# wilson95=[0.947041, 0.998284], replay checked=103 collisions=0,
# gate_passed=true, EXIT=0 — без --allow-legacy-taxonomy-hash

python manage.py catalog_rules_release_manifest --check
# drift по taxonomy_manifest/gate_sample/labels — ожидаемо до перевыпуска
python manage.py catalog_rules_release_manifest --force
# canonical_hash=76bc9d70d2034d5cda3f8217b9a2950f82400d642db21716c5e0beda163c7bbb
python manage.py catalog_rules_release_manifest --check
# check=ok, EXIT=0
```

Release manifest перевыпущен **тем же коммитом** (`ee169b7`), что и sample.

## 5. Пины и документация

Обновлены (тем же коммитом): `test_taxonomy_manifest.py` (PINNED_IDENTITY/
SEMANTIC_HASH, 336), `test_rules_release.py` (CANONICAL_TAXONOMY_HASH, 336),
`test_h5_canonical_downgrade_e2e.py` (336/332/332/332), `test_queue_commands.py`
(startswith `7ac7a9a2`), `.github/workflows/tests.yml` (комментарий binding),
`CLAUDE.md` §7 (`7ac7a9a2…`, 336 options), `docs/catalog/rules-release-manifest.md`.
Остаточные `887eea5d…` — только исторические (планы, отчёты, артефакты
scratchpad, упоминания «до этого» в тех же файлах); как «текущее состояние»
старый хэш нигде не остался.

## 6. Seed и reconcile (локально)

- `load_tool_types` → `created=2, present=334, display_updated=0,
  display_mismatch=0` (fail-closed, no-delete). EXIT=0.
- `catalog_taxonomy_reconcile` → `identity_equal=True`, все blocking = 0,
  EXIT=0. Advisory `manifest_unused_option`: 8 (2 новых + 6 ранее известных:
  `hoz-schetchiki`, `metchiki`, `osnastka-rezbonarez`, `plashki`, `svar-katody`,
  `zap-boyki` — ожидают своих recat-окон).
- **Стенд — отдельный шаг после деплоя** с `-e FEATURE_CATALOG_PROCESSING=True`.

## 7. Товары не тронуты

PAV `tool_type` (локальная БД) до и после:

```
count:       38833 → 38833
fingerprint: c0b4e8f652db917cf0e571b6c4c4ec92f105fe9d396584eee42d6e954e4c52df (идентичен)
```

sha256 от упорядоченного списка `(product_id, value_text)` по
`ProductAttributeValue(attribute=tool_type)`. На стенде инвариант владельца —
PAV `tool_type` = 38 877 (проверяется приёмщиком).

## 8. Кандидаты на перенос (для следующего окна, recat)

Артефакт: `scratchpad/catalog/tt-14-recat-candidates.json` — 106 головок + 21
воронка с `product_id`, `original_name`, текущим `tool_type`, группой 1С.
Собран read-only по локальной БД; на стенде по step4 — 108 головок (72 активных)
и 21 воронка (5 активных). Перед recat пересобрать на стенде.
`tool_type` товарам **не записывался**.

Локальное распределение головок: `prochaya-osnastka` ×90, `krep-gaiki` ×6,
`krep-bolty` ×4, без типа ×6. Воронки: без типа ×20, `svar-sopla` ×1.

## 9. pytest

```
pytest apps/catalog -p no:pylama -q
1163 passed, 1 skipped in 217.17s
```

Первый прогон поймал нарушение инварианта канонической сортировки опций в файле
(`test_manifest_file_is_canonically_ordered`) — опции переставлены по slug,
semantic_hash пересчитан (`92b0a2d5…` → `9958cfcd…`), release manifest
перевыпущен повторно, коммит amend → `ee169b7`. Повторный прогон — чистый,
падений нет.

## 10. Границы

- Правила распознавания (`tool_type.v2.json`) не тронуты; matcher, applied
  corpus не менялись (гейт подтверждает пересчётом).
- Существующие опции не переименованы и не удалены; `legacy_aliases` не менялись.
- Поблажка `--allow-legacy-taxonomy-hash` не включалась ни на одном шаге.
- Глобальные команды (`enrich_attributes` без `--path`, `rebuild_attrs_cache`)
  не запускались.
- Push/PR не выполнялись (только по явной просьбе владельца).
