# Phase 7C — протокол исполнения и Human Decision Log

> Артефакт исполнения по плану `docs/plans/2026-07-22-PHASE7C_RULESET_COVERAGE_EXPANSION_PLAN.md` (v2, AUTHORIZED: Stage 0, Stage 1, Stage 2.1–2.6; обязательный STOP на Stage 2.7).
> Пополняется по ходу фазы. План, ruleset v1, corpus v1, таксономия, matcher не изменяются.

## Human Decision Log

| Decision | Reason | Timestamp (UTC) |
|---|---|---|
| Plan v2 — AUTHORIZED | Authorization scope: Stages 0, 1, and 2.1–2.6 only. Mandatory STOP at Stage 2.7 for per-rule human review. D-1(a) approved exclusively as a temporary Phase 7C research instrument. Stages 3–6 are not yet authorized | 2026-07-22 (пользователь) |
| Stage 2.7 per-rule review completed | Approved: rules 1–24, 26–27. Rule 25 approved after modification: keyword "пояс для" replaced with "пояс для инструмента". Rules 28 and 29 rejected: 28 moved to taxonomy_gap; 29 rejected as catch-all taxonomy assignment. Authorization scope: Stage 3.1–3.7 only. Mandatory STOP after Stage 3.7. Stages 4–6 remain unauthorized | 2026-07-22 (пользователь) |
| Stage 3.1–3.7 accepted | Validated: 38 rules = 11 v1 verbatim + 27 new; 39 fixtures = 12 v1 verbatim + 27 new; load_ruleset OK; negative fixtures 0 violations; taxonomy validation 0 missing slugs; corpus regression correct=37/54, collisions=0, wrong_slug=0; new_rule_overlap=0; local new_independent estimate=262; three expected same-slug multi-match cases for siz-ochki. Authorization scope: Stage 4.1–4.3 only. Mandatory STOP at Stage 4.4 before commit authorization. Stages 4.5–6 remain unauthorized | 2026-07-22 (пользователь) |

## Stage 0 evidence (2026-07-22, read-only, `transaction_read_only=on`)

- **0.1** Инвариант дублей `(attribute_id, slug)` непустых slug → 0 rows.
- **0.2** id=16 = `steplery-i-zaklepochniki` / tool_type; id=73 = `steplery` / tool_type.
- **0.3** Counters = baseline 7B: PAV=60896; tt_options=328; CatalogChange total=57 / tool_type applied=56; CatalogProcessingRun=4.
- **0.4** Staging `_taxonomy_hash` = `b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b` (328 options) — совпал с pin.
- **0.5** Снимок таксономии записан на staging `/app/logs/phase7c-taxonomy-snapshot.json`, забран локально в `scratchpad/phase7c/phase7c-taxonomy-snapshot.json`; локальный `_taxonomy_hash` == `b357be60…`.
- **0.6** Контейнерные входные артефакты: `tool_type.v1.json` sha256 = `b476199a…`, `applied_corpus_tool_type.v1.json` = `6663a6fe…` — совпали с pins §2.
- **0.7** Code-level post-#584 подтверждён по файлам контейнера (git в контейнере отсутствует, как и в 7B): миграция `0027_reslug_steplery_unique_option_slug.py` присутствует; constraint `uniq_attributeoption_attr_slug_nonempty` найден в `apps/catalog/models.py` (grep=1); `/app/.git` отсутствует.

Drift не обнаружен. STOP-условие Stage 0 не сработало — фаза продолжается.

## Stage 1 evidence

- Скрипт `scratchpad/phase7c/extract_nomatch.py` (D-1(a), временный инструмент) размещён в контейнере `/app/logs/phase7c-extract-nomatch.py`; sha256 local == container (`4682b63c…`).
- Первый запуск упал на `ModuleNotFoundError: config` (скрипт вне `/app`, нет `PYTHONPATH`) — исправлено запуском `docker exec -e PYTHONPATH=/app`; код скрипта не менялся. Повтор: exit 0.
- Результат: `no_match=1530 pool_size=1593` — **точное совпадение с baseline 7B** (F-2 не сработал).
- Dataset: `/app/logs/phase7c-nomatch-pool.json` → локально `scratchpad/phase7c/phase7c-nomatch-pool.json`; sha256 staging == local = `0b5a37223af891b868724f657621cacb606d7a5450905b9fd1c3680d097c0d78`.
- Контроли: `ruleset_id=tool_type.v1`, `ruleset_hash=51b3bbad…` (v1 baseline); `count=1530 == len(rows)`; snapshot tx `REPEATABLE READ READ ONLY` (паттерн `SNAPSHOT_SQL`).

