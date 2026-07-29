# Wave 7.1 / Stage H3 — протокол исполнения (default v2 CI replay + release manifest)

> По плану `docs/plans/2026-07-26-WAVE7_1_H3_H5_PLAN.md` §4. Scope: контроль поверх контура (CI job, release manifest, команда, docs, тесты). Semantics матчера (`evaluate_product`, `facts_hash`), содержимое ruleset v2, applied corpus, canonical taxonomy manifest, enrichment/apply pipeline, Phase 8 — не тронуты.
> **Push и PR не выполнялись** (запрет владельца). На момент старта окна коммиты H2 были только локально; фактически владелец запушил их в ходе сессии — на момент закрытия протокола `origin/dev = 989aec6` (H2 внутри), а `dev` ahead 4 — это ровно коммиты H3. Джоба доказана локальным исполнением её шагов; зелёный прогон на GitHub появится после push H3.

## 1. Commits

| # | SHA | Содержание |
|---|---|---|
| 1 | `0246c58` | `apps/catalog/rules_release.py` (build/serialize/load/diff), команда `catalog_rules_release_manifest` (генерация + `--check`), артефакт `data/catalog_processing_rules/rules_release_manifest.v1.json`, `.gitattributes` (LF-пиннинг), перенос `DEFAULT_CORPUS_PATH` в `rules_gate`, 28+9 тестов |
| 2 | `b65fdde` | джоба `catalog-rules-gate` в `.github/workflows/tests.yml` (gate на frozen 7D sample против default ruleset + `release_manifest --check`) |
| 3 | `17b81f9` | `docs/catalog/rules-release-manifest.md`, CLAUDE.md §7 (модуль, артефакт, команда, CI-джоба) |
| 4 | `67349e4` | чистка: неиспользуемый параметр `_emit` |

## 2. Архитектура H3

**Release manifest** — детерминированная фиксация версии контура поверх *пройденного* gate 2.0. Документ: `{"canonical": {...}, "canonical_hash": sha256(canonical)}`.

- `canonical.inputs` — по блоку на каждый первичный вход: `ruleset` (path/ruleset_id/version/rules/`ruleset_hash`/`artifact_sha256`), `corpus` (corpus_id/items/sha), `taxonomy_manifest` (manifest_version/options/`taxonomy_identity_hash`/`manifest_semantic_hash`/sha), `gate_sample` (rows/sha), `labels` (labels/sha);
- `canonical.gate` — `gate_passed`, `legacy_taxonomy_hash_allowed`, `metrics` (rows/correct/decisions/precision без округления/Wilson 95%), `thresholds`, `declared_mismatches`, `warnings`, `report_schema_version`;
- `canonical` содержит `matcher_version` (`1.0`) и `gate_version` (`2.0`);
- **`generated_at` в файл не пишется** — non-canonical, выводится в stdout. Именно поэтому файл байт-стабилен;
- пути — POSIX относительно `BASE_DIR` (портабельность Windows ↔ CI);
- всё содержимое — пересчитанное через `run_independent_gate` (H2 declared-artifact policy); declared-поля попадают только в `declared_mismatches` как объект сравнения.

**Fail-closed:** manifest не выпускается, если gate не прошёл — команда завершается его exit code (1 thresholds / 2 blocking), файл не создаётся и не изменяется.

**Команда** `catalog_rules_release_manifest`: генерация (идемпотентно: байт-идентичный файл → `unchanged`, отличающийся → нужен `--force`) и `--check` (режим CI). Флаги входов те же, что у gate (`--ruleset/--corpus/--taxonomy-manifest/--gate-sample/--labels/--allow-legacy-taxonomy-hash`), плюс `--manifest/--check/--force/--format`. Exit codes: 0 ok; 1 thresholds; 2 invalid inputs / blocking gate / битый `canonical_hash` / расхождение с зафиксированным; 3 internal. В БД не пишет.

**CI-джоба `catalog-rules-gate`** в переиспользуемом `tests.yml` (вызывается из `ci.yml` на PR и `deploy.yml` перед деплоем), два шага: (1) `catalog_rules_gate_validate` на замороженном 7D sample против **default** ruleset, (2) `catalog_rules_release_manifest --check`. Exit code команды = статус джобы. Сервисы Postgres/Redis не поднимаются — контур DB-independent. Legacy-поблажка вынесена в `LEGACY_TAXONOMY_HASH` на уровне джобы, снимается в H4.

