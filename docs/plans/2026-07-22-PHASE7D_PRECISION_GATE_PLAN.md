# Phase 7D — Precision Gate для tool_type.v2 (план)

**Статус:** Proposed v2, 2026-07-22 (учтён review пользователя от
2026-07-22: исправлен Stage 1.3, уточнены D-1/D-2/D-4, добавлены
Overall CI, Decision Owner, запрет git push, F-7). Основан на
результатах Phase 7C (COMPLETED, commit
`2375d8e4b542f1acea1e6576df98921f2e8d005e`).

## 1. Цель и граница фазы

Phase 7C ответила на вопрос «мы ничего не сломали и существенно увеличили
покрытие?» (coverage + stability). Phase 7D отвечает на вопрос:

> Насколько качественно работают 325 predictions ruleset v2 на реальных
> товарах? (precision + promotion decision)

Результат фазы — **человеческое решение** (PROMOTE / PROMOTE WITH
EXCEPTIONS / HOLD / REJECT), основанное на статистически обоснованном
официальном gate. Фаза намеренно короткая: вся инженерная работа
(ruleset, freeze, shadow-контур, детерминизм) завершена в 7C.

**Фаза НЕ подтверждает и не изменяет:** coverage, matcher, taxonomy,
состав правил. Precision измеряется, а не конструируется.

## 2. Входные артефакты (pins из Phase 7C)

| Артефакт | Pinned значение |
|---|---|
| Ruleset v2 | `data/catalog_processing_rules/tool_type.v2.json`, LF sha256 `ff449701939e993e6bf3e0d68de20d07a672884a54df602c7b2807316f8728ec`; canonical ruleset_hash `9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330` |
| Commit 7C | `2375d8e4b542f1acea1e6576df98921f2e8d005e` (ровно 3 файла) |
| Ruleset v1 (default, frozen) | LF sha256 `b476199afaf83e7f305d335d7ed2c77d855469f59fd73dbfe357c9183d7d1e6e` |
| Applied corpus (overlap-check) | LF sha256 `6663a6fe48c2c2656604a179c1f70338a08a9d3e2a364a5ec2f663600b85d6e3` |
| taxonomy_hash | `b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b` |
| input_universe_hash | `82536a4698688c927f6decd35787d1bb0d3deb8f3c298f698f9bf6387b749db8` |
| Shadow report 7C (референс counts) | `scratchpad/phase7c/phase7c-shadow-report-v2-pool-all.json`, sha256 `4c1f39d3d9426790eb3afa4a08c6435b457794d92e7443b6022cc2e0a8bc760e` |
| Derivation doc v2 (monitoring-лист) | `docs/catalog/phase7c-ruleset-v2-derivation.md` |
| Код gate/shadow | `catalog_rules_shadow.py`, `catalog_rules_gate_validate.py`, `apps/catalog/rules_engine.py` — ветка `dev`, без изменений |

Gate-константы из кода (не из плана): `PRECISION_GATE = 0.99`,
`MIN_ROWS_GATE = 100` (`catalog_rules_gate_validate.py:24-25`); правило:
`precision >= 0.99 and rows >= 100 and collision_count == 0 and
corpus_overlap_checked` (там же, fail-closed аудит sample).

Monitoring-лист (handoff 7C, обязательное представительство в разметке):
`tt-svar-apparaty-truby` (10), `tt-bp-vozdukhoduvki-akkum` (4),
`tt-obor-mebel-verstak` (4), `tt-izm-kolesa-dorozhnoe` (4),
`tt-yashchiki-sumki-benzopila` (4), `tt-siz-pozh-inventar-polotno` (3),
`tt-siz-izveshchateli-gromkogovoritel` (3) — итого 32 predictions; отдельно
`tt-siz-ochki-shitok` (15, из них 10 same-slug multi-match).

## 3. Scope и non-scope

**Scope:**

- freeze-сверка pins (Stage 0);
- формирование **официального** gate sample (Stage 1) — новый прогон
  `catalog_rules_shadow` с новым seed, тем же pinned v2, `pool=all`;
- human labeling по смешанной модели (Stage 2);
- официальный gate `catalog_rules_gate_validate` + per-rule статистика
  с confidence intervals (Stage 3);
- фиксация человеческого решения (Stage 4).

**Non-scope:**

- promotion и изменение default `RULESET_PATH` — только после verdict
  PROMOTE и отдельной авторизации (Stage 5 вне начального scope);
- любые изменения ruleset v2/v1, matcher, taxonomy, corpus, схемы,
  кода; новые правила; derivation-циклы;
- применение predictions к каталогу; изменения БД (все staging-операции
  read-only, как в 7C); deploy, миграции, feature flags;
