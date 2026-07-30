# Phase 7B — протокол исполнения и Human Decision Log

> Артефакт исполнения по плану `docs/plans/2026-07-22-PHASE7B_SHADOW_GATE_PLAN.md` (v2, AUTHORIZED).
> Пополняется по ходу фазы. План, derivation doc, ruleset и corpus не изменяются.

## Human Decision Log

| Decision | Reason | Timestamp (UTC) |
|---|---|---|
| Phase 7B plan v2 — AUTHORIZED, исполнение до конца Stage 1 включительно | все замечания ревью закрыты | 2026-07-22 (пользователь) |
| F-1 hash mismatch — RESOLVED as false positive | root cause = CRLF/LF representation: Git blob на dev == staging bytes (`b476199a…` ruleset, `6663a6fe…` corpus); различие воспроизводится удалением CR; JSON semantic equality confirmed; `ruleset_hash` (canonical JSON hash) не изменился. LF/Git SHA-256 accepted as authoritative for this phase; старые значения `93d145e4…`/`32511e85…` — Windows/CRLF-specific, не использовать как cross-platform reference | 2026-07-22 (пользователь) |
| F-2 predictions=19 < 100 — STOP после Stage 1.1; replay Stage 1.3 не выполнялся; ожидание решения пользователя (pool=all / расширение ruleset / приёмка без gate) | план, условие F-2: немедленная остановка при predictions < MIN_ROWS_GATE | 2026-07-22 |
| F-2 resolved by owner | Official gate on in-stock impossible because predictions=19 < MIN_ROWS_GATE. Proceeding with pool=all exactly as provided by Phase 7B contingency plan. Ruleset remains frozen. No derivation changes. No taxonomy changes. No matcher changes. Единственный изменённый параметр Stage 1: pool=in-stock → pool=all; остальное (read-only, ruleset, corpus, seed, sample_size=100, overlap-check, replay, gate) без изменений | 2026-07-22 (пользователь) |
| Phase 7B — COMPLETED AS OBSERVATIONAL BASELINE | Official precision gate was not reached: pool=in-stock produced 19 predictions; pool=all produced 63 predictions; MIN_ROWS_GATE=100. Maximum eligible pool was exhausted. No collisions, corpus overlap, nondeterminism, writes, or drift detected. Ruleset remains candidate-tier. No promotion or catalog application authorized. Further progress requires a separately authorized ruleset expansion cycle | 2026-07-22 (пользователь) |

## Stage 0 evidence (2026-07-22, read-only, `transaction_read_only=on`)

- Code-level staging = post-#584: миграция 0027 в контейнере, constraint в `models.py`.
- Инвариант дублей `(attribute_id, slug)` непустых slug → 0 rows.
- id=16 = `steplery-i-zaklepochniki` / tool_type; id=73 = `steplery` / tool_type.
- Индекс `uniq_attributeoption_attr_slug_nonempty` существует.
- Counters: PAV=60896; tt_options=328; applied_tt=56; non_final=0.
- healthz → 200 `{"status":"ok","db":"ok","redis":"ok"}`.
- Пул (по `_eligible_qs` + in-stock): pool_size=**188** (без tool_type), excluded=5683 (с tool_type).
- Контейнерные копии входных артефактов = Git blob на dev (см. F-1 entry).

## Stage 1 evidence (2026-07-22)

### Stage 1.1 — shadow-прогон (staging, `snapshot_isolation=repeatable_read_read_only`, exit 0)

Команда:
`docker exec proff58_staging-web-1 python manage.py catalog_rules_shadow --ruleset /app/data/catalog_processing_rules/tool_type.v1.json --pool in-stock --sample-size 100 --seed 20260721 --out /app/logs/phase7b-shadow-report.json --gate-sample-out /app/logs/phase7b-gate-sample.json --corpus /app/data/catalog_processing_rules/applied_corpus_tool_type.v1.json`

Итоги:

- pool=in-stock size=**188**; excluded_existing_tool_type=5683; rewrite_attempts=0.
- predictions=**19** (share 0.1011); no_match=169; collisions=**0**; regression_tier hits/collisions = 0/0.
- Overlap-check: `corpus_overlap_checked=true`; `collision_count=0`.
- Хэши: ruleset_hash=`51b3bbad7c65565637711e5bf9ee74eb7b477ff71b9e25183095ede9cb1044bd` (= pinned canonical); taxonomy_hash=`b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b`; input_universe_hash=`6c91d37a414c641c2a96917749c1d84304efd2f7a63ebddfe165f7beec6050ea`; content_hash=`7dd090689fcab0b116abfe74a97beaadc0154058109646a41ca5cf7793a6c049`.
- Gate sample: seed=20260721, rows=**19** (все predictions; 19 < 100 → sample = полный набор предсказаний).
- Performance: duration 47.7s; container memory snapshot 229.6MiB / 7.745GiB (мгновенный снимок `docker stats`, не peak).

Per-rule `prediction_hits` (все 11 правил, tier=candidate, collision_hits=0, same_slug_multi_hits=0):

| rule_id | raw_hits | prediction_hits | coverage_share |
|---|---|---|---|
| tt-siz-ochki-zashchitnye | 5 | 5 | 0.0266 |
| tt-adaptery-universal (№6) | 3 | 3 | 0.0160 |
| tt-dinamometricheskie-klyuchi-klyuch | 3 | 3 | 0.0160 |
| tt-hoz-lenty-malyarnaya | 3 | 3 | 0.0160 |
| tt-yashchiki-sumki-keys-prochee | 2 | 2 | 0.0106 |
| tt-bp-pnevmosteplery-gvozde | 1 | 1 | 0.0053 |
| tt-izm-shtativy-derzhatel (№7) | 1 | 1 | 0.0053 |
| tt-krep-shplinty-nabor | 1 | 1 | 0.0053 |
| tt-nabory-instrumenta-dielektr | 0 | 0 | 0 |
| tt-puskovye-provoda-startovye | 0 | 0 | 0 |
| tt-svar-reduktory-regulyator | 0 | 0 | 0 |

Строки правил №6/№7 в gate sample:

- №6 `tt-adaptery-universal` → `adaptery`: product_id 6683 (art. 792-131, «Адаптер для подключения пылесоса резиновый 32/35/38/41мм ПУЛЬСАР»); product_id 1113 (art. 40309-MD, «Адаптер-переходник для инструмента MAKITA с аккум DEWALT»); product_id 1112 (art. 40309-MB, «Адаптер-переходник для инструмента MAKITA с аккум BOSCH»).
- №7 `tt-izm-shtativy-derzhatel` → `izm-shtativy`: product_id 10633 (art. 34706, «Держатель с микролифтом KRAFTOOL MM1»).

Артефакты (sha256, staging == local, перенесены в `scratchpad/phase7b/`):

- `phase7b-shadow-report.json`: `8325d9004bedf7dc1965af12c572770473a1d868dd21a08e2d247028eb8a9bdb`
- `phase7b-gate-sample.json`: `aa5f697df4d0b9aed4b3ba06fea7b4555c5526ee699c9087cdf1b65e146425fc`

canonical_hash (`apps.catalog.processing.canonical_hash`, локально, из Git checkout dev):

- sample_full: `a64a7f4cc55b00399235f9d0f68b366c99688338e9a06c0a99319f5f0b82eb36`
- rows_only: `af872b183b769f05b9970a8aee8a0a27f527af4d7581cc7ae0f7cf79d225922e`

### Stage 1.2 — F-2 STOP

- predictions=**19** < MIN_ROWS_GATE=**100** → сработало условие **F-2**: precision gate на текущем пуле недостижим (даже 100% correct на 19 строках не даёт gate-вердикта).
- Replay Stage 1.3 (детерминизм) **не выполнялся**: при 19 predictions gate-выборка из 100 строк не набирается, сравнение replay не имеет значения для gate; запуск — после решения по F-2.
- Потолок pool=all (read-only SELECT на staging, `transaction_read_only=on`): eligible без stock-фильтра = **1593**; контрольный in-stock = 188 (совпал со Stage 0 и report).
- Экстраполяция hit rate (10.1%) на pool=all ≈ 160 predictions — ориентировочно, не гарантия прохождения MIN_ROWS_GATE.
- STOP по плану. Варианты решения (план §F-2): (a) pool=all — отдельным решением; (b) расширение ruleset — вне замороженного контура, новый цикл; (c) приёмка фазы без gate-вердикта (observational baseline).