### Побочная находка (исправлена в коммите 1)

`artifact_sha256` считается по сырым байтам, а `core.autocrlf=true` держал в рабочей копии Windows CRLF-версии `tool_type.v2.json` и `applied_corpus_tool_type.v1.json` (blob в git — LF). Манифест, сгенерированный на Windows, не сошёлся бы с CI (`git show` sha ≠ worktree sha: `ff449701…`/`6663a6fe…` против `5c12db44…`/`32511e85…`). Добавлен `.gitattributes` (`-text` на `data/catalog_processing_rules/*.json` и `apps/catalog/tests/fixtures/*.json`), рабочая копия перечитана из blob, манифест перевыпущен на LF-байтах. Тест `test_primary_inputs_are_lf_pinned` закрывает регресс.

## 3. Проверки (доказательства)

**Байт-стабильность** — три независимых прогона (`data/...v1.json`, `scratchpad/rel-run1.json`, `scratchpad/rel-run2.json`), sha256 файлов идентичны:

```
2324e183a04afeee0d44e2771d907acf37e7bd743480ac5a7cba070a6b8f67fe *rules_release_manifest.v1.json   (до LF-фикса)
2324e183…  *rel-run1.json
2324e183…  *rel-run2.json
```

После LF-нормализации артефакт перевыпущен: `canonical_hash=f43d6e0d3b55af12bd55727dabe3bb054fb457eb4113033b3dc850b89e82c223`, повторный прогон → `unchanged (байт-идентичен)`, `--check` → `check=ok`. Отдельно закреплено тестами `test_two_builds_are_byte_identical`, `test_canonical_has_no_timestamp_fields`, `test_committed_manifest_matches_recomputed`.

**Зафиксированная версия контура** (LF-байты, ровно то, что увидит CI):

```
matcher_version=1.0 gate_version=2.0 schema_version=1
ruleset=data/catalog_processing_rules/tool_type.v2.json id=tool_type.v2 rules=38
  ruleset_hash=9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330
corpus=data/catalog_processing_rules/applied_corpus_tool_type.v1.json
  id=staging-tool-type-6ebb8ac9d856 items=54
taxonomy identity=fc13be7804b06713dccde5cd2888a437a1a7521772d5911acc7d9d93636714d8
  semantic=91b3ed0c1f7b2bd08c63fe9460b43c20cdf04fa748921465589d1c90b7058b16 options=328
gate rows=103 correct=102 precision=0.9902912621359223 wilson95=[0.947041, 0.998284]
canonical_hash=f43d6e0d3b55af12bd55727dabe3bb054fb457eb4113033b3dc850b89e82c223
```

**Локальное исполнение шагов CI-джобы** (те же команды, что в `tests.yml`):

```
step 1  catalog_rules_gate_validate … --allow-legacy-taxonomy-hash $LEGACY_TAXONOMY_HASH
        gate_passed=true (recomputed precision>=0.99 and rows>=100 and blocking_errors==0)   EXIT=0
step 2  catalog_rules_release_manifest --check --allow-legacy-taxonomy-hash $LEGACY_TAXONOMY_HASH
        check=ok (зафиксированный manifest совпадает с пересчитанным)                        EXIT=0
```

**DB-independence джобы** (обоснование отсутствия сервисов): прогон gate с заведомо мёртвым `DATABASE_URL=postgres://nobody:nobody@127.0.0.1:1/nodb` → `gate_passed=true`, EXIT=0.

**YAML-валидность** `tests.yml`: jobs = `lint, frontend, test, catalog-rules-gate`, шаги распарсились.

## 4. Негативная матрица (все → ненулевой exit)