## Stage 2 evidence (2.1–2.6)

- **2.1** Группировка no_match по source_group: 39 групп → `phase7c-nomatch-by-group.md`. Топ: Запчасти Хитачи 508, Хозтовары 182, Электроинструмент 108, Слесарно-столярный 89, Автомобильный 76.
- **2.2** Частотный анализ по 33 группам ≥3 → `phase7c-nomatch-freq.md`; фактические товары по кандидатным кластерам → `phase7c-cluster-rows.md` (38 секций, включая RISK/GAP-контексты для negative fixtures).
- **2.3** Маппинг на slug'и сверен со staging snapshot (328 options). Для спорных маппингов — read-only SELECT'ы текущего наполнения slug'ов (`BEGIN TRANSACTION READ ONLY … ROLLBACK`): `phase7c-slug-usage.txt`, `phase7c-slug-samples.txt`, `phase7c-slug-samples2.txt`, `phase7c-fixture-candidates.txt`. Ключевые факты:
  - `rukoyatki-dlya-instrumenta` = рукоятки РУЧНОГО инструмента (41957–41962) → кластер «рукоятка» (32) отклонён как taxonomy_gap;
  - `vibratory-betona` = только машины → «вал гибкий/вибронаконечник» (11) неоднозначен, не предложен;
  - `payalniki` = паяльники (44399–44401), `payalniki-stancii` де-факто смешан → выбран `payalniki`;
  - прецеденты подтверждены: obor-pena/шампунь (6213), bp-podgotovka-vozduha/влагоотделитель (28319, 29132), bp-kompressory/авто-компрессор (28364), izm-ruletki/геодезийная лента (11458, 11464), siz-ochki/щиток (36300–36304);
  - «пояс монтажника» рассогласован между siz-vysota и sumki-poyasnye (pre-existing) → правило 25 сужено до «подсумок/пояс для»;
  - `zap-korpusa-kryshki` не содержит картеров (0 прецедентов); `prochaya-osnastka` не содержит тарелок (0 прецедентов) → правила 28/29 помечены borderline.
- **2.4** Локальная симуляция реальным engine (`keyword_matches_text`, original_name, token/prefix) → `phase7c-simulation.md`:
  - v1 sanity против 1530 no_match → 0 совпадений;
  - 29 candidate rules → **276 predictions**; взаимный overlap новых правил = **0**; ошибочно сматчившихся negative fixtures = **0**; яя-префиксные (1087, 1064, 1065) не матчатся (by design);
  - substring-оценки скорректированы engine-семантикой: изолента 32→27 (5 яя-вариантов), такелаж 28→27 (333 «Стяжка пружин» корректно исключена двухсловным keyword — precision win), фонарь 13→12, воздуходувка 6→4 (`phase7c-dropped.txt`).
- **2.5** Derivation doc: `docs/catalog/phase7c-ruleset-v2-derivation.md` — 29 карточек правил (все PROPOSED, ни одного APPROVED), списки singleton / неоднозначные / taxonomy_gap / rejected с причинами и evidence.
- **2.6** Yield: 276 всего; 263 без borderline 28/29; 235 только clean без monitoring-флагов. Коридор 120–150 new_independent **реалистичен с запасом ~2×**; доказательство исчерпания кластеров не требуется. Все predictions независимы от v1 (no_match pool), взаимный overlap = 0.

**STOP 2.7**: исполнение остановлено. Review package передан пользователю. Stage 3+ не начинался; `tool_type.v2.json` не собирался; таксономия, matcher, ruleset v1, corpus не изменялись; коммитов не было.

## Stage 3 evidence (3.1–3.7, локально, draft note)

