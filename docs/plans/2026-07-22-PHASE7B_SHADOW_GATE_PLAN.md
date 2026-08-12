# Phase 7B: Shadow-прогон по пулу + gate sample ≥ 100 — план на утверждение

> Статус: PROPOSED v2 (rework по ревью 2026-07-22: Important 1/2, Minor 1
> устранены; D-1 = mixed зафиксирован). Исполнение НЕ авторизовано —
> go/no-go checkpoint.
> Прецеденты процесса: `docs/plans/2026-07-21-PHASE7A_CORPUS_AND_CANDIDATE_RULES_PLAN.md`,
> `docs/plans/2026-07-22-PHASE7A_2_DEVIATION2_REMEDIATION_PLAN.md`.
> Входные условия выполнены: Phase 7A CLOSED (ruleset v1 canonical),
> Phase 7A.2 COMPLETED (DEVIATION-2 RESOLVED, миграция 0027 на staging,
> инвариант дублей = 0 rows, post-deploy verification PASS).

## 0. Что изменилось со времён Phase 7A и почему 7B теперь разблокирована

- Phase 7A.2 устранила DEVIATION-2: `(attribute, slug)` уникален для непустых
  slug (partial unique index `uniq_attributeoption_attr_slug_nonempty`),
  matcher/apply переведены на fail-fast `.get()`, seed-guard в
  `load_tool_types`. Недетерминированный lookup, блокировавший 7B,
  устранён архитектурно, а не обойдён.
- Staging подтверждён на `dev@dbdc5eb` (post-merge deploy #584,
  run 29924840548 success, миграция 0027 applied).
- Правила №6 (`tt-adaptery-universal`) и №7 (`tt-izm-shtativy-derzhatel`)
  утверждены «with monitoring»: их precision обязан быть показан отдельно
  (см. §8, acceptance).

## 1. Точный scope

Phase 7B — **100% наблюдательная** фаза (как 7A): независимая проверка
утверждённого ruleset `tool_type.v1` на полном пуле товаров staging.

Входит:

1. Shadow-прогон ruleset по пулу `in-stock` (все товары с остатком) —
   существующая read-only команда `catalog_rules_shadow` (Phase 6.0,
   proposal-only, zero writes, snapshot `REPEATABLE READ READ ONLY`).
2. Формирование официального `gate_sample` (v1) — 100 predictions,
   fail-closed: обязательная overlap-проверка `sample ∩ training corpus = ∅`.
3. Human gate labels: разметка каждой строки sample решением из enum
   `correct / incorrect / identity_problem / taxonomy_gap / unverifiable`.
4. Gate-валидация `catalog_rules_gate_validate`: observed precision и
   `gate_passed` по неокруглённому precision.
5. Per-rule precision отчёт, отдельно по правилам №6 и №7 (monitoring).
6. Performance Summary (по образцу §6.2 плана 7A) — для оценки
   масштабирования на полный пул в следующих фазах.
7. Итоговый отчёт + Human Decision Log → STOP → решение пользователя.

НЕ входит (явный non-scope):

- Любое применение predictions к каталогу (`Product`,
  `ProductAttributeValue`, `attrs_cache`, `Category`, `AttributeOption`).
- Создание `CatalogProcessingRun` / `CatalogProcessingItem` /
  `CatalogChange` / `ContentFinding`; импорт чего-либо.
- Промоушен ruleset (candidate → production tier) — отдельная фаза и
  отдельная авторизация ПОСЛЕ gate-вердикта.
- Новые правила, изменение ruleset/corpus fixtures, изменение кода,
  миграции, feature flags, deploy, коммиты в репозиторий.
- `pool=all` без отдельного решения пользователя (см. F-2).
- Досampling под правила №6/№7 сверх основного sample (см. F-5).

## 2. Входные артефакты