### Stage 1 rerun (pool=all, AUTHORIZED AMENDMENT 2026-07-22, exit 0)

Команда (основной прогон и replay идентичны, кроме выходных путей):
`docker exec proff58_staging-web-1 python manage.py catalog_rules_shadow --ruleset /app/data/catalog_processing_rules/tool_type.v1.json --pool all --sample-size 100 --seed 20260721 --out /app/logs/phase7b-shadow-report-pool-all.json --gate-sample-out /app/logs/phase7b-gate-sample-pool-all.json --corpus /app/data/catalog_processing_rules/applied_corpus_tool_type.v1.json`

Основной прогон:

- pool=all size=**1593**; excluded_existing_tool_type=18123; rewrite_attempts=0.
- predictions=**63** (share 0.0395); no_match=1530; collisions=**0**; regression_tier hits/collisions = 0/0.
- Overlap-check: `corpus_overlap_checked=true`; `collision_count=0`.
- Хэши: ruleset_hash=`51b3bbad…` (= pinned canonical, идентичен in-stock прогону); taxonomy_hash=`b357be60…` (идентичен); input_universe_hash=`82536a4698688c927f6decd35787d1bb0d3deb8f3c298f698f9bf6387b749db8` (отличается от in-stock `6c91d37a…` — другой пул, ожидаемо); content_hash=`b9e31a65e80b53a255350b98e6b1736dbfa5d5c8dd5f393b491cdc4e3cc46c12`.
- Gate sample: seed=20260721, rows=**63** (все predictions; <100 → sample = полный набор).
- Performance: duration 20.238s; memory snapshots (`docker stats`, не peak): 279.7MiB / 7.745GiB, CPU 40.3% (t≈10s); 253.2MiB (после завершения).

Per-rule `prediction_hits` (сработали все 11 правил; collision_hits=0, same_slug_multi_hits=0):

| rule_id | raw_hits | prediction_hits | coverage_share |
|---|---|---|---|
| tt-dinamometricheskie-klyuchi-klyuch | 16 | 16 | 0.0100 |
| tt-yashchiki-sumki-keys-prochee | 13 | 13 | 0.0082 |
| tt-siz-ochki-zashchitnye | 11 | 11 | 0.0069 |
| tt-svar-reduktory-regulyator | 5 | 5 | 0.0031 |
| tt-adaptery-universal (№6) | 4 | 4 | 0.0025 |
| tt-bp-pnevmosteplery-gvozde | 4 | 4 | 0.0025 |
| tt-hoz-lenty-malyarnaya | 3 | 3 | 0.0019 |
| tt-krep-shplinty-nabor | 2 | 2 | 0.0013 |
| tt-izm-shtativy-derzhatel (№7) | 2 | 2 | 0.0013 |
| tt-puskovye-provoda-startovye | 2 | 2 | 0.0013 |
| tt-nabory-instrumenta-dielektr | 1 | 1 | 0.0006 |

Строки правил №6/№7 (pool=all ⊃ in-stock строки — ветки консистентны):

- №6 `tt-adaptery-universal` → `adaptery` (4): product_id 6683, 1113, 1112, 6685.
- №7 `tt-izm-shtativy-derzhatel` → `izm-shtativy` (2): product_id 10633, 10635.

Replay (Stage 1.3, детерминизм):

- gate-sample sha256=`c4d2bcc8818c1ce0c58227f334033353f1cc26fbac12ab3eb5926919c18c3526` — **байт-идентичен** основному прогону; canonical_hash(sample_full)=`2e1a684c6036c61f7c91242ecde6bae7535cf27c58654ce107b2ffa1ac858b76` совпадает; порядок product_id совпадает.
- report diff основного прогона и replay: только volatile keys (`started_at`/`finished_at`/`generated_at`, duration 20.238s → 1.161s) и `command.args.out`/`gate_sample_out` (другие выходные пути) → content_hash replay=`8fcbffe8…` отличается ожидаемо и безопасно.
- Вывод: детерминизм matcher/sample подтверждён на пуле 1593.