- **3.1** Собран `data/catalog_processing_rules/tool_type.v2.json` (`build_v2.py`): `"version": 1`, `"ruleset_id": "tool_type.v2"`, `"note": "draft, Phase 7C"`; 38 rules = v1 (11) verbatim + 27 APPROVED-правил (№25 с keyword «подсумок, пояс для инструмента»); 39 fixtures = v1 (12) verbatim + 27 новых (fixtures на 23255/28677 — новые записи, v1 fixtures не тронуты). Формат: CRLF, indent=2, sort_keys — как v1. Verbatim-контроль v1-части: parsed deep-equality, diff = ∅.
- **3.2** `load_ruleset`: OK (schema + семантика), ruleset_hash (draft) = `14aab84be66eb598ce478d80233b6bc315efd3f325be9a4ce6fbb02e09222dd2` — **НЕ pin** (изменится после финализации note в Stage 4).
- **3.3** `check_negative_fixtures` = [] (0 violations).
- **3.4** `validate_against_taxonomy` против snapshot (328 options, `b357be60…`) = [] (0 missing slugs).
- **3.5** Corpus regression (`replay_v2_vs_corpus.py`): **correct=37/54** (baseline v1 = 32; рост +5 за счёт новых правил — зафиксирован, `expected_recall=0.59` не пересматривался), **collisions=0**, **wrong_slug=0**. Same-slug multi-match: 3 items (36300, 36302, 36304 → [tt-siz-ochki-shitok, tt-siz-ochki-zashchitnye], slug siz-ochki) — ожидаемо по правилу 21, зафиксировано.
- **3.6** Rules-ветка тестов: **93 passed, 1 skipped** (6 файлов: test_rules_engine, test_rules_corpus, test_rules_corpus_replay, test_rules_gate_validate, test_rules_shadow_command, test_rules_snapshot).
- **3.7** Overlap dry-run на dataset (`dryrun_v2_overlap.py`): **predicted=262, new_rule_overlap=0**, exit 0. Фактический №25 после сужения: **3 predictions** (было 4; 36709 «Пояс для подсумка» более не матчится — зафиксирован фактический результат, правило не подгонялось). Раскладка per-rule: `phase7c-stage3-dryrun.txt`. new_independent (локальная оценка) = 262 = 276 − 7 (rule 28) − 6 (rule 29) − 1 (сужение rule 25).
- Derivation doc актуализирован: финальные статусы 29 правил, №25 (MODIFIED), №24 (текст fixture), 28/29 → rejected/taxonomy_gap, определение monitoring (review/documentation, не runtime tier), итоговый yield 262, Stage 3 summary.

**STOP после Stage 3.7**: финализация note, pinning, commit, копирование на staging, Stage 5/6, официальный gate — НЕ выполнялись и НЕ авторизованы. Отчёт передан пользователю.

## Stage 4 evidence (4.1–4.3, freeze)

- **4.1** note финализирован в `tool_type.v2.json`: `"approved 2026-07-22, Phase 7C Stage 2.7 per-rule review (27/29 rules accepted, incl. 1 modified); base tool_type.v1 + 27 new rules"` (фактический review: рассмотрено 29, вошло 27, одно — после модификации, два отклонены; НЕ «27/27»).
- **4.2** Pinning ПОСЛЕ финализации note (`phase7c-stage4-validate.txt`, `phase7c-stage4-hashes.txt`):
  - FINAL canonical ruleset_hash = `9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330`;
  - FINAL LF byte sha256 = `ff449701939e993e6bf3e0d68de20d07a672884a54df602c7b2807316f8728ec`;
  - working-copy (CRLF) sha256 = `5c12db44bc73813ec27f980b1ac593411adb0960358950e7830d0901cf590f66` (platform-specific, справочно).
- **4.3** Повторные проверки после финализации note — все зелёные: `load_ruleset` OK (rules=38, fixtures=39, ruleset_id=tool_type.v2, version=1); `check_negative_fixtures` = 0; `validate_against_taxonomy` = 0 missing; v1-часть parsed deep-equality: rules=True, fixtures=True. Pin table внесена в derivation doc; протокол актуализирован.
- Состав к freeze: 38 rules (11 v1 verbatim + 27 new), 39 fixtures (12 v1 verbatim + 27 new), new_independent estimate = 262.
- **progress.md НЕ обновлялся** (вне scope 4.1–4.3; вопрос о его включении в commit вынесен на checkpoint 4.4: файл покрыт `.superpowers/sdd/.gitignore` = `*`, не трекается с Jun 26, `git add` потребует `-f` — расхождение плана §4.5 с действующей repo-политикой).

**STOP 4.4**: commit, `git add`, Stage 4.5–4.7, staging, Stage 5/6, официальный gate — НЕ выполнялись и НЕ авторизованы. Checkpoint-отчёт передан пользователю.

## Stage 4.5–4.7 evidence (commit)

**Human Decision Log (2026-07-22):**
- Verdict: вариант (b) APPROVED — `.superpowers/sdd/progress.md` остаётся local-only; политика репозитория не меняется.
- AUTHORIZED: Stage 4.5–4.7 без расширения scope; обязательный STOP после 4.7.

