# Phase 7D — протокол исполнения и Human Decision Log

> Артефакт исполнения по плану `docs/plans/2026-07-22-PHASE7D_PRECISION_GATE_PLAN.md` (v2, AUTHORIZED: Stage 0, Stage 1; обязательный STOP после Stage 1.5, до любой разметки).
> Пополняется по ходу фазы. Ruleset v2/v1, corpus, taxonomy, matcher, код gate/shadow не изменяются. Commit/push/promotion/записи в БД не авторизованы.

## Human Decision Log

| Decision | Reason | Timestamp (UTC) |
|---|---|---|
| Phase 7D plan v2 — AUTHORIZED | D-1(a) minimal deterministic amendment; D-2 mixed labeling; D-3 seed 20260722 / random core 100; D-4 exceptions only through fully re-pinned v2.1; pool=all explicitly approved. Authorization scope: Stage 0 and Stage 1 only. Mandatory STOP after Stage 1.5, before any labeling. Stages 2–5, commit, push, promotion and database writes remain unauthorized | 2026-07-22 (пользователь) |

## Stage 0 evidence (2026-07-22, freeze pre-checks)

**Локальные pins — все зелёные:**

- v2 LF sha256 = `ff449701939e993e6bf3e0d68de20d07a672884a54df602c7b2807316f8728ec` == pin ✓
- canonical ruleset_hash = `9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330` == pin ✓ (`load_ruleset`: rules=38, ruleset_id=tool_type.v2, version=1)
- v1 LF sha256 = `b476199afaf83e7f305d335d7ed2c77d855469f59fd73dbfe357c9183d7d1e6e` == pin ✓
- corpus LF sha256 = `6663a6fe48c2c2656604a179c1f70338a08a9d3e2a364a5ec2f663600b85d6e3` == pin ✓
- commit `2375d8e4b542f1acea1e6576df98921f2e8d005e` присутствует (`git log`: `2375d8e feat(catalog): tool_type.v2 ruleset — coverage expansion (Phase 7C)`) ✓
- tracked drift: отсутствует в ruleset/corpus/matcher/shadow/gate code; единственная tracked-модификация — чужая pre-existing `M docs/catalog/stroitelnyy-roadmap.md` ✓
- default `RULESET_PATH` (`rules_engine.py:30`) → `tool_type.v1.json`, не изменён ✓

**Staging (read-only):**

- контейнерные входные артефакты: `/app/data/catalog_processing_rules/tool_type.v1.json` = `b476199a…`, `applied_corpus_tool_type.v1.json` = `6663a6fe…` == pins ✓
- staging `_taxonomy_hash` = `b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b` (328 options) == pin ✓ (SELECT-only вызов в контейнере)
- DB counters через psql `BEGIN TRANSACTION READ ONLY … ROLLBACK` (`transaction_read_only=on` — evidence): untyped_pool=**1593**, typed_excluded=**18123** == baseline 7B/7C ✓
- drift-контроль каталога: `pav_total=60896`, `tt_options=328` == counters Stage 0 фазы 7C ✓

**Отложенные контроли (by design, как в 7C):**

- `input_universe_hash` = `canonical_hash({pool, untyped_ids, typed_eligible})` — вычисляется shadow-командой; верификация == pin `82536a4698688c927f6decd35787d1bb0d3deb8f3c298f698f9bf6387b749db8` выполняется официальным прогоном Stage 1 (F-2).
- `rewrite_attempts` — runtime-счётчик shadow-команды (не DB-значение); подтверждение == 0 — в Stage 1 (официальный прогон и replay). Во всех прогонах 7C был 0.

Drift не обнаружен. F-1/F-6 не сработали.

## Stage 1 evidence (официальный gate sample)

**1.1 LF-copy + transfer:** local `scratchpad/phase7d/tool_type.v2.lf.json` sha256 = `ff449701…` == pin; container `/app/logs/phase7d-tool_type.v2.json` sha256 = `ff449701…` == pin ✓.

**1.2 Официальный прогон** (`--pool all --sample-size 100 --seed 20260722 --corpus …v1.json`): exit 0; pool=all size=1593 predictions=325 collisions=0; snapshot_isolation=repeatable_read_read_only.
- report sha256 = `a22e1d1ace94f95f2480f68eb4b43f4ae7a355dc984445a6bf3815f6fd12ae9d`
- random100 sample sha256 = `a23e794d6fe15636ff4fe7ff6fb3574e206b5d00f179e6aee7986e47ad0246ab`

**1.3(a) Replay (тот же seed):** exit 0; predictions=325, collisions=0.
- replay report sha256 = `603b1b6f7ca502f3547bf1f35f00e5b9c9e0a3a5042264a41f7a0b066e0eed54`; replay sample sha256 = `a23e794d…` (**байт-идентичен** официальному).
- normalized full report diff: **EMPTY**; sample canonical hash равен (`455f49cfa1536bf0…`); counts equal; predictions ordered equal; per_rule counters (4×38) equal ✓.

**1.3(b) Universe vs 7C (референс `4c1f39d3…`):** counts equal; ordered predictions product_id→slug equal (n=325); per_rule counters equal (38 rules); `ruleset_hash`/`taxonomy_hash`/`input_universe_hash` == pins; `rewrite_attempts=0`; sample audit: `corpus_overlap_checked=true`, `collision_count` строго int 0. [info] sample∩sample7C = 31 id (список в `phase7d-stage1-analysis.txt`).