| Артефакт | Путь | Pinned hash / версия |
|---|---|---|
| Ruleset (APPROVED, Stage 7) | `data/catalog_processing_rules/tool_type.v1.json` | sha256 `93d145e479dfc2c528e849d09bbfc69640f2ca6672766b69f6c7c68cee4b7b8b`; `ruleset_hash = 51b3bbad7c65565637711e5bf9ee74eb7b477ff71b9e25183095ede9cb1044bd` |
| Applied corpus (training, для overlap-check) | `data/catalog_processing_rules/applied_corpus_tool_type.v1.json` | sha256 `32511e850f732c7419cf6c7164d4a41da7de566ecb3929f15f34baf73aba035e` (`expected_recall = 0.59`) |
| Derivation doc (мониторинг-лист, per-rule риски) | `docs/catalog/phase6-ruleset-v1-derivation.md` | Stage 7 CLOSED 2026-07-21 |
| Staging БД | `proff58_staging-db-1`, только SELECT | snapshot isolation `REPEATABLE READ READ ONLY` внутри команды |
| Код shadow/gate | `apps/catalog/management/commands/catalog_rules_shadow.py`, `catalog_rules_gate_validate.py`, `apps/catalog/rules_engine.py` | ветка `dev`, без изменений |

Gate-константы из кода (не из плана):
`PRECISION_GATE = 0.99`, `MIN_ROWS_GATE = 100`
(`catalog_rules_gate_validate.py:24-25`); правило:
`precision >= 0.99 and rows >= 100 and collision_count == 0 and
corpus_overlap_checked` (там же, `:88-103`).

## 3. Разрешённые операции

- SSH `taximeter@194.87.99.126`; read-only SQL только в транзакциях
  `BEGIN TRANSACTION READ ONLY … ROLLBACK` (доказательство режима —
  `SHOW transaction_read_only = on` в протоколе).
- Запуск на `proff58_staging-web-1`:
  `python manage.py catalog_rules_shadow …` и чтение его артефактов —
  команда read-only по построению (одна snapshot-транзакция, далее CPU).
- Создание файлов-артефактов: staging `/app/logs/phase7b-*` и локально
  `scratchpad/phase7b/`. Перезапись только через `--force`
  (атомарная запись с backup/restore — контракт команды).
- `docker stats --no-stream` (Performance Summary), `docker exec … cat/ls`.
- Локально: `catalog_rules_gate_validate`, скрипты сводок в
  `scratchpad/phase7b/`, запуск тестов.

Запрещено: любые INSERT/UPDATE/DELETE к staging-БД; изменение каталога,
processing-таблиц, feature flags, конфигурации, кода, миграций;
deploy; коммиты/PR; recreate контейнеров; изменение входных артефактов
(ruleset/corpus — сверяются по pinned-хэшам в Stage 0).

## 4. Ожидаемые изменения данных

В БД — **никаких** (команда не пишет; snapshot-транзакция read-only на
уровне SQL). Новые файлы — полный инвентарь двумя группами.

Canonical deliverables:

| Файл | Где | Содержимое |
|---|---|---|
| `phase7b-shadow-report.json` | staging `/app/logs/` → локально `scratchpad/phase7b/` | coverage по пулу, per-rule hits, `collision_count`, `snapshot_isolation`, длительности |
| `phase7b-gate-sample.json` | staging `/app/logs/` → локально | 100 строк: `product_id`, `facts_hash`, `predicted_option_slug`, `rule_refs`; `corpus_overlap_checked=true`, `seed`, `pool`, хэши ruleset/matcher/taxonomy |
| `phase7b-gate-labels.json` | локально | 100 labels: `product_id`, `decision`, `reviewer_id`, `reviewed_at`; `sample_hash`, `ruleset_hash`, `matcher_version` |
| `sample_summary.md` | локально `scratchpad/phase7b/` | сводка 100 строк sample для разметки (Stage 2.1) |
| `phase7b-report.md` | локально | сводка gate, per-rule precision, Performance Summary, отклонения, Decision Log |

Temporary verification artifacts (существуют только для проверок
фазы; не являются deliverables):

| Файл | Где | Назначение |
|---|---|---|
| `phase7b-shadow-report-replay.json` | staging `/app/logs/` → локально | второй прогон детерминизма (Stage 1.3) |
| `phase7b-gate-sample-replay.json` | staging `/app/logs/` → локально | второй sample для сравнения `canonical_hash` (Stage 1.3) |
| `*.py`-скрипты сводок/per-rule precision | локально `scratchpad/phase7b/` | Stage 2.1 и 3.2 |