| Сценарий | Ожидание | Результат |
|---|---|---|
| испорченный ruleset (временная копия в scratchpad, добавлено keyword `tampered-h3`) → gate | exit 2 | `blocking: declared mismatch sample.ruleset_hash: declared='9bf0271a…' != recomputed='6def50a0…'` (+ labels.ruleset_hash), **EXIT=2** |
| тот же ruleset → `release_manifest --check` | exit 2, manifest не выпущен | `CommandError: release manifest не выпущен: blocking gate errors: … sample.ruleset_hash …`, **EXIT=2** |
| зафиксированный manifest подделан без пересчёта `canonical_hash` | exit 2 | `canonical_hash не соответствует содержимому canonical: записан 'b6fa8a61…', пересчитан 'f4cf4ae3…'`, **EXIT=2** |
| manifest самосогласован, но разошёлся с пересчётом (`precision=1.0`, `rules=999`) | exit 2 + структурный дифф | `drift: canonical.gate.metrics.precision: зафиксировано=1.0, пересчитано=0.9902912621359223`; `drift: canonical.inputs.ruleset.rules: зафиксировано=999, пересчитано=38`, **EXIT=2** |
| `--check` без `--allow-legacy-taxonomy-hash` | exit 2 | blocking taxonomy_hash (H2-политика сохранена) |
| файл manifest отсутствует / битый JSON / нет секции `canonical` | exit 2 | `не найден` / `не валидный JSON` / `без секции canonical` |
| gate thresholds (sample обрезан до 99 строк) | exit 1, manifest не выпущен | `document is None`, `outcome.exit_code == 1` |
| существующий отличающийся файл без `--force` | exit 2, файл не тронут | `release manifest уже существует и отличается (используйте --force)` |

Все строки матрицы, кроме подготовки временных копий вручную, закреплены тестами (`test_rules_release.py`, `test_rules_release_manifest.py`). Испорченные артефакты создавались только во временных каталогах — `data/` не изменялся (кроме штатного выпуска release manifest).

## 5. Regression

- Новые тесты: **17** (`test_rules_release.py`) + **11** (`test_rules_release_manifest.py`) = **28**.
- Catalog suite (`pytest apps/catalog/tests`): **349 passed, 1 skipped** (было 321+1 в H2; +28 новых).
- `manage.py check` — 0 issues; `makemigrations --check --dry-run` — no changes.
- ruff/black — clean (по tracked-файлам, миграции исключены; ошибки `ruff check .` относятся к неотслеживаемым scratch-скриптам в корне и существовали до H3).
- Полный suite — см. ниже.

## 6. Оставшиеся риски

- P1: джоба **не проверена на GitHub** — `dev` ahead 4 от `origin/dev` (`989aec6`), это коммиты H3. Первый реальный прогон CI будет после их push; локально исполнены те же команды с теми же env.
- P2: legacy-поблажка `--allow-legacy-taxonomy-hash` зашита в джобу переменной уровня job — это ожидаемо до H4 (re-gate sample на canonical binding). После H4 переменную и оба флага надо убрать, иначе «зелёный CI» снова перестаёт быть полным доказательством.
- P2: release manifest фиксирует **frozen 7D sample** как evidence; при перевыпуске sample в H4 артефакт обязан быть перегенерирован в том же коммите (процедура описана в docs §«Обновление manifest»).
- P2: `artifact_sha256` чувствителен к байтам — политика LF держится только `.gitattributes`; появление новых артефактов вне двух перечисленных путей потребует расширения списка.
- P2: default-входы команды указывают на `apps/catalog/tests/fixtures/` — release-evidence живёт в тестовых фикстурах (так их зафиксировал H2). Перенос в `data/` — вопрос H4/H5, не решался, чтобы не трогать byte-identical фикстуры.

## Full regression suite

**2 failed, 1834 passed, 1 skipped (379.13s)** — только два известных environmental baseline failure
(`tests/test_regression_mvp.py::test_healthcheck_returns_ok` — 503 без Redis;
`tests/test_deploy_release.py::test_release_script_is_executable` — Windows exec bit).
Сигнатура совпадает с pinned baseline; 1806 + 28 новых = 1834 passed, третьего падения нет.

> Первый прогон этой сессии (2:10:14, `1 failed, 500 passed, 1335 errors`) **невалиден**: во время
> него был выключен Docker Desktop и PostgreSQL был недоступен, все errors — отказы соединения с БД.
> После `docker compose up -d db` прогон повторён на живой БД — результат выше.