**1.4 Monitoring coverage random core (8 refs):**
- покрыты random: tt-svar-apparaty-truby (2 solo), tt-obor-mebel-verstak (2 solo), tt-izm-kolesa-dorozhnoe (1 solo), tt-yashchiki-sumki-benzopila (2 solo), tt-siz-ochki-shitok (3, **все multi**, solo=0 — по D-1 не amendment'ится: правило присутствует);
- отсутствовали: tt-bp-vozdukhoduvki-akkum, tt-siz-pozh-inventar-polotno, tt-siz-izveshchateli-gromkogovoritel.

**Amendment (D-1 minimal, greedy по возрастанию product_id; 3 строки, 3 уникальных id, second-row случаев нет):**

| product_id | added_for_rule_refs | option_slug | same_slug_multi | reason |
|---|---|---|---|---|
| 422 | tt-bp-vozdukhoduvki-akkum | bp-vozdukhoduvki | false | rule_ref absent from random core; minimal product_id |
| 29557 | tt-siz-izveshchateli-gromkogovoritel | siz-izveshchateli | false | rule_ref absent from random core; minimal product_id |
| 29733 | tt-siz-pozh-inventar-polotno | siz-pozh-inventar | false | rule_ref absent from random core; minimal product_id |

Mapping fidelity: 100/100 random строк воспроизведены verbatim из report predictions (конструкция == команде); amendment rows verbatim vs report = True.

**Официальный sample** `scratchpad/phase7d/phase7d-gate-sample-official.json` (random 100 + amendment 3 + блок `amendment`): `validate_gate_sample` = **0 violations**; уникальность product_id ✓; corpus overlap = 0; collision_count строго int 0; corpus_overlap_checked=true; все 8 monitoring refs покрыты ✓.

**1.5 Freeze:**
- byte sha256 = `873ee2a19e7dedbc322357f8ff4108690b4e3f6a25889571e13c5f7191bfdeb8`
- canonical_hash = `888980e7209c27026c13f56152330e5264d8da7103345fefb685713f8635a6db`
- состав: random=100 + amendment=3 = **103 уникальные строки**; amendment product_ids = [422, 29557, 29733]; покрытые refs = все 8.

**Zero-write:** все операции read-only относительно БД (snapshot isolation; rewrite_attempts=0); записи только `/app/logs/phase7d-*` (staging) и `scratchpad/phase7d/` (локально). Stage 2 не начинался.

**STOP 1.5.**

### Monitoring table (рекомендация reviewer при STOP 1.5; информационная)

| monitoring rule | support in universe | random hits | amendment hits | final sample hits |
|---|---|---|---|---|
| tt-svar-apparaty-truby | 10 | 2 | 0 | 2 |
| tt-bp-vozdukhoduvki-akkum | 4 | 0 | 1 | 1 |
| tt-obor-mebel-verstak | 4 | 2 | 0 | 2 |
| tt-izm-kolesa-dorozhnoe | 4 | 1 | 0 | 1 |
| tt-yashchiki-sumki-benzopila | 4 | 2 | 0 | 2 |
| tt-siz-pozh-inventar-polotno | 3 | 0 | 1 | 1 |
| tt-siz-izveshchateli-gromkogovoritel | 3 | 0 | 1 | 1 |
| tt-siz-ochki-shitok | 15 | 3 (все multi) | 0 | 3 |

## Stage 2 evidence

**Human Decision Log (2026-07-22):** STAGE 1 ACCEPTED. AUTHORIZED: Stage 2.1–2.3 (analyst pre-labels → reviewer verification → final labels + schema validation только в режиме проверки labels, без расчёта gate). Mandatory STOP после Stage 2.3. Stage 3–5, commit, push, promotion не авторизованы.

**2.1 Analyst pre-labels (выполнено):**
- `phase7d-labels-prelim.json`: 103/103 строки размечены; источники — факты строки, snapshot taxonomy (328 options), derivation doc v2; веб-поиск не использовался.
- Distribution: correct=103, incorrect=0, identity_problem=0, taxonomy_gap=0, unverifiable=0.
- Borderline-флаги analyst: 31104 (потоковый регулятор расхода газа → «Газовые редукторы»); мониторинг-контексты отмечены в rationale (29557, 43696/43699, 36301/36307/36310, 6215, 29035).
- Monitoring-строки (13): 422, 1857, 1858, 10807, 29557, 29733, 31973, 31974, 36301, 36307, 36310, 43696, 43699.
- Spot-check proposal (seed 20260722, 20/90 non-monitoring correct): 315, 326, 366, 677, 6215, 24867, 28894, 29035, 37015, 37271, 37272, 37273, 40678, 43774, 43780, 43787, 44277, 44281, 44319, 44340.
- Reviewer package: `phase7d-labels-review.md` (секции A monitoring / B borderline / C spot-check / D полная разметка).

**Ожидание 2.2:** reviewer verification выполняется пользователем (D-2). Финальный labels (2.3) — после решений reviewer.

**2.2 Reviewer verification (пользователь, 2026-07-22):**
- Проверено: monitoring 13/13; analyst non-correct 0; spot-check 20/20 (набор seed 20260722 принят, новый draw не потребовался); borderline 31104 проверен отдельно.
- Изменения reviewer: **1** — id=31104: `correct` → `unverifiable` с rationale reviewer (недостаточно разрешённых источников для принадлежности к «Газовые редукторы»; внешний поиск запрещён).
- changed rationale only: 0; принято без изменений: 33 (13 monitoring + 20 spot-check; в сводке reviewer указано «32» — арифметическая опечатка, по явным формулировкам приняты все 13+20=33).
- reviewer_id = `andrey`.

**2.3 Final labels:**
- `phase7d-labels.json`: 103 labels; override 31104 применён; rationale остальных = analyst (приняты reviewer).
- Distribution final: correct=102, incorrect=0, identity_problem=0, taxonomy_gap=0, unverifiable=1.
- byte sha256 = `4cb05d36213d1183c9fe93956471118beb253042b5dd40a3454df9ad143928f1`
- sample_hash = `888980e7209c27026c13f56152330e5264d8da7103345fefb685713f8635a6db` (== canonical_hash(official sample), F-7 не сработал)
- ruleset_hash = `9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330`; matcher_version = `1.0`
- reviewer_id = `andrey`; reviewed_at = `2026-07-22T20:36:13Z`
- Schema/contract validation: `validate_gate_labels` = **0 violations**; sample audit (`corpus_overlap_checked=true`, `collision_count` строго int 0) ✓. Валидация выполнена программным вызовом валидатора — management-команда `catalog_rules_gate_validate` (считает precision/gate_passed) **не запускалась**: Stage 3 не авторизован.

**STOP 2.3.** Stage 3 не начинался.

## Stage 3 evidence

**Human Decision Log (2026-07-22):** STAGE 2 ACCEPTED. AUTHORIZED: Stage 3.1 (официальный gate, фиксация без ручного пересчёта), Stage 3.2 (статистика, временный скрипт только в `scratchpad/phase7d/`), Stage 3.3 (протокол). Mandatory STOP после Stage 3.3. Stage 4 (PROMOTE / PROMOTE WITH EXCEPTIONS / HOLD / REJECT) не авторизована — выбор verdict только за пользователем. Изменение ruleset, v2.1, RULESET_PATH, commit, PR, git push, promotion, deploy, применение predictions, записи в БД запрещены.

**3.1 Официальный gate (локально, 2026-07-23):**

Команда:
```
PYTHONPATH=. PYTHONIOENCODING=utf-8 DJANGO_SETTINGS_MODULE=config.settings.dev \
  ./.venv/Scripts/python.exe manage.py catalog_rules_gate_validate \
  --gate-sample scratchpad/phase7d/phase7d-gate-sample-official.json \
  --labels scratchpad/phase7d/phase7d-labels.json
```

- exit code = **0**
- полный stdout сохранён: `scratchpad/phase7d/phase7d-gate-output.txt`, byte sha256 = `33c0197fa3f4340d3087ba97f090f6a5cd8f17c880d3fe39d4ca427f1234e56d`
- machine output (verbatim):
```
rows=103 decisions: correct=102 identity_problem=0 incorrect=0 taxonomy_gap=0 unverifiable=1
observed_precision=0.9903 (correct=102 / rows=103)
gate_passed=true (precision>=0.99 and rows>=100 and collision_count==0 and corpus_overlap_checked)
```
- observed precision (unrounded) = 102/103 = **0.9902912621359223**
- PRECISION_GATE=0.99; MIN_ROWS_GATE=100; collision_count=0; corpus_overlap_checked=true
- **gate_passed = true** (machine output; ручной пересчёт/округление не выполнялись)

**3.2 Статистика:**

- временный скрипт `scratchpad/phase7d/stats_stage3.py` → `scratchpad/phase7d/phase7d-per-rule-stats.txt` (byte sha256 = `e44266bd5899606e68c6a35bf0a4fed07cf7cd0f13eb0940a93cb1c8457644dc`); метод — Wilson score interval, z=1.96.
- **Overall precision = 0.9902912621359223; Wilson 95% CI = [0.947042, 0.998284]** (основной KPI).
- Decision distribution: correct=102, unverifiable=1, остальные 0.
- Per-rule: 38 правил, полная таблица в `phase7d-per-rule-stats.txt`; единственное правило с non-correct — `tt-svar-reduktory-regulyator` (sup=1, correct=0, precision=0.000000 [0.0000, 0.7935]) — строка 31104.
- Monitoring-группа: aggregate sup=13, correct=13, precision=1.000000, Wilson95=[0.7719, 1.0000]; каждое из 8 monitoring-правил correct=sup (включая tt-siz-ochki-shitok 3/3, все multi).
- Support buckets (attribution-based): 1–4 → 28 rules, 57 attributions, 56 correct, 0.982456 [0.9071, 0.9969]; 5–9 → 3 rules, 25/25, 1.000000 [0.8668, 1.0000]; 10+ → 2 rules, 24/24, 1.000000 [0.8620, 1.0000].
- Zero-support rules (нет строк в sample, 5): tt-bp-trimmery-akkum, tt-izm-ruletki-mernaya-lenta, tt-krep-shplinty-nabor, tt-nabory-instrumenta-dielektr, tt-sumki-poyasnye-podsumok.
- Разбор 31104: slug=svar-reduktory, refs=[tt-svar-reduktory-regulyator]; «Регулятор расхода газа А-90-5 азотный 90л/мин 1,0М», sg=Сварочное оборудование, art=ПТК-А905; decision=unverifiable (reviewer override; analyst был correct); rationale reviewer записан verbatim в labels; влияние — единственная не-correct строка, gate пройден ровно на границе допуска (1 не-correct из 103).
- Denominator semantics: same-slug multi строки (36301, 36307, 36310) = одна классификация на строку; overall denominator=103; per-rule attribution учитывает строку у каждого связанного rule_ref (attributions total=106 = 103 + 3 extra).
- Обязательное предупреждение зафиксировано: per-rule CI при малом n (support 1–4) очень широки и НЕ доказывают rule-level precision ≥ 0.99; это observational evidence, а не статистическое подтверждение правил.

**Zero-write:** Stage 3 полностью локальный; staging не использовался; записей в БД не выполнялось (gate команда работает с файлами sample/labels); артефакты только в `scratchpad/phase7d/`. Ruleset, matcher, taxonomy, corpus, default `RULESET_PATH` не изменялись.

**STOP 3.3.** Stage 4 не начиналась; verdict (PROMOTE / PROMOTE WITH EXCEPTIONS / HOLD / REJECT) не выбирался.

## Stage 4 — Human Decision

**Human Decision Log:**

- **Decision: PROMOTE**
- Decision owner: Product Owner
- Decision date: 2026-07-23

**Reason:**
The official Phase 7D precision gate passed:
102 correct out of 103 rows,
observed precision 0.9902912621359223,
rows >= 100,
collision_count = 0,
corpus_overlap_checked = true.

The only non-correct row was classified as unverifiable rather than
incorrect. It does not constitute sufficient evidence to exclude the
associated legacy v1 rule or create ruleset v2.1.

**Known limitations:**
overall Wilson 95% CI [0.947042, 0.998284];
five rules had zero sample support;
small-support per-rule estimates are observational only;
monitoring aggregate 13/13 с широким Wilson interval;
результат на границе gate: ещё одна non-correct строка (101/103 ≈ 0.9806) провалила бы gate.

**Почему не PROMOTE WITH EXCEPTIONS (D-4 не применяется):** строка 31104 (`tt-svar-reduktory-regulyator`) получила decision=unverifiable — разрешённых источников не хватило для независимого подтверждения, а не доказана ошибочность классификации. Правило относится к ранее существовавшему контуру v1; удаление его в v2.1 по одной unverifiable строке непропорционально и могло бы создать поведенческое расхождение с current default v1 без доказанного дефекта.

**Ограничения verdict:** PROMOTE означает, что ruleset v2 прошёл утверждённый Phase 7D gate и может перейти к отдельно контролируемой процедуре promotion. PROMOTE **не** означает, что статистически доказана истинная precision ≥0.99 для всей генеральной совокупности или для каждого правила. Требуются аккуратный rollout и post-promotion monitoring.

**Authorization (2026-07-23, пользователь):** разрешено только — зафиксировать verdict PROMOTE в Human Decision Log; подготовить детальный план Stage 5 (обязательно: rollback, staging smoke, post-promotion monitoring). **Не авторизовано:** изменение RULESET_PATH, изменение ruleset, создание v2.1, commit, PR, git push, deploy, применение predictions, записи в БД.

**STOP.** Stage 5 требует нового плана и отдельной авторизации.

## Stage 5.0 + Stage A + F-5.2 event (2026-07-23)

**Human Decision Log (2026-07-23, Product Owner):** VERDICT option (a) — Stage A may proceed with documented environmental exceptions. F-5.2 уточнено: срабатывает при любом **новом** failure или изменении failure signature относительно pinned v1 baseline. Baseline exceptions (waived только для локального Stage A, только при идентичном воспроизведении на v1): (1) `tests/test_regression_mvp.py::test_healthcheck_returns_ok` — Redis недоступен локально; (2) `tests/test_deploy_release.py::test_release_script_is_executable` — Windows checkout не материализует POSIX exec bit (git index 100755; авторитетная проверка — Linux CI). Зелёный CI на Linux перед staging deploy обязателен. **Не авторизовано:** Stage B, git add, commit, push, CI/deploy, cleanup, изменения ruleset JSON, синхронизация локальной БД, изменение/skip-маркировка двух baseline-тестов.

**5.0 Freeze re-verification (до правки) — все pins зелёные:**
- HEAD = `2375d8e4b542f1acea1e6576df98921f2e8d005e` ✓; `git status` — новых tracked-модификаций нет (чужая pre-existing `M docs/catalog/stroitelnyy-roadmap.md`).
- v2 LF sha256 = `ff449701…` ✓; canonical ruleset_hash = `9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330` ✓ (ruleset_id=tool_type.v2, 38 rules); v1 LF = `b476199a…` ✓; corpus LF = `6663a6fe…` ✓.
- sample byte = `873ee2a1…` ✓; labels byte = `4cb05d36…` ✓.

**A.1 + первый полный pytest и F-5.2 event:**
- Применён однострочный diff `tool_type.v1.json → tool_type.v2.json` (`rules_engine.py:30`); diff = 1 file / 1 insertion / 1 deletion.
- Первый прогон полного pytest (`--reuse-db`): таймаут 30 мин на ~29%, сплошные `E` с первого теста. Root cause: **протухшая reused тестовая БД** — `django.db.utils.ProgrammingError: column reviews_review.subject_type does not exist` на этапе `create_test_db → serialize_db_to_string`; каждый DB-тест ошибся в setup. Environment-дрейф scratch-БД, не связан с правкой.
- Пересоздана **только тестовая** БД (`--create-db`; dev/staging-данные не затрагивались). Повторный полный pytest **с применённой правкой**: **2 failed, 1734 passed, 1 skipped, 509.20s**.
- Точные failures: (1) `tests/test_regression_mvp.py::test_healthcheck_returns_ok` — `assert 503 == 200` (redis:6379 недоступен локально); (2) `tests/test_deploy_release.py::test_release_script_is_executable` — нет exec-бита у `docker/release.sh` в Windows-чаекауте.
- По исходному контракту F-5.2 выполнен **немедленный revert** (`git checkout -- apps/catalog/rules_engine.py`), дерево возвращено в pinned-состояние.
- **Baseline reproduction evidence:** оба теста идентично падают на pinned v1 (`2 failed in 5.83s`, те же сигнатуры: `assert 503 == 200`, exec-bit assertion). Регрессия от правки не установлена; локальный full-green недостижим в принципе (нет Redis, NTFS exec bit) при любом состоянии кода.
- Product Owner принял environmental baseline exceptions (см. HDL выше) и уточнил F-5.2.

**Повторное применение и уточнённый Stage A (после verdict):**
- Однострочный diff применён повторно; `git diff --stat` = **1 file changed, 1 insertion(+), 1 deletion(-)**; blob-diff идентичен первому применению (`ecae863..5458c30`).
- Профильный regression-набор (rules contour): `test_rules_engine.py` + `test_rules_corpus.py` + `test_rules_corpus_replay.py` + `test_rules_shadow_command.py` + `test_rules_gate_validate.py` + `test_rules_snapshot.py` → **93 passed, 1 skipped in 8.64s** (skip pre-existing). Полный pytest повторно не выполнялся — уже выполнен с правкой (выше), baseline двух failures подтверждён на v1.
- **Partial local default-path smoke:** `load_ruleset(None)` (тот же код-путь, что `catalog_rules_shadow.py:226`) → `ruleset_id=tool_type.v2`, `ruleset_hash=9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330`, 38 rules.
- **Local full shadow: NOT EXECUTABLE** — pre-existing local taxonomy drift: локальная dev-БД имеет 299 tool_type options (staging: 328); `validate_against_taxonomy` падает на 7 slug (`bp-podgotovka-vozduha`, `dinamometricheskie-klyuchi`, `kobury-dlya-instrumenta`, `krep-shplinty`, `puskovye-provoda`, `sterzhni-kleevye`, `sumki-poyasnye`); v1 локально тоже не проходит (3 slug) — отставание предшествует promotion. Promotion-caused regression: not established. Синхронизация локальной БД не выполнялась (zero-write scope).
- **Authoritative full smoke: deferred to Stage C staging** (default-ruleset shadow на staging, где taxonomy 328 options покрывает все 35 slug v2 — доказано официальным прогоном Stage 1: exit 0, predictions=325, collisions=0).

**Zero-write:** записей в БД не выполнялось (пересоздание касалось только scratch test-БД `test_*`); записи файлов только в `scratchpad/phase7d/`; tracked-изменения — ровно одна строка `rules_engine.py`; JSON ruleset/corpus байт-неизменны.

**STOP A.** Stage B (commit), Stage C (push/CI deploy), cleanup, production не авторизованы.

## Stage B — promotion commit (2026-07-23)

**Human Decision Log (2026-07-23, Product Owner):** STOP A принят. AUTHORIZED: Stage B only. Mandatory STOP сразу после создания и проверки commit. Push, Stage C, CI/deploy, rollback, cleanup, production, predictions, записи в БД — не авторизованы.

**B.0 (F-5.6) pre-commit guard — PASSED:** staged scope до commit — `git diff --cached --stat` = **1 file changed, 1 insertion(+), 1 deletion(-)**; staged diff — ровно одна строка `RULESET_PATH` v1→v2; `stroitelnyy-roadmap.md`, план, scratchpad, JSON в staged area отсутствуют.

**B.1–B.3 Commit:**

- commit = `58ede33f9105daa40a8b530204335b65e468e7a5`
- parent = `2375d8e4b542f1acea1e6576df98921f2e8d005e` ✓ (pinned HEAD 7C)
- message = `feat(catalog): promote tool_type.v2 to default ruleset (Phase 7D Stage 5)`
- scope: ровно 1 файл (`apps/catalog/rules_engine.py`), 1 insertion(+), 1 deletion(-); author/committer = AndreyDeveloper84, CommitDate 2026-07-23 06:49:38 +0300.

**Acceptance criteria Stage B — все выполнены:** один файл; одна заменённая строка; `tool_type.v1.json → tool_type.v2.json`; нет изменений JSON/тестов/документации/scratchpad в commit; parent == 2375d8e; чужая `M docs/catalog/stroitelnyy-roadmap.md` осталась в working tree и в commit не попала.

**Post-commit проверки:**
- `git status --short` (tracked): только чужая pre-existing `M docs/catalog/stroitelnyy-roadmap.md`.
- JSON byte hashes не изменились (== значениям до commit): v2 byte `5c12db44bc73813ec27f980b1ac593411adb0960358950e7830d0901cf590f66`; v1 byte `93d145e479dfc2c528e849d09bbfc69640f2ca6672766b69f6c7c68cee4b7b8b`; corpus byte `32511e850f732c7419cf6c7164d4a41da7de566ecb3929f15f34baf73aba035e`. LF pins подтверждены: v2 `ff449701…`, v1 `b476199a…`, corpus `6663a6fe…`.
- **Push не выполнялся.** Ветка `dev` опережает origin на 1 commit; CI/deploy не запускался.

**STOP B.** Stage C (push → CI auto-deploy staging → post-deploy smoke) не авторизован.

## Stage C — push → CI auto-deploy → staging smoke (2026-07-23)

**Human Decision Log (2026-07-23, Product Owner):** STOP B принят. D-5.1 подтверждён (авторизация Stage C = push + автоматический CI deploy + staging deployment + post-deploy smoke). D-5.4 подтверждён (при любом нарушении инвариантов F-5.4 — немедленный `git revert` + push + CI deploy + incident evidence, разбор после восстановления). AUTHORIZED: Stage C полностью. Mandatory STOP после полного post-deploy staging smoke. **Не авторизовано:** Stage D, cleanup, дополнительные commits, push в main, production deploy, применение predictions, записи в рабочую БД.

**C.1 Push:** `git push origin dev` → `dbdc5eb..58ede33 dev -> dev`; доставлено ровно 2 commit (`2375d8e` 7C + `58ede33` promotion); remote notice о bypassed branch rules (PR-only + 2 required checks) — push прошёл с правами владельца.

**CI (run 29978195551):** conclusion=**success**; headSha=`58ede33f9105daa40a8b530204335b65e468e7a5`; jobs: tests/test ✓, tests/lint ✓, tests/frontend ✓, deploy ✓; created 03:54:51Z → updated 04:01:28Z (~6m37s; deploy job 3m5s). Annotations: только Node.js 20 deprecation notices.

**Deploy verification:** контейнерная строка 30 `/app/apps/catalog/rules_engine.py` = `…"tool_type.v2.json"` (promotion задеплоен); контейнерные файлы: `tool_type.v2.json` sha256=`ff449701…` == pin, `tool_type.v1.json` = `b476199a…` == pin (Linux-чаекаут материализует LF). origin/dev = `58ede33f…` == local HEAD.

**C.2 Authoritative staging smoke (default ruleset, БЕЗ --ruleset):**
```
docker exec proff58_staging-web-1 python manage.py catalog_rules_shadow \
  --pool all --out /app/logs/phase7d-stage5-smoke-default.json
```
exit 0; snapshot_isolation=repeatable_read_read_only; artifact sha256 (container) = `6f3ab9b7e595e9f66252966007d643f72bc8f610e1c4a240de10c71fa71ee435`; локальная копия `scratchpad/phase7d/phase7d-stage5-smoke-default.json` byte-identical (тот же sha256).

**C.3 Frozen comparison (comparator `compare_stage5_smoke.py`, 16/16 PASS):**
- ruleset_id=tool_type.v2; ruleset_hash=`9bf0271a…` == pin; taxonomy_hash=`b357be60…` == pin; input_universe_hash=`82536a46…` == pin; matcher_version=1.0.
- predictions=**325**; counts.collisions=**0**; top-level collisions=[]; rewrite_attempts=**0**; pool.size=**1593**; excluded_existing_tool_type=**18123**; typed_eligible_universe=**18123**.
- **ordered predictions identical** к frozen reference `a22e1d1a…` (n=325, product_id→option_slug→rule_refs по порядку); **per-rule counters identical** (38 правил × raw/prediction/collision/same_slug_multi).
- **31104 unchanged**: slug=`svar-reduktory`, refs=[`tt-svar-reduktory-regulyator`], facts_hash == reference — автоматических изменений monitoring-case нет.

**F-5.4 не сработал. Rollback NOT executed.**

**Zero-write:** записей в рабочую БД не выполнялось (smoke — read-only snapshot); записи только `/app/logs/phase7d-stage5-*` (staging) и `scratchpad/phase7d/` (локально). `git status --short` после Stage C: только чужая pre-existing `M docs/catalog/stroitelnyy-roadmap.md`.

**STOP C.** Stage D (monitoring activation + финальный протокол + cleanup по D-5.3) не авторизован.

## Stage D — финальное закрытие (2026-07-23)

**Human Decision Log (2026-07-23, Product Owner):** STAGE C ACCEPTED. AUTHORIZED: Stage D only (финальный протокол, регистрация monitoring cases, cleanup по D-5.3 после фиксации SHA-256). **Не авторизовано:** новые commits, дополнительные push, push в main, production deploy, применение 325 predictions, изменение товара 31104, создание v2.1, изменение ruleset JSON, запуск +7/+30 replay раньше дат, любые записи в рабочую каталожную БД.

### D.1 Финальный протокол promotion

- promotion commit = `58ede33f9105daa40a8b530204335b65e468e7a5` (parent `2375d8e4…`);
- GitHub Actions run `29978195551` = success (tests/test, tests/lint, tests/frontend, deploy — все ✓; ~6m37s);
- staging smoke (default ruleset, без `--ruleset`): exit 0; ruleset_id=tool_type.v2; ruleset_hash=`9bf0271a…`; predictions=325; collisions=0; rewrite_attempts=0; pool=1593; excluded=18123; taxonomy_hash=`b357be60…`; input_universe_hash=`82536a46…`;
- frozen comparison vs `a22e1d1a…`: **16/16 PASS**; ordered diff = EMPTY; per-rule counters identical (38×4);
- Rollback NOT executed (F-5.4 не сработал);
- zero-write: записей в рабочую БД не выполнялось ни на одной стадии.

**Итоговый статус promotion (принципиальное различие):**

> **ruleset v2 promoted to default shadow/gate ruleset on staging.**

> **predictions were not applied to catalog data.**

Это разные события: изменён только default `RULESET_PATH` для команд `catalog_rules_shadow` / `catalog_rules_gate_validate`. Ни один товар, ни одно `ProductAttributeValue`, ни одна категория не изменены; применение predictions не выполнялось и остаётся неавторизованным; production (main) не затронут.

### D.2 Monitoring cases (зарегистрированы)

- **M-1 (product_id=31104).** Текущий результат: `svar-reduktory`; rule_ref `tt-svar-reduktory-regulyator`; human decision = `unverifiable`. **Автоматическое изменение запрещено.** Пересмотр только: при изменении facts товара; при следующем human precision audit; при появлении разрешённого независимого evidence. Строка не является доказанной ошибкой и не требует немедленного v2.1.
- **M-2 (пять zero-support rules):** `tt-bp-trimmery-akkum`, `tt-izm-ruletki-mernaya-lenta`, `tt-krep-shplinty-nabor`, `tt-nabory-instrumenta-dielektr`, `tt-sumki-poyasnye-podsumok`. Статус: **promoted but unmeasured at rule level** (НЕ «подтверждены», НЕ «precision 100%»). В следующем human-labeled audit — принудительное представительство через deterministic amendment (D-1-style).
- **M-3 (drift replay).** Cadence от фактической даты deployment Stage C (**2026-07-23**, CI run updated 04:01:28Z): **+7 days = 2026-07-30**; **+30 days = 2026-08-22**. Сейчас replay-прогоны НЕ выполняются. Scope каждого: read-only staging shadow с default ruleset; сравнение counts, ordered predictions, rule refs, per-rule counters, taxonomy_hash, input_universe_hash против frozen reference `a22e1d1a…`. Drift = доклад и отдельное решение; **автоматического rollback по M-3 нет**. Инструмент: `scratchpad/phase7d/compare_stage5_smoke.py` (сохранён специально под M-3).
- **M-4 (gate boundary).** Promotion принят на границе: **102/103 correct** (ещё одна non-correct → gate был бы провален: 101/103 ≈ 0.9806). Любой будущий audit v2 — не менее 100 строк с обязательным monitoring-представительством.

### D.3 Cleanup (по D-5.3; SHA-256 зафиксированы ДО удаления)

**Удаляется со staging (`/app/logs/`):**

| файл | sha256 |
|---|---|
| phase7d-tool_type.v2.json | `ff449701939e993e6bf3e0d68de20d07a672884a54df602c7b2807316f8728ec` |
| phase7d-shadow-report-v2-official.json | `a22e1d1ace94f95f2480f68eb4b43f4ae7a355dc984445a6bf3815f6fd12ae9d` |
| phase7d-shadow-report-v2-official-replay.json | `603b1b6f7ca502f3547bf1f35f00e5b9c9e0a3a5042264a41f7a0b066e0eed54` |
| phase7d-gate-sample-random100.json | `a23e794d6fe15636ff4fe7ff6fb3574e206b5d00f179e6aee7986e47ad0246ab` |
| phase7d-gate-sample-random100-replay.json | `a23e794d6fe15636ff4fe7ff6fb3574e206b5d00f179e6aee7986e47ad0246ab` |
| phase7d-stage5-smoke-default.json | `6f3ab9b7e595e9f66252966007d643f72bc8f610e1c4a240de10c71fa71ee435` |

(hash smoke и его локальная byte-identical копия зафиксированы — условие удаления выполнено.)

**Удаляется локально (`scratchpad/phase7d/`):**

| файл | sha256 |
|---|---|
| analyze_stage1.py | `1a8fabebb67a409c499472efeb0a387a71c06b76b6001fced6d332d2df4cd632` |
| build_prelim_labels.py | `27361cbfc684e51e07aca0316b99ce1c9cad638459f58910e7b5eb091bcd2d3f` |
| gen_review_doc.py | `a872e442d6da3fcccffd33b322ebc49bef3224af2575f089b475d731a9eb08e9` |
| build_final_labels.py | `07f5d5276ed6369cc6fc50beb989cc7ddb40026284b7e1f364795a465c57a383` |
| stats_stage3.py | `6acb84d81f40fa2c758398a0825f21466a27185c63838010eff0321ff27fb826` |
| tool_type.v2.lf.json | `ff449701939e993e6bf3e0d68de20d07a672884a54df602c7b2807316f8728ec` |
| phase7d-gate-sample-random100-replay.json | `a23e794d6fe15636ff4fe7ff6fb3574e206b5d00f179e6aee7986e47ad0246ab` |
| phase7d-shadow-report-v2-official-replay.json | `603b1b6f7ca502f3547bf1f35f00e5b9c9e0a3a5042264a41f7a0b066e0eed54` |

**Сохраняется (canonical evidence):**

| файл | sha256 / назначение |
|---|---|
| phase7d-report.md | протокол + Human Decision Log (этот файл) |
| phase7d-gate-sample-official.json | `873ee2a1…` — frozen official sample (103) |
| phase7d-labels.json | `4cb05d36…` — final labels (102 correct / 1 unverifiable) |
| phase7d-gate-output.txt | `33c0197f…` — официальный machine output gate |
| phase7d-shadow-report-v2-official.json | `a22e1d1a…` — frozen reference для M-3 replay |
| phase7d-stage5-smoke-default.json | `6f3ab9b7…` — Stage 5 staging smoke (byte-identical удалённой контейнерной копии) |
| phase7d-per-rule-stats.txt | `e44266bd…` — итоговая per-rule статистика с CI |
| phase7d-gate-sample-random100.json | `a23e794d…` — deliverable плана 7D |
| phase7d-labels-prelim.json | `4dda01f4…` — analyst pre-labels (deliverable плана 7D) |
| phase7d-labels-review.md, phase7d-labeling-worksheet.txt, phase7d-stage1-analysis.txt, phase7d-stage2-prelim-summary.txt, phase7d-stage2-final-summary.txt | процессное evidence разметки/анализа |
| compare_stage5_smoke.py | `86c269fa…` — comparator инвариантов F-5.4; сохранён как инструмент M-3 drift replay |
| docs/plans/2026-07-23-PHASE7D_STAGE5_PROMOTION_PLAN.md | promotion plan (v2, с D-решениями) |

Cleanup не затрагивает tracked project files, ruleset JSON, corpus, тесты, документацию вне Phase 7D scratch-артефактов.

### D.4 Итоговый статус

Предлагаемый verdict: **PHASE 7D COMPLETED** с обязательными оговорками:

- v2 стал default **только** для shadow/gate-контура (staging + код в dev);
- predictions **не применены** к товарам;
- production promotion (main) **не выполнялся**;
- пять правил остаются **unmeasured** (M-2);
- product 31104 остаётся **monitoring case** (M-1);
- **+7/+30 drift replay** (2026-07-30 / 2026-08-22) — будущие контрольные действия, сейчас не выполняются.

**Подтверждения на момент Stage D:** новых commit и push после `58ede33` нет (HEAD == origin/dev == `58ede33f…`); записей в рабочую каталожную БД не выполнялось; `git status --short` — только чужая pre-existing `M docs/catalog/stroitelnyy-roadmap.md`.

**STOP D.**

## FINAL VERDICT (2026-07-23, Product Owner)

**PHASE 7D COMPLETED.**

Основания: tool_type.v2 promoted в default shadow/gate ruleset на staging; promotion commit `58ede33f9105daa40a8b530204335b65e468e7a5` прошёл зелёный CI и deploy; authoritative staging smoke — 325 predictions, 0 collisions, 0 rewrite attempts; frozen comparison 16/16 PASS; ordered predictions и per-rule counters не изменились; ruleset/taxonomy/input-universe hashes совпали с pins; predictions не применялись к каталожным данным; рабочая БД не изменялась; rollback не потребовался; cleanup выполнен после фиксации SHA-256; новых commit и push после Stage C нет.

**Зафиксированные ограничения (обязательные):**
- Phase 7D не утверждает статистически доказанную precision ≥ 0.99 для всей генеральной совокупности или для каждого отдельного правила.
- M-1: product 31104 — unverifiable, без автоматического изменения.
- M-2: пять правил — promoted but unmeasured at rule level.
- M-3: read-only drift replay — 2026-07-30 и 2026-08-22 (механизм запуска авторизуется отдельно по D-5.2).
- M-4: следующий audit — минимум 100 строк с обязательным monitoring-представительством.

**Итог:** ruleset v2 promoted to default shadow/gate ruleset on staging; predictions were not applied to catalog data; production promotion was not performed. Дополнительных изменений в рамках Phase 7D не требуется.

## M-3 replay scheduling (2026-07-23)

Механизм M-3 (по D-5.2, авторизован пользователем 2026-07-23): системные one-shot напоминания в сессии kimi CLI.

- **+7 replay:** id `9e2be679` — 2026-07-30 10:23 (+03:00), артефакт `phase7d-m3-replay-plus7.json`.
- **+30 replay:** id `870da7ed` — 2026-08-22 10:23 (+03:00), артефакт `phase7d-m3-replay-plus30.json`.

Формулировка обоих: read-only staging shadow без `--ruleset` → сравнение с frozen reference `a22e1d1a…` через `compare_stage5_smoke.py` → при PASS запись результата в протокол и удаление контейнерного артефакта после фиксации sha256; при drift — **без автоматического rollback**, drift-evidence и доклад пользователю для отдельного решения. Ограничение механизма: напоминания срабатывают только при живой (возобновлённой) сессии; иначе replay выполняется вручную по настоящему протоколу.