Rollback (§5) охватывает весь `scratchpad/phase7b/` и все файлы
`/app/logs/phase7b-*`, созданные этой фазой; существовавшие до фазы
артефакты не трогаем.

## 5. Dry-run и rollback contract

- Shadow-прогон сам по себе dry-run по построению: zero writes,
  snapshot-чтение; повторный запуск с тем же `--seed 20260721` даёт
  тот же sample (детерминизм фиксируется сравнением `sample_hash`
  двух прогонов в Stage 1).
- Rollback = удаление всех файлов-артефактов Phase 7B по инвентарю §4:
  локально — весь `scratchpad/phase7b/`; на staging — все
  `/app/logs/phase7b-*`, созданные этой фазой (включая replay-пару
  Stage 1.3). Артефакты, существовавшие до фазы, не удаляются.
  Восстанавливать в БД нечего — записей нет. Pre-existing файлы при
  `--force` защищены backup/restore контрактом команды.
- Идемпотентность: повтор Stage 1–4 безопасен; `--out` без `--force`
  падает, если файл существует (fail-closed против случайной перезаписи).

## 6. Подтверждение: 7B не опирается на исторический slug `steplery` id=16

Проверено на pinned-артефактах (grep, 2026-07-22):

- В `tool_type.v1.json` строка `steplery` встречается только как
  `bp-pnevmosteplery` (rule №3, другой slug, другая семантика);
  ни один из 11 `option_slug` не равен `steplery` или
  `steplery-i-zaklepochniki`.
- В `applied_corpus_tool_type.v1.json` `applied_option_slug` —
  только `bp-pnevmosteplery` из этого семейства; slug `steplery`
  в labels отсутствует.
- Taxonomy, которую shadow-прогон читает (`_allowed_tool_type_options`),
  — это ТЕКУЩАЯ БД post-7A.2: slug уникален (инвариант = 0 rows),
  id=16 → `steplery-i-zaklepochniki`, канонический `steplery` = id=73;
  недетерминированного выбора больше не существует (`.get()` fail-fast).
- Следовательно: predictions 7B не затрагивают семейство `steplery`
  вообще, а lookup-контракт, на который опирается matcher, после 7A.2
  детерминирован.

## 7. Stages и команды

### Stage 0 — pre-checks (staging, read-only)

- [ ] **0.1** Staging code-level = post-#584:
  `docker exec proff58_staging-web-1 ls apps/catalog/migrations/0027_reslug_steplery_unique_option_slug.py`
  и `docker exec proff58_staging-web-1 grep -c uniq_attributeoption_attr_slug_nonempty apps/catalog/models.py` → `1` (или более).
- [ ] **0.2** Инварианты 7A.2 не деградировали (READ ONLY):
  duplicate-invariant → 0 rows; id=16 = `steplery-i-zaklepochniki`;
  id=73 = `steplery`; индекс `uniq_attributeoption_attr_slug_nonempty`
  существует.
- [ ] **0.3** Baseline counters (фиксируются свежими, НЕ считаются
  вечными): PAV total, tool_type options (=328), applied changes
  (`status=applied`, `target_kind=tool_type`), non-final changes.
- [ ] **0.4** Pinned-хэши входных артефактов совпадают с §2
  (`sha256sum` локально); healthz → 200.
- [ ] **0.5** Оценка ёмкости пула (READ ONLY): товары `in-stock`
  без текущего PAV tool_type — нужен запас predictions ≥ 100
  (оценка верхней границы; фактический выход — Stage 1).

STOP-условие Stage 0: любой drift инвариантов/хэшей или code-level ≠
post-#584 → фаза не начинается, отчёт пользователю.

### Stage 1 — shadow-прогон + официальный gate_sample (staging, read-only)

- [ ] **1.1** Прогон (таймаут ≥ 280 с — хост медленный):