**4.5 Commit:**
- SHA: `2375d8e4b542f1acea1e6576df98921f2e8d005e` (branch dev)
- Message: `feat(catalog): tool_type.v2 ruleset — coverage expansion (Phase 7C)`
- 3 files changed, 1899 insertions(+)

**4.6 Scope check (`git diff --name-only HEAD^ HEAD`) — ровно 3 файла:**
- `data/catalog_processing_rules/tool_type.v2.json` (1079)
- `docs/catalog/phase7c-ruleset-v2-derivation.md` (378)
- `docs/plans/2026-07-22-PHASE7C_RULESET_COVERAGE_EXPANSION_PLAN.md` (442)

**4.7 Hash verification:**
- Git blob sha256 = `ff449701939e993e6bf3e0d68de20d07a672884a54df602c7b2807316f8728ec` == pinned LF hash ✓
- Working-copy LF sha256 после commit = `ff449701…` — содержимое не менялось после pinning ✓
- canonical ruleset_hash `9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330` — вычислен из этих же байтов на Stage 4.2; byte-identity подтверждает отсутствие drift ✓

**Repository state:** `git status --short` — 3 файла Phase 7C закоммичены и исчезли из списка; оставшиеся записи — чужие pre-existing (`M docs/catalog/stroitelnyy-roadmap.md` + foreign untracked, включая `scratchpad/`). Working tree clean относительно собственного commit.

**STOP 4.7.** Stage 5 (staging shadow, docker cp, replay) НЕ начат. Ожидается отдельная авторизация.

## Stage 5 evidence (staging shadow v2, read-only)

**Human Decision Log (2026-07-22):** Stage 4.5–4.7 accepted (commit 2375d8e, 3 файла, blob==pinned LF, drift отсутствует). AUTHORIZED: Stage 5.1–5.7; обязательный STOP после 5.7.

**5.1 LF-copy + transfer:**
- local LF sha256 = `ff449701939e993e6bf3e0d68de20d07a672884a54df602c7b2807316f8728ec` == pinned ✓
- container `/app/logs/phase7c-tool_type.v2.json` sha256 = `ff449701…` == local == pinned ✓
- `/app/data/catalog_processing_rules/` не тронут; transit `/tmp` на staging очищен.

**5.2 main run:** exit 0; pool=all size=1593 predictions=325 collisions=0; snapshot_isolation=repeatable_read_read_only.
- report sha256 = `4c1f39d3d9426790eb3afa4a08c6435b457794d92e7443b6022cc2e0a8bc760e`
- gate sample sha256 = `9243ba6f5ef59c8085e2feeab461d1f17e548ecef2d023b6b264fe42aa659441`

**5.3 controls (main report) — ALL OK:**
- ruleset_hash = `9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330` ✓
- taxonomy_hash = `b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b` ✓
- input_universe_hash = `82536a4698688c927f6decd35787d1bb0d3deb8f3c298f698f9bf6387b749db8` ✓
- pool_size=1593; rewrite_attempts=0; collisions=0; corpus_overlap_checked=true (derived: `skip_corpus_overlap_check=false`, corpus задан, exit 0, fail-closed дизайн)
- counts: predictions=325, no_match=1268, excluded_existing_tool_type=18123, regression_tier_hits=0, regression_tier_collisions=0

**5.4 replay (exit 0):** predictions=325, collisions=0.
- gate sample byte sha256 identical: `9243ba6f…` == main ✓; canonical sample hash equal (`a01ca546daf2d396…`)
- normalized full report diff: **EMPTY** (volatile keys + out-paths исключены) ✓
- counts equal, predictions list equal (ordered), per_rule counters (raw/prediction/collision/same_slug_multi) equal по всем 38 правилам ✓
- replay report sha256 = `570649156cd6c83ccc34d4fa310b13d481a58a7b38e2836c761daa6096c2b17e`

**5.5 v1 regression:** 63/63 predictions присутствуют в v2 с тем же slug; missing=none; slug changed=none. **REGRESSION OK.**
- total_v2 unique product_ids = 325; **new_independent = 262** (== локальная оценка Stage 3.7).

