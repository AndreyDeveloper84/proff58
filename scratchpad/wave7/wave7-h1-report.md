# Wave 7.1 / Stage H1 — протокол исполнения (canonical taxonomy manifest)

> Работа по утверждённому H1 Plan Amendment (v2). Scope: manifest/schema/loader, seed switch, reconciliation, docs. Без push, без staging-изменений, без изменений extraction semantics, tool_type.v2, corpus, shadow/gate контура.

## Commits

| # | SHA | Parent | Содержание |
|---|---|---|---|
| 1 | `e3e07972f62a7df68d708a72c02ea88428215f1a` | 58ede33 | `data/catalog_processing_rules/tool_type_taxonomy.v1.json` (328 options), `apps/catalog/schemas/tool_type_taxonomy_v1.json`, `apps/catalog/taxonomy_manifest.py`, `apps/catalog/tests/test_taxonomy_manifest.py` (23 теста) |
| 2 | `24d35f762b437840c954de511761458a6a981cc2` | e3e0797 | `load_tool_types` — seed из manifest (fail-closed, no-delete, `--update-display`); runtime guards `enrich_tool_type`/`backfill_option_slugs`; allowlist в модуле; переписанный `test_load_tool_types_slug_guard.py` (9), новый `test_manifest_guards.py` (8) |
| 3 | `06c0fa2da1e52c52b9a45d2ad6ddcb7907f6be6c` | 24d35f7 | `catalog_taxonomy_reconcile` (read-only, blocking/advisory, `--fail-on blocking\|any`), `test_taxonomy_reconcile.py` (10), `docs/catalog/tool-type-taxonomy-manifest.md` |

## Manifest (canonical artifact)

- Путь: `data/catalog_processing_rules/tool_type_taxonomy.v1.json`; schema_version=1, manifest_version=1; 328 options (канонический порядок по slug).
- `taxonomy_identity_hash` = `fc13be7804b06713dccde5cd2888a437a1a7521772d5911acc7d9d93636714d8` (code-point canonical recipe; environment-independent).
- `manifest_semantic_hash` = `91b3ed0c1f7b2bd08c63fe9460b43c20cdf04fa748921465589d1c90b7058b16`.
- Состав: 313 seed + 11 legacy_unknown (PAV-backed) + 4 manual_backport (v2-required); 15 `pending_business_review` (11 legacy + 4 unused); 7 collision-winners с `legacy_aliases` (approved); `semantic_duplicate_allowlist` = [].
- Owner-дополнения: поле `manifest_version` (независимо от schema_version); раздел `future_evolution.immutable_option_identity` (option_uid — путь эволюции, не реализован).

## Проверки

- Manifest validation: duplicate/empty/pattern slug, duplicate value вне allow-list, alias-инварианты, пересчёт обоих hashes — fail-closed (тесты 23/23).
- Seed: clean DB → exact manifest; second run no-op; missing→created; incompatible slug/value → CommandError; value под другим slug → CommandError; sort_order только с `--update-display`; no-delete (тесты 9/9).
- Guards: enrich `_resolve_option` — create only from manifest / `option_not_in_manifest`; backfill — `outside_manifest`/`missing_in_db` счётчики, создание подавлено (тесты 8/8).
- Reconcile: 9 категорий (5 blocking + 4 advisory), `--fail-on blocking|any`, exit codes; `(attribute,value)` unique-constraint делает live-дубликат невозможным — детектор проверен на синтетическом live-снимке (тесты 10/10).
- Catalog suite: **296 passed, 1 skipped**.
- `manage.py check` — 0 issues; `makemigrations --check --dry-run` — no changes; `ruff check apps/catalog/` — clean; `black --check apps/catalog/` — 179 files unchanged.

## Clean-seed без staging

Воспроизводимость проверяется тестами на чистой pytest-Django БД (migrations-only): `test_clean_seed_creates_exact_manifest`, `test_second_run_is_noop` и полный набор seed/guard тестов — staging БД не участвует.

## Legacy hash vs canonical hashes

- Legacy `_taxonomy_hash` (order-sensitive, DB-collation): live staging == pinned `b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b` (проверено 2026-07-23 read-only).
- Canonical `taxonomy_identity_hash` (`fc13be78…`) — отдельный контракт; смешения нет; shadow/gate контур в H1 не затронут.

## Pending (требуют отдельной авторизации)

- Push commits e3e0797/24d35f7/06c0fa2 → CI/deploy.
- Staging: `catalog_taxonomy_reconcile` (read-only) — ожидание blocking drift=0, advisory: unused=4, pending_business_review=15; затем no-op seed `load_tool_types` на staging (по отдельному GO).
- H2 (gate hardening), H3 (default v2 CI replay + release manifest), H4 (re-gate + clean-taxonomy check), H5 (reverse migration hardening).
- Phase 8 — FROZEN до `WAVE 7.1 ACCEPTED`.

## H1.4 — выравнивание контрактных тестов (commit 4)

Первый полный regression (после H1.1–H1.3): 8 failed = 6 контрактных + 2 environmental baseline. Шесть контрактных падений — тесты старого контракта `load_tool_types`/`backfill_option_slugs`, жившие вне `apps/catalog/tests/` (поэтому не попали в первичный catalog-suite прогон):