- коммиты без отдельной авторизации; **`git push` — до отдельной
  авторизации, даже после возможного разрешённого коммита**;
- переиспользование sample 7C как официального (он остаётся evidence).

## 4. Разрешённые операции

- SSH `taximeter@194.87.99.126`; `docker exec proff58_staging-web-1
  python manage.py catalog_rules_shadow …` (read-only по построению,
  snapshot `repeatable_read_read_only`); чтение артефактов;
  `docker stats --no-stream` (snapshot, не peak).
- Файлы-артефакты: staging `/app/logs/phase7d-*`, локально
  `scratchpad/phase7d/`; перезапись только через `--force`.
- Локально: `catalog_rules_gate_validate` (read-only по построению),
  временные скрипты статистики в `scratchpad/phase7d/`, запуск тестов.
- `pool=all` — требует явного подтверждения при авторизации плана
  (прецедент F-2 из 7B/7C: единственная вселенная с 325 predictions v2).

Запрещено: INSERT/UPDATE/DELETE к staging-БД; изменение входных
артефактов; коммиты/PR/**push** без отдельной авторизации; deploy;
recreate контейнеров; досampling сверх процедуры D-1 без отдельного
решения; самостоятельный поиск по интернету при разметке (см. §6
Stage 2).

## 5. Решения D (приняты при review 2026-07-22)

### D-1 = (a). Monitoring representation: random core + минимальный amendment

Официальный sample формирует командой (`--sample-size 100 --seed
<D-3>`). Затем применяется правило минимального amendment:

- если random core уже содержит monitoring rule_ref — **ничего не
  добавляется**;
- если rule_ref отсутствует — добавляется **ровно одна** строка,
  детерминированно (наименьший product_id) из predictions того же
  официального report;
- **вторая** строка для rule_ref допускается только если первая
  относится к same-slug multi-match и не позволяет оценить правило
  самостоятельно.

Amendment-строки берутся verbatim из report (те же `facts_hash`, slug,
rule_refs) — они из того же collision-free, overlap-checked прогона.
`validate_gate_sample` локально перепроверяет полный итоговый набор
(уникальность id, overlap с corpus = 0, обязательные поля). Итоговый
файл = новый артефакт `phase7d-gate-sample-official.json` с блоком
`amendment` (список добавленных product_id и rule_ref); labels и gate
работают с этим файлом; знаменатель precision включает все строки.
Максимум ~116 строк.

(Отклонённые варианты: (b) чистый random с post-hoc флагами — support
3–4 выпадают с вероятностью ~33% каждый; (c) увеличенный random без
гарантии покрытия.)

### D-2 = mixed. Разметка

Analyst (агент) предварительно размечает все строки с кратким
обоснованием в `phase7d-labels-prelim.json`. Reviewer (пользователь)
обязательно проверяет: все `incorrect`/`identity_problem`/
`taxonomy_gap`/`unverifiable`; все строки monitoring-правил; случайные
≥20 строк, помеченных analyst как `correct`.

Reviewer может: **изменить decision; изменить rationale; оставить
analyst rationale без изменений.** Reviewer утверждает не только enum,
но и текстовое обоснование.

Финальный `phase7d-labels.json`: `reviewer_id` = финальный принимающий
решение (пользователь); решения reviewer имеют приоритет; расхождения
analyst/reviewer фиксируются в протоколе.

### D-3 = seed 20260722, random core 100

Официальный sample обязан быть новым: `--seed 20260722
--sample-size 100` (seed 7C `20260721` не переиспользуется).

### D-4 = PROMOTE WITH EXCEPTIONS через v2.1

Если gate в целом пройден, но отдельные правила провалились:
исключаемые правила удаляются из v2 → ruleset **v2.1**, который получает
**новый canonical ruleset_hash** и новый LF byte sha256 (полный re-pin),
повторную corpus regression и shadow-проверку (collisions=0, регрессия
оставшихся predictions полная) — всё в рамках отдельно авторизуемого
Stage 5. Без re-pin исключения не применяются.

## 6. Стадии

### Stage 0 — Freeze pre-checks

- [ ] **0.1** Все pins §2 зелёные: v2 LF sha256 (рабочая копия через
  `sed 's/\r$//'`), canonical ruleset_hash из `load_ruleset`, v1/corpus
  LF sha256, commit `2375d8e` присутствует (`git log`), taxonomy_hash и
  input_universe_hash — по свежему read-only snapshot staging taxonomy
  (процедура как Stage 0 в 7C). Расхождение → F-1.
- [ ] **0.2** Frozen inputs: `git status` — нет tracked-модификаций кода/
  ruleset/corpus; default `RULESET_PATH` (`rules_engine.py:30`) →
  `tool_type.v1.json`; staging DB counters (pool all = 1593,
  excluded/typed = 18123) — read-only SELECT в
  `BEGIN TRANSACTION READ ONLY … ROLLBACK`.
- [ ] **STOP 0** → checkpoint пользователю.

### Stage 1 — Официальный gate sample

- [ ] **1.1** LF-копия v2 → контейнер `/app/logs/phase7d-tool_type.v2.json`;
  sha256 контейнера == pinned LF (иначе F-1).
- [ ] **1.2** Официальный прогон (seed D-3):

```bash
docker exec proff58_staging-web-1 python manage.py catalog_rules_shadow \
  --ruleset /app/logs/phase7d-tool_type.v2.json \
  --pool all --sample-size 100 --seed 20260722 \
  --out /app/logs/phase7d-shadow-report-v2-official.json \
  --gate-sample-out /app/logs/phase7d-gate-sample-random100.json \
  --corpus /app/data/catalog_processing_rules/applied_corpus_tool_type.v1.json
```

  exit 0; collisions=0; `corpus_overlap_checked=true` в sample-артефакте.
- [ ] **1.3** Детерминизм и стабильность вселенной (два независимых
  контроля; сравнение sample с 7C НЕ выполняется — новый seed
  закономерно даёт другой sample):
  - **(a) replay с тем же seed:** повторный прогон 1.2 в `-replay`
    пути; критерий — normalized diff двух reports пуст (volatile keys и
    out-пути исключаются), gate sample байт-идентичен, per-rule
    counters идентичны. Расхождение → F-2.
  - **(b) стабильность вселенной против 7C:** `counts`, список
    `predictions` (product_id → slug, упорядоченный) и `per_rule`
    counters официального report == референсу 7C (`4c1f39d3…`).
    Расхождение → F-2 (drift вселенной или matcher). Пересечение
    нового sample с sample 7C фиксируется чисто информационно.
- [ ] **1.4** Monitoring coverage random core: per-rule счётчики по 8
  monitoring refs. Amendment по D-1 (минимальное число строк); сборка
  `phase7d-gate-sample-official.json` (random rows + amendment rows
  verbatim из report + блок `amendment`); локальный
  `validate_gate_sample` против corpus (уникальность, overlap=0, поля)
  — иначе F-3. Если monitoring-покрытие не обеспечено и amendment
  невозможен → F-4.
- [ ] **1.5** Freeze sample: sha256 официального sample-файла, состав
  (100 random + M amendment), pin в протокол. Артефакты локально.
- [ ] **STOP 1** → пользователь утверждает sample до начала разметки.

### Stage 2 — Human labeling (mixed, D-2)

- [ ] **2.1** Analyst pre-labels: `phase7d-labels-prelim.json` — каждая
  строка sample: decision из enum (`correct`, `incorrect`,
  `identity_problem`, `taxonomy_gap`, `unverifiable`) + однофразовое
  обоснование. **Разрешённые источники верификации — только:** факты
  строки (name, article, brand, source_group), snapshot taxonomy
  (соседние товары slug), derivation doc v2. **Самостоятельный поиск
  по интернету запрещён**; если разрешённых источников недостаточно —
  ставится `unverifiable`. Same-slug multi-match строка = одна
  классификация предсказанного slug (не collision, не две строки).
- [ ] **2.2** Reviewer verification (пользователь): все не-`correct`,
  все monitoring-строки, random ≥20 analyst-`correct`. Reviewer может
  изменить decision, изменить rationale или оставить analyst rationale
  (D-2); те же ограничения источников и правило `unverifiable`
  применяются и к reviewer.
- [ ] **2.3** Финальный `phase7d-labels.json`: `sample_hash =
  canonical_hash(official sample)`, `ruleset_hash` v2,
  `matcher_version`, `reviewer_id` = финальный принимающий,
  `reviewed_at`; локальный `catalog_rules_gate_validate --gate-sample …
  --labels …` в режиме проверки схемы (violations → F-5, исправление до
  продолжения; `sample_hash` mismatch → F-7). Знаменатель precision =
  все строки, включая `unverifiable` и `taxonomy_gap` (правило 7B).
- [ ] **STOP 2** → пользователь утверждает labels.

### Stage 3 — Gate + статистика

- [ ] **3.1** Официальный запуск: `catalog_rules_gate_validate
  --gate-sample phase7d-gate-sample-official.json --labels
  phase7d-labels.json` локально; зафиксировать decisions-сводку,
  **неокруглённый** observed precision, `gate_passed` (true|false —
  оба исхода валидны, это вход Stage 4, а не провал фазы).
- [ ] **3.2** Статистика (временный скрипт `scratchpad/phase7d/`,
  удаляется при завершении):
  - **Overall precision с Wilson 95% CI — основной KPI фазы;**
  - precision по каждому rule_ref с Wilson 95% CI;
  - отдельно monitoring-группа (8 refs);
  - support buckets (1–4 / 5–9 / 10+);
  - per-decision распределение;
  - разбор каждой не-`correct` строки (product_id, rule_ref, decision,
    обоснование).
- [ ] **3.3** Протокол `phase7d-report.md`: полное evidence.
- [ ] **STOP 3** → gate-результаты пользователю.

### Stage 4 — Decision

**Decision owner: Product Owner (пользователь).** Вердикт с
обоснованием в Human Decision Log:

- **PROMOTE** → готовится отдельная авторизация Stage 5;
- **PROMOTE WITH EXCEPTIONS** → список исключаемых правил + D-4;
- **HOLD** → что именно нужно для повторного gate (больше данных,
  доразметка, новый sample);
- **REJECT** → ruleset v2 остаётся candidate-tier, v1 default без
  изменений.

### Stage 5 — Promotion (ВНЕ начального scope; отдельная авторизация)

Контур (только при PROMOTE-вердикте): изменение default
`RULESET_PATH` → `tool_type.v2.json` (либо v2.1 при exceptions, D-4) в
`rules_engine.py`; re-pin; тесты; отдельный commit; **`git push`
запрещён без отдельной авторизации**; deploy на staging; smoke shadow
с default ruleset (predictions == официальным); rollback = revert
commit. Детальный план Stage 5 утверждается отдельно после Stage 4.

## 7. F-условия (немедленный STOP)

- **F-1.** Drift любого pinned hash/invariant (Stage 0, 1.1).
- **F-2.** Replay с тем же seed ≠ официальный прогон (недетерминизм),
  либо `counts`/`predictions`/`per_rule` официального report ≠
  референс 7C (drift вселенной/matcher).
- **F-3.** Sample пересекается с training corpus
  (`validate_gate_sample`) или дубли product_id.
- **F-4.** Monitoring-покрытие не обеспечено и amendment-механизм
  невозможен.
- **F-5.** Labels невалидны (`validate_gate_labels` violations) —
  разметка не считается завершённой.
- **F-6.** Любая запись в БД; изменения вне `/app/logs/phase7d-*`
  (staging) и `scratchpad/phase7d/` (локально); drift frozen inputs.
- **F-7.** `sample_hash` в labels ≠ canonical hash официального gate
  sample. (Архитектурный инвариант; технически уже ловится
  `validate_gate_labels`, зафиксирован явно.)

`gate_passed=false` — НЕ F-условие: это легитимный результат gate,
вход для Stage 4.

## 8. Инвентарь артефактов

Deliverables (сохраняются):

- `scratchpad/phase7d/phase7d-report.md` — протокол + Human Decision Log;
- `phase7d-shadow-report-v2-official.json`, `phase7d-gate-sample-random100.json`;
- `phase7d-gate-sample-official.json` (random + amendment, frozen);
- `phase7d-labels-prelim.json` (analyst), `phase7d-labels.json` (final);
- `phase7d-gate-output.txt`, `phase7d-per-rule-stats.txt`.

Temporary (удаляются при завершении, после фиксации sha256):

- replay-артефакты (`phase7d-shadow-report-v2-official-replay.json`,
  `phase7d-gate-sample-random100-replay.json`);
- скрипт per-rule статистики; LF-копия v2; контейнерные
  `/app/logs/phase7d-*`.

## 9. Acceptance criteria

1. Stage 0: все pins зелёные, frozen inputs без drift.
2. Официальный sample произведён командой (audit-поля
   `corpus_overlap_checked=true`, `collision_count=0`); replay с тем же
   seed идентичен; counts/predictions/per_rule совпали с референсом 7C;
   `validate_gate_sample` чист.
3. Monitoring-представительство обеспечено минимальным amendment
   (D-1); состав sample заморожен и утверждён.
4. Labels валидны; `reviewer_id` = финальный принимающий решение;
   reviewer утвердил и decisions, и rationale.
5. Gate исполнен; неокруглённый precision и `gate_passed` (любой
   исход) зафиксированы честно; per-rule/monitoring/bucket статистика
   с CI представлена.
6. **Overall precision reported with Wilson 95% CI.**
7. Человеческое решение Decision owner записано в Human Decision Log.
8. Ноль записей в БД; cleanup выполнен; v1 остаётся default при любом
   исходе, кроме отдельно авторизованного Stage 5; `git push` не
   выполнялся.

## 10. Rollback

Фаза read-only; откат = удаление `scratchpad/phase7d/` и
`/app/logs/phase7d-*`. Система остаётся байт-в-байт в состоянии
post-7C: v2 закоммичен как candidate, default — v1.