**5.6 per-rule + monitoring:** полная таблица 38 правил — `scratchpad/phase7c/phase7c-stage5-analysis.txt`. Monitoring-правила (raw/pred/coll/ssm + ids) зафиксированы там же.
- **same-slug multi-match: 10 predictions** — 36299, 36301, 36303, 36305–36311 → [tt-siz-ochki-shitok, tt-siz-ochki-zashchitnye], slug siz-ochki. Это v1-predictions (zashchitnye — v1-правило), получившие дополнительную same-slug атрибуцию новым правилом 21 — разрешённый случай; slug не изменён, collision нет.
- Расхождения со Stage 3.5 НЕТ: там multi-match 36300/36302/36304 — это **corpus items** (проверено: все три в `applied_corpus_tool_type.v1.json`, 54 items); они typed → исключены из eligible pool (excluded_existing_tool_type=18123) и корректно отсутствуют в shadow predictions. Два набора id не пересекаются по разным причинам, противоречия нет.
- products with >1 distinct slugs (collision-кандидаты): none.

**Performance:** duration main=2.129s, replay=1.756s. Memory snapshot (`docker stats --no-stream`, ~25s после запуска): web=247.6MiB/7.745GiB, db=440.4MiB/7.745GiB — **observed snapshot, не peak** (run ~2s, сэмпл отражает baseline контейнера после завершения).

**5.7 artifacts local + sha256 (staging == local):**
- `phase7c-shadow-report-v2-pool-all.json` = `4c1f39d3…`
- `phase7c-gate-sample-v2-pool-all.json` = `9243ba6f…`
- `phase7c-shadow-report-v2-pool-all-replay.json` = `57064915…`
- `phase7c-gate-sample-v2-pool-all-replay.json` = `9243ba6f…` (== main sample)

**Zero-write:** все staging-операции read-only относительно БД (snapshot isolation repeatable_read_read_only; rewrite_attempts=0); записи только в `/app/logs/` (разрешено); изменений вне `/app/logs/` нет; `/tmp` очищен.

**STOP 5.7.** Stage 6 не начат.

## Stage 6 evidence (coverage verdict + финальная сверка + cleanup)

**Human Decision Log (2026-07-22):** Stage 5.1–5.7 accepted (325 total / 262 new / 63×63 regression / 0 collisions / replay deterministic / zero writes). AUTHORIZED: Stage 6.1–6.3; обязательный STOP 6.3; Phase 7D не авторизована.

**6.1 COVERAGE VERDICT:**
- target corridor: 120–150+ new independent predictions
- actual: **new_independent = 262**, total_v2 = 325, v1 regression 63/63, collisions = 0
- запас над верхней границей: 262 − 150 = **+112**
- **COVERAGE TARGET: PASSED. F-7: NOT TRIGGERED.**
- cross-check со Stage 3.7: локальная оценка 262 == фактический staging 262 (точное совпадение).

**6.2 Финальные pins:**
- commit = `2375d8e4b542f1acea1e6576df98921f2e8d005e` (ровно 3 файла)
- tool_type.v2 LF sha256 = `ff449701939e993e6bf3e0d68de20d07a672884a54df602c7b2807316f8728ec`
- canonical ruleset_hash = `9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330`
- taxonomy_hash = `b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b`
- input_universe_hash = `82536a4698688c927f6decd35787d1bb0d3deb8f3c298f698f9bf6387b749db8`

**Frozen inputs — финальная сверка (drift отсутствует):**
- `tool_type.v1.json` LF sha256 = `b476199afaf83e7f305d335d7ed2c77d855469f59fd73dbfe357c9183d7d1e6e` == pinned ✓
- `applied_corpus_tool_type.v1.json` LF sha256 = `6663a6fe48c2c2656604a179c1f70338a08a9d3e2a364a5ec2f663600b85d6e3` == pinned ✓
- matcher/schema: `matcher_version=1.0`, `pool_filter_version=1.0`, `report_schema_version=1.0` — идентичны 7B и 7C; `code_sha=unknown` в обоих (поле не заполняется, консистентно); tracked code modifications отсутствуют (git status: только чужая pre-existing `M docs/catalog/stroitelnyy-roadmap.md`) ✓
- taxonomy: taxonomy_hash 7B == 7C == pinned ✓
- staging DB counters: pool 7B == pool 7C точно (size=1593, excluded=18123, typed_eligible_universe=18123, rewrite_attempts=0) ✓
- default RULESET_PATH: `rules_engine.py:30` → `tool_type.v1.json`, не изменён ✓

**Replay итог:** main=325 / replay=325 predictions; normalized report diff = empty; gate sample byte-identical = true; per-rule counters identical = true.