- `apps/catalog/test_backfill_option_slugs.py` (4): backfill больше не создаёт tool_type options — тесты переведены на generic SELECT-атрибут (`material`), добавлен guard-тест `test_tool_type_values_not_created`.
- `apps/catalog/test_tool_type.py::LoadToolTypesReuseIdentityTests` (1): новый контракт — PK/value сохраняются, `sort_order` НЕ перезаписывается по умолчанию; синхронизация только `--update-display` (ожидание sort_order из manifest).
- `apps/catalog/test_taxonomy_dinamometricheskie_klyuchi.py::LoadToolTypesDeltaTests` (1): delta changeset переписан на manifest («до» = canonical минус option → +1 создана, PK/slug/sort_order существующих без изменений, повтор no-op); мёртвый helper `_manifest_without_new_rule` удалён.

Commit 4: `67efeea983dbd1fdb899a6d9e80521d35c29f927` (parent 06c0fa2), ровно 3 тестовых файла, 99+/51−.

## Full regression suite

- **Финальный: 2 failed, 1781 passed, 1 skipped (432.97s)** — только 2 известных environmental baseline failure (`tests/test_regression_mvp.py::test_healthcheck_returns_ok` — redis недоступен локально; `tests/test_deploy_release.py::test_release_script_is_executable` — Windows exec bit; сигнатуры идентичны pinned v1 baseline, задокументированы в Phase 7D).
- Предыдущий прогон (до H1.4): 8 failed / 1773 passed — 6 контрактных исправлены commit 4.
- Промежуточный: catalog suite 296 passed (H1.1–H1.3), 353 passed после H1.4 (catalog + 3 файла).

## Staging read-only reconciliation (2026-07-23, после CI/deploy 67efeea)

**Контейнерные проверки:** `taxonomy_manifest.py`, `catalog_taxonomy_reconcile.py`, `tool_type_taxonomy.v1.json` — sha256 == локальным закоммиченным файлам (код == commit `67efeea`); команда доступна (`--help`).

**Команда:** `python manage.py catalog_taxonomy_reconcile --format json --fail-on blocking` (read-only, SELECT-only). Exit code **0**, длительность ~7s (включая SSH+startup).

**Результат:**
- live options = 328; manifest options = 328; **identity_equal = True** (live identity == manifest `taxonomy_identity_hash` = `fc13be7804b06713dccde5cd2888a437a1a7521772d5911acc7d9d93636714d8`).
- `manifest_semantic_hash` = `91b3ed0c1f7b2bd08c63fe9460b43c20cdf04fa748921465589d1c90b7058b16` == pin.
- artifact sha256 manifest в контейнере = `e996502f2dde898f359ceb2817da7ba33d98ee36774b656cb1a58a74bb9aa42d` == локальному committed файлу.
- **Blocking drift = 0**: missing_in_live 0, unexpected_in_live 0, slug_value_mismatch 0, used_outside_manifest 0, ruleset_unknown_slug 0.
- **Advisory (ожидаемые):** semantic_duplicate 0; display_metadata_mismatch 0; manifest_unused_option 4 (`hoz-schetchiki`, `metchiki`, `osnastka-rezbonarez`, `plashki`); pending_business_review 15 (11 legacy_unknown + 4 unused; 4 manual_backport — approved).
- Изменений БД не выполнялось (команда read-only по построению; `load_tool_types` и `--update-display` не запускались).

**Evidence:** `scratchpad/wave7/staging-reconcile-report.json` (machine-readable отчёт, sha256 `a891c745508157d9b6ddc7500b9843189ea5a26ca22b10e83eae178090814c26`).

**Статус: STAGING RECONCILIATION PASS.** No-op seed verification — по отдельному GO.

## No-op seed verification на staging (2026-07-23)

**Preflight:** deployed code == `67efeea` (`load_tool_types.py` sha256 `1bd39775…` == локальному); флаги `--path/--manifest/--update-display` (последний НЕ использовался). Write-paths команды: create option (только missing slug → 328/328 present), update value (нет; mismatch → CommandError), update sort_order (только с `--update-display` → не использовался), CategoryAttribute binding `update_or_create` для 13 категорий из rules-файла (no-op UPDATE с идентичными значениями; is_required/group не затрагиваются), удалений/PAV-записей нет.

**Before snapshot** (`staging-seed-before.json`, sha256 `9a97cdb8…`): options=328, PAV=38822, bindings=19, live_identity == manifest_identity == `fc13be78…`.

**Execution:** `python manage.py load_tool_types` — один раз. stdout: `Атрибут tool_type готов (manifest v1, 328 options). created=0, present=328, display_updated=0, display_mismatch=0.` Exit code **0**, длительность ~7s.

**Post-check** (`staging-seed-after.json`): options=328→328; PAV=38822→38822; bindings=19→19; live_identity без изменений; **полный snapshot option id/slug/value/sort_order — идентичен**; **полный snapshot bindings (все поля) — идентичен**.

**Reconcile после seed** (`staging-reconcile-after-seed.json.out`): exit 0; blocking = 0 по всем 5 категориям; advisory без изменений: manifest_unused_option=4, pending_business_review=15, semantic_duplicate=0, display_metadata_mismatch=0; identity_equal=True.

**Статус: STAGING NO-OP SEED VERIFICATION PASS.**
