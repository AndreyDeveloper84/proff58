# TT-07 · протокол: пакет из 5 типов + re-gate + seed на обеих БД

Дата: 2026-07-28. Ветка `dev`. Окно: одно (то же, что TT-06/TT-08).
Состав пакета утверждён владельцем в переписке (4 типа + пятый `bp-leska`
по предложению окна; value четвёртого — «Гайковёрты» без скобок, решение
владельца). Коммит: **`65a350d`** (10 файлов, +87/−28, точечные пути,
чужие изменения CAT-06/PARS не затронуты). Push не выполнялся.

---

## 1. Состав (утверждён до правки манифеста)

| slug | value | ниша (оценка read-only) |
|---|---|---|
| `bp-leska` | Леска триммерная | 214 SKU (193 в `prochaya-osnastka`) |
| `gaikoverty` | Гайковёрты | ~110 SKU (108 в `dreli-shurupoverty`) |
| `gaikoverty-ruchnye` | Гайковёрты ручные | ~6 SKU |
| `svar-katody` | Катоды (электроды) плазмотронов | 2 SKU |
| `zap-boyki` | Бойки и ударники | ~17 SKU |

Обоснования «почему не подходит ни один из 329» — `scratchpad/catalog/tt-07-proposal.md`
(перебор всех 15 `svar-*` для катодов; родственных ключей для гайковёртов;
`zap-*`/оснастки для бойков; расходников `bp-*` для лески). Предложение →
утверждение → правка — порядок соблюдён, манифест не правился до утверждения.

## 2. Манифест и хэши

`data/catalog_processing_rules/tool_type_taxonomy.v1.json`: +5 опций в
алфавитные позиции, метаданные `origin_kind=manual_backport`,
`origin_ref="phase8 step3 + owner decision 2026-07-28 (TT-07)"`,
`review_status=approved`, `review_ref=tt-07`, per-type `review_reason`.
Диф файла: +57/−2 (5 опций × 11 строк + 2 хэш-строки).

```
options:                  329 → 334
taxonomy_identity_hash:   524d4e317a80… → 887eea5d442455fbb97c9eda888c0307f46a1f7e2e51bd56c2bd8a11d3949175
manifest_semantic_hash:   5ebbad744c0e… → 2911b659f3d1079ec5e6a2b1ad185b9cf39efb7c8bcfb7c10ba9227027404d4f
```

Fail-closed валидация `load_manifest()` (JSON Schema + content) — пройдена.

## 3. Gate-артефакты — ровно две строки, разметка не тронута

- `phase7d-gate-sample-official.json`: строка `taxonomy_hash` → `887eea5d…`;
- `phase7d-labels.json`: строка `sample_hash` → `4554d32c…`
  (`canonical_hash(sample)` пересчитан после правки; sanity ДО: старый
  `sample_hash` == `canonical_hash` старого sample — проверено).

Диф фикстур: **2 файла × 1 строка = ровно две строки**. `rows=103`,
`correct=102`, `unverifiable=1` — не сдвинулись (подтверждено прогоном гейта);
множество `product_id`, ground truth, `decision`, `rationale`, `reviewer_id`,
`reviewed_at` — идентичны (диф только в двух строках).

## 4. Гейт и release manifest

```bash
python manage.py catalog_rules_gate_validate \
  --gate-sample apps/catalog/tests/fixtures/phase7d-gate-sample-official.json \
  --labels apps/catalog/tests/fixtures/phase7d-labels.json
# rows=103 correct=102 unverifiable=1, precision=0.9903, wilson95=[0.947, 0.998]
# gate_passed=true, EXIT=0 — без --allow-legacy-taxonomy-hash

python manage.py catalog_rules_release_manifest --force   # canonical_hash=a9963c7d…
python manage.py catalog_rules_release_manifest --check   # check=ok, EXIT=0
```

Release manifest перевыпущен **тем же коммитом** (`65a350d`), что и sample.

## 5. Пины и документация

Обновлены (тем же коммитом): `test_taxonomy_manifest.py` (PINNED_IDENTITY/
SEMANTIC_HASH, 334), `test_rules_release.py` (CANONICAL_TAXONOMY_HASH, 334),
`test_h5_canonical_downgrade_e2e.py` (334/330/330/330), `.github/workflows/tests.yml`
(комментарий binding), `CLAUDE.md` §7 (`887eea5d…`, 334 options),
`docs/catalog/rules-release-manifest.md`. Остаточные `524d4e31…` — только
исторические (планы, acceptance report, пример снимка в reverse-migration.md);
как «текущее состояние» старый хэш нигде не остался.

## 6. Seed на обеих БД

- **Локально:** `load_tool_types` → `created=5, present=329,
  display_updated=0, display_mismatch=0` (fail-closed, no-delete).
- **Staging:** pg_dump `/home/taximeter/backups/staging/db-2026-07-29-0121.sql.gz`
  → манифест доставлен в контейнер (image без bind-mount кода — файл записан
  в fs контейнера; доедет штатно с деплоем коммита) → `load_tool_types`:
  `created=5` (повторный `created=0, present=334` — идемпотентно).
- **reconcile обеих БД:** manifest 334, `identity_equal=True`,
  **blocking = 0**; advisory `manifest_unused_option = 9` (5 новых + 4
  прежних неиспользуемых — ожидаемо до TT-08).

## 7. Regression

Отдельная БД `proff58_tt07reg` (`--create-db`, `-p no:pylama`, вывод в файл
`scratchpad/catalog/tt-07-pytest.log`):

```
2 failed, 2060 passed, 1 skipped in 452.83s
FAILED tests/test_regression_mvp.py::test_healthcheck_returns_ok       (нет Redis — known)
FAILED tests/test_deploy_release.py::test_release_script_is_executable (Windows exec bit — known)
```

Арифметика: `--collect-only` = **2063** = 2 known failed + 2060 passed +
1 skipped. Сходится. **Третьего падения нет.** Δ к прогону TT-06 (+9) —
чужие незакоммиченные добавления CAT-06 (`test_facets.py` +43 строки);
мой коммит новых тестов не добавляет (только пины). Затронутые пинами
тесты отдельно: 56 passed (`test_taxonomy_manifest`, `test_rules_release`,
`test_h5_canonical_downgrade_e2e`, `test_rules_gate_validate`).

## 8. Границы

- Манифест правился только после утверждения состава владельцем; value
  существующих 329 не менялись (диф — только +5 опций и 2 хэш-строки).
- Matcher (`evaluate_product`, `facts_hash`), ruleset v2, applied corpus не
  тронуты (гейт это подтверждает пересчётом).
- Коммит — точечными путями (10 файлов); чужие изменения (CAT-06:
  `admin/facets/models/queries/test_facets/enrich_attributes`,
  `data/attribute_rules.json`) не staged, не откатывались.
- Push/PR не выполнялись; глобальные команды не запускались; ступень 4
  (batch 50) не начиналась.

## 9. Артефакты

- Коммит `65a350d`; предложение `scratchpad/catalog/tt-07-proposal.md`;
  редактор манифеста `scratchpad/catalog/tt07_edit_manifest.py`;
  лог regression `scratchpad/catalog/tt-07-pytest.log`;
  staging pg_dump `db-2026-07-29-0121.sql.gz`.
- Этот протокол: `scratchpad/catalog/tt-07-report.md`.