**Monitoring handoff → Phase 7D:** правила tt-svar-apparaty-truby, tt-bp-vozdukhoduvki-akkum, tt-obor-mebel-verstak, tt-izm-kolesa-dorozhnoe, tt-yashchiki-sumki-benzopila, tt-siz-pozh-inventar-polotno, tt-siz-izveshchateli-gromkogovoritel + отдельно tt-siz-ochki-shitok (ssm=10). **Constraint для 7D:** принудительно включать monitoring-примеры в human-labelled sample, если случайная выборка их не покрывает (support 3–4 рискуют не попасть в 100 строк).

**Cleanup — зафиксированные SHA-256 удаляемых временных артефактов:**

Локальные (scratchpad/phase7c/):
- `phase7c-shadow-report-v2-pool-all-replay.json` = `570649156cd6c83ccc34d4fa310b13d481a58a7b38e2836c761daa6096c2b17e`
- `phase7c-gate-sample-v2-pool-all-replay.json` = `9243ba6f5ef59c8085e2feeab461d1f17e548ecef2d023b6b264fe42aa659441`
- `tool_type.v2.lf.json` = `ff449701939e993e6bf3e0d68de20d07a672884a54df602c7b2807316f8728ec`
- `extract_nomatch.py` = `4682b63c8bef6114f4b4e73bd7d3e3c6e5561c30ec01115dc58f8e8ce194c83f`
- `replay_v2_vs_corpus.py` = `b008bbfbfa05bc6e1bebb01398fd62ab4518f993c961ef7f3056c2bbb24eda37`
- `dryrun_v2_overlap.py` = `032c9ff0ebf984d06d4c204b95a31ea3328479b298e1dc2b02fc8d0a3f056fd3`
- `simulate_rules.py` = `9bfa1c4f951e60076aa7c341a3d847f540a86d2aa0a2f051ffde66b378035fd9`
- `build_v2.py` = `2569fbc54adab7edbb18df8ebdd6d7eb92309a0861bb694fb65a49b12c4bed78`
- `extract_more_clusters.py` = `cc7f2d2e305907418dfdade01c2f56366e453e8943c75fde388067665e40af86`
- `analyze_stage5.py` = `88ad07d34e8b82ecda2f44166aab0516123ab81b6bf19cf2494bc34a74e08b0f`

Контейнерные `/app/logs/phase7c-*` (8 файлов, hashes сверены с локальными где применимо):
- `phase7c-tool_type.v2.json` = `ff449701…` == pinned; `phase7c-extract-nomatch.py` = `4682b63c…` == local; report/sample main+replay == local; `phase7c-nomatch-pool.json` = `0b5a3722…`; `phase7c-taxonomy-snapshot.json` = `17399a85…` (локальные копии сохранены как deliverables).

**Сохраняемые deliverables:** repo (3 файла в commit 2375d8e) + `scratchpad/phase7c/`: phase7c-report.md, phase7c-nomatch-pool.json, phase7c-taxonomy-snapshot.json, phase7c-shadow-report-v2-pool-all.json, phase7c-gate-sample-v2-pool-all.json, phase7c-stage5-analysis.txt (+ derivation evidence Stage 0–4: cluster-rows.md, nomatch-*.md, simulation.md, slug-*.txt, stage3-*.txt, stage4-*.txt, taxonomy-options.md, dropped.txt, fixture-candidates.txt).

**Статус фазы (proposed):** Phase 7C — COMPLETED. Подтверждены покрытие и техническая стабильность; precision новых правил НЕ подтверждается — предмет Phase 7D.

**STOP 6.3.**

## FINAL VERDICT (2026-07-22)

**PHASE 7C: COMPLETED.** COVERAGE TARGET: PASSED. F-7: NOT TRIGGERED.

Принято без исправлений: commit 2375d8e; 325 total / 262 new independent (+112 над коридором); 63/63 v1 regression; collisions=0; replay детерминирован; pins совпадают; frozen inputs неизменны; staging read-only; cleanup выполнен; Phase 7D не запускалась.

Precision новых правил НЕ подтверждена — предмет Phase 7D (отдельный официальный sample, human labeling, gate). Handoff constraints 7D зафиксированы в Stage 6 evidence: гарантированное представительство monitoring-правил и tt-siz-ochki-shitok в разметке; sample 7C = evidence, не официальный gate sample; 10 same-slug multi-match (siz-ochki) считать одной корректной классификацией, не collision; promotion и смена default ruleset запрещены до verdict 7D.