```bash
docker exec proff58_staging-web-1 python manage.py catalog_rules_shadow \
  --ruleset /app/data/catalog_processing_rules/tool_type.v1.json \
  --pool in-stock --sample-size 100 --seed 20260721 \
  --out /app/logs/phase7b-shadow-report.json \
  --gate-sample-out /app/logs/phase7b-gate-sample.json \
  --corpus /app/data/catalog_processing_rules/applied_corpus_tool_type.v1.json
```

  (путь `/app/data/...` подтверждается в Stage 0 через `ls`; если в
  образе fixtures лежат иначе — забрать repo-файлы в `/tmp` контейнера
  тем же `docker cp`, хэши сверить до запуска.)

- [ ] **1.2** Из отчёта: `collision_count == 0` (иначе F-3),
  `snapshot_isolation = repeatable_read_read_only`, predictions total
  ≥ 100 (иначе F-2), per-rule hits сведены.
- [ ] **1.3** Детерминизм: повторный прогон с ДВУМЯ новыми путями —
  заменить только `--out` недостаточно: команда проверяет оба выходных
  файла до записи и пишет пару как единую группу, поэтому без нового
  `--gate-sample-out` второй запуск fail-closed остановится на
  существующем `phase7b-gate-sample.json`:

```bash
docker exec proff58_staging-web-1 python manage.py catalog_rules_shadow \
  --ruleset /app/data/catalog_processing_rules/tool_type.v1.json \
  --pool in-stock --sample-size 100 --seed 20260721 \
  --out /app/logs/phase7b-shadow-report-replay.json \
  --gate-sample-out /app/logs/phase7b-gate-sample-replay.json \
  --corpus /app/data/catalog_processing_rules/applied_corpus_tool_type.v1.json
```

  Критерий: `canonical_hash(phase7b-gate-sample.json) ==
  canonical_hash(phase7b-gate-sample-replay.json)` — gate sample не
  содержит временных полей и строится детерминированно из seed +
  product_id. Дополнительно сверяются: `rows`, порядок строк,
  `product_id`, `facts_hash`, `predicted_option_slug`, `rule_refs`.
  Несовпадение → F-4.
- [ ] **1.4** Артефакты перенесены локально (`docker exec … cat`),
  сверены sha256 обеих копий; Performance Summary: длительность
  прогона, observed container memory snapshot
  (`docker stats --no-stream --format "{{.MemUsage}}" proff58_staging-web-1`
  сразу после прогона — моментальное значение, НЕ peak; настоящий peak
  здесь не является gate-критерием и не измеряется), размеры файлов.

### Stage 2 — сводка sample пользователю + human labels

- [ ] **2.1** Локальная сводка `scratchpad/phase7b/sample_summary.md`:
  100 строк — product_id, название/группа, `predicted_option_slug`,
  `rule_refs`; распределение predictions по правилам (сколько строк
  на каждое из 11 правил; отдельно помечены строки правил №6/№7).
- [ ] **2.2** Процесс разметки — D-1 = **mixed** (решение пользователя
  2026-07-22, зафиксировано в Decision Log):
  1. analyst предварительно размечает очевидные строки с кратким
     обоснованием по каждой строке;
  2. пользователь проверяет ВСЕ строки с предварительными метками
     `incorrect`, `identity_problem`, `taxonomy_gap`, `unverifiable`;
  3. пользователь проверяет ВСЕ строки правил №6
     (`tt-adaptery-universal`) и №7 (`tt-izm-shtativy-derzhatel`)
     независимо от предварительной метки;
  4. пользователь дополнительно проверяет случайную выборку ≥ 20
     строк, помеченных analyst как `correct`;
  5. `reviewer_id` в labels отражает финального принимающего решение,
     а не только автора предварительной метки.
- [ ] **2.3** `phase7b-gate-labels.json` заполняется по схеме:
  каждый `product_id` sample ровно один раз; `decision` из enum;
  `reviewer_id` + `reviewed_at` обязательны; `sample_hash =
  canonical_hash(sample)`, `ruleset_hash`/`matcher_version` из sample.
  Локальная проверка `validate_gate_labels` до gate-валидации.

### Stage 3 — gate-валидация (локально)

- [ ] **3.1**

```bash
./.venv/Scripts/python.exe manage.py catalog_rules_gate_validate \
  --gate-sample scratchpad/phase7b/phase7b-gate-sample.json \
  --labels scratchpad/phase7b/phase7b-gate-labels.json
```

  Ожидание: `rows=100`, decisions-сводка, `observed_precision`,
  `gate_passed=true|false (precision>=0.99 and rows>=100 and
  collision_count==0 and corpus_overlap_checked)`.