**F-2 (второе срабатывание)**: predictions=**63** < MIN_ROWS_GATE=**100** даже на pool=all → официальный precision gate на текущем ruleset недостижим. Продуктовый факт: ruleset покрывает 63/1593 (3.95%) eligible каталога; расширение пула исчерпано (pool=all — максимум).

Drift-check после обоих прогонов (read-only, `transaction_read_only=on`):

- Инвариант дублей `(attribute_id, slug)` → 0 violations.
- id=16 = `steplery-i-zaklepochniki`, id=73 = `steplery` — без изменений.
- Counters = Stage 0 baseline: PAV=60896; tt_options=328; CatalogChange total=57 (tool_type applied=56); CatalogProcessingRun=4.
- Пул: pool_all=1593, pool_in_stock=188 — без изменений.
- healthz → 200 `{"status":"ok","db":"ok","redis":"ok"}`.

Локальные артефакты (`scratchpad/phase7b/`, sha256 staging == local):

- `phase7b-shadow-report-pool-all.json` = `ba60e2d9b9a23353a2c5d9d713a3d3e4692b35f21f98cd898a3f4045df1ee0a9`
- `phase7b-gate-sample-pool-all.json` = `c4d2bcc8818c1ce0c58227f334033353f1cc26fbac12ab3eb5926919c18c3526`
- replay-копии: `phase7b-shadow-report-pool-all-replay.json` = `bd1d4c5b…`, `phase7b-gate-sample-pool-all-replay.json` = `c4d2bcc8…` (= основному)

STOP: checkpoint #2. Gate недостижим на текущем ruleset при любом пуле. Ожидание решения владельца.

## Финальный статус (2026-07-22)

**Phase 7B — COMPLETED AS OBSERVATIONAL BASELINE.** Не PASSED и не FAILED.

```
gate_not_reached:
  rows = 63
  required_rows = 100
```

Качество ruleset официально не подтверждено и не опровергнуто.

Подтверждено:

- ruleset детерминирован (replay: gate sample байт-идентичен, sha256 `c4d2bcc8…`, canonical_hash `2e1a684c…`);
- collision_count = 0 на обоих пулах;
- overlap с training corpus отсутствует (`corpus_overlap_checked=true`);
- все 11 правил дают реальные predictions;
- matcher работает стабильно (snapshot isolation `repeatable_read_read_only`, exit 0 оба прогона);
- side effects и drift отсутствуют (drift-check: инварианты, counters, пул без изменений; записей в БД не было);
- максимальное покрытие текущего ruleset: 63 / 1593 = 3.95% eligible;
- правила №6 и №7: 4 и 2 наблюдения соответственно;
- официальный precision gate не состоялся из-за недостаточного объёма predictions (19 на in-stock, 63 на all; требуется ≥100).

Не подтверждено (нельзя утверждать):

- ruleset прошёл precision gate;
- precision ≥ 0.99;
- ruleset готов к promotion;
- правила №6/№7 имеют статистически надёжную precision;
- predictions можно применять к каталогу.

Ruleset остаётся в **candidate tier**. Промоушен и применение к каталогу не авторизованы.

Не выполнено: Stage 2 (разметка) и gate-валидация — отменены решением владельца (невозможны при 63 predictions).

Инвентарь артефактов (`scratchpad/phase7b/`, sha256, staging == local):

- in-stock ветка: `phase7b-shadow-report.json` = `8325d900…`; `phase7b-gate-sample.json` = `aa5f697d…`
- pool=all ветка (canonical baseline): `phase7b-shadow-report-pool-all.json` = `ba60e2d9…`; `phase7b-gate-sample-pool-all.json` = `c4d2bcc8…`
- replay (verification): `phase7b-shadow-report-pool-all-replay.json` = `bd1d4c5b…`; `phase7b-gate-sample-pool-all-replay.json` = `c4d2bcc8…`
- staging-копии `/app/logs/phase7b-*.json` оставлены как evidence.

Изменений кода, БД, ruleset, corpus не производилось; коммитов и PR нет.

Следующий шаг (за пределами фазы, требует отдельного плана и авторизации): **Phase 7C — Ruleset Coverage Expansion** — довести число новых независимых predictions до 120–150, чтобы после overlap-фильтрации, коллизий и исключений гарантированно осталось ≥100 строк для официального gate.