- [ ] **3.2** Per-rule precision (скрипт `scratchpad/phase7b/`):
  labels × sample.rows → `correct/rows` по каждому `rule_ref`;
  отдельные строки для №6 `tt-adaptery-universal` и №7
  `tt-izm-shtativy-derzhatel` (мониторинг по решению Stage 7);
  разбор каждого non-`correct` label (класс ошибки, правило, товар).

### Stage 4 — отчёт + STOP

- [ ] **4.1** `phase7b-report.md`: gate-вердикт, per-rule таблица,
  разбор non-correct, Performance Summary, отклонения (F-* если были),
  Human Decision Log со всеми решениями фазы.
- [ ] **4.2** STOP → решение пользователя: вердикт по gate и дальнейший
  путь (промоушен ruleset / доработка правил / расширение corpus) —
  отдельной авторизацией, вне scope 7B.

## 8. Acceptance criteria

1. Stage 0: все инварианты зелёные; staging code-level = post-#584.
2. `collision_count == 0`; `corpus_overlap_checked == true`;
   `sample ∩ corpus = ∅` (проверено и командой, и локально).
3. `rows = 100`; каждая строка имеет ровно один валидный label
   (`validate_gate_labels == []`).
4. `gate_passed` вычислен и зафиксирован с точным
   `observed_precision` (неокруглённым) и сводкой decisions.
5. Per-rule precision таблица представлена; правила №6/№7 показаны
   отдельными строками с их denominators (даже если малы — с пометкой
   low-confidence, см. F-5).
6. Все non-`correct` labels разобраны по классам
   (incorrect / identity_problem / taxonomy_gap / unverifiable).
7. Performance Summary включён; артефакты воспроизводимы
   (два прогона → один `sample_hash`).
8. Доказательство read-only в протоколе (`transaction_read_only=on`,
   zero writes по построению команды; инварианты Stage 0 повторены
   в конце фазы и не деградировали).

## 9. F-условия (остановка и отчёт, без самостоятельных обходов)

- **F-1.** Drift инвариантов Stage 0 / финальных инвариантов,
  обнаруженный write в БД, несовпадение pinned-хэшей.
- **F-2.** Predictions в пуле `in-stock` < 100 → официальный gate
  невозможен (`rows >= 100`). Отчёт; пользователь решает: `pool=all`,
  расширение ruleset, или приёмка фазы без gate-вердикта.
- **F-3.** `collision_count > 0` в shadow-отчёте.
- **F-4.** Несовпадение `sample_hash` между двумя прогонами
  (недетерминизм семплинга).
- **F-5.** Правила №6/№7 имеют < 5 строк в sample → precision по ним
  low-confidence; досampling под конкретные правила — только отдельным
  решением пользователя (не входит в официальный sample).
- **F-6.** `gate_passed = false` — НЕ дорабатывать ruleset молча:
  разбор non-correct в отчёте, решение о rework — за пользователем.

## 10. Human Decision Log (заполняется по ходу фазы)

| Decision | Reason | Timestamp (UTC) |
|---|---|---|
| Phase 7B plan — PROPOSED | go/no-go checkpoint после закрытия 7A.2 | 2026-07-22 (analyst) |
| Plan v1 — CHANGES REQUIRED | Important 1 (Stage 1.3: нужны оба новых выходных пути), Important 2 (инвентарь файлов неполон), Minor 1 (`docker stats --no-stream` ≠ peak) | 2026-07-22 (пользователь) |
| D-1 = mixed | analyst pre-label с обоснованием; пользователь проверяет все non-correct, ВСЕ строки правил №6/№7 и ≥ 20 случайных correct; `reviewer_id` = финальный принимающий | 2026-07-22 (пользователь) |
| Plan v2 per reviewer recipe | §4 — инвентарь двумя группами (canonical + temporary), rollback охватывает обе группы; Stage 1.3 — оба пути + критерий сравнения; memory snapshot переименован | 2026-07-22 (analyst rework) |
| | | |
