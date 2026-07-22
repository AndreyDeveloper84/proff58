# Phase 6 — proposal-only / shadow plan: детерминированные правила tool_type

Статус: **approved** (решения 1–5 утверждены 2026-07-20; amendments по ревью
2026-07-21 — `2026-07-21-PHASE6_0_SHADOW_RULES_REVIEW.md`). Документ — план и
read-only анализ: **никаких изменений staging, taxonomy, массовых запусков и
auto-apply**. Первый live run, создание options и merge реализации — только по
отдельным решениям.

Базовые документы: роадмап `2026-07-17-CATALOG_RESEARCH_QUEUE_ROADMAP_V2.md`
(§18 Phase 6), закрытие batch-50
`docs/catalog/phase5-batch50-closure-report.md`.

## Цель Phase 6 (по роадмапу)

Детерминированные массовые правила: brand + model series, устойчивые
слова/фразы в названии, исходная категория 1С, артикул/префикс, существующие
атрибуты. Правила работают **только как proposals с модерацией**; Codex
research остаётся для неоднозначного длинного хвоста. Auto-apply не
вводится никогда в рамках этого плана.

**Ограничение первого slice:** существующие атрибуты (PAV) как измерение
правил в первый matcher НЕ входят и отложены на следующую версию ruleset
(amendment 2026-07-21).

## Read-only impact analysis (staging, 2026-07-20; только SELECT)

Критерии пула shadow (уточнены 2026-07-21): `is_active=True`,
`content_locked=False`, непустой `article` (whitespace-only считается
пустым), без PAV `tool_type` с `value_option IS NOT NULL` (NOT EXISTS);
пул `in-stock` добавляет `available_quantity > 0`. Эти критерии **строже**
`catalog_queue_create` (который не фильтрует `is_active`/`content_locked`/
`article`); основной текст ниже и отчёты используют строгий вариант.

`pool.size` означает **untyped eligible pool**; typed eligible universe
(те же критерии, но с заполненным tool_type) публикуется отдельно.
`excluded_existing_tool_type` — это размер typed eligible universe для
выбранного пула, а НЕ число попыток перезаписи; отдельная метрика
`rewrite_attempts` обязана оставаться равной 0 (конструкция исключает
typed-товары до матчинга).

| Показатель | Значение |
|---|---|
| active товаров всего | 22 156 |
| без `tool_type` (весь каталог, без stock-фильтра) | 8 403 |
| **in-stock пул (строгие критерии)** | **190** |
| shadow-hits валидированных правил | **1/190** (`krep-shplinty` — «шплинт»; `puskovye-provoda` — 0) |

Числа 190 / 8 403 / PAV 60 896 — **baseline observations на момент
2026-07-20**, а не вечные assertions: staging-проверки сравнивают pre/post
снимки текущего запуска.

Частота taxonomy-gap типов batch-50 в in-stock пуле: динамометрический ключ —
**3** (закрыт ADR-0011: option материализована 2026-07-21, remediation
12957/12959 завершена), воронка — 2, FastClip — 2, компрессометр 1,
ледоступы 1, ESD-браслет 1, лодочный мотор / мерная ёмкость / отсос припоя — 0.

Top source_groups пула: Электроинструмент 26, Слесарно-столярный 24,
Хозтовары/сад 18, Запчасти 14, СИЗ 13, Наборы инструмента 13,
Аккумуляторный 12, Автомобильный 10, Измерительный 8.

### Выводы из анализа

1. Детерминированные правила, валидированные на batch-50, покрывают
   **~0,5%** in-stock пула — keyword-правила дают малый вклад; массовый
   выигрыш Phase 6 возможен только за счёт системных family/brand-series
   правил, которые выводятся из applied-корпуса (состав корпуса —
   см. «current-state corpus» ниже). Важно: applied-корпус — это training
   data; доказательство precision на тех же товарах было бы training leakage
   (см. gate 6.1 — независимая выборка ≥ 100 predictions).
2. In-stock пул мал (190): Codex research остаётся основным инструментом;
   экономический смысл Phase 6 — снижение стоимости повторных research
   (family-repeatability показала 7/9 applied) и пред-модерационная
   подсветка, а не замена research.
3. Главный блокер покрытия — taxonomy gaps: 22% abstention в batch-50.
   До расширения rules любые массовые прогоны будут упираться в те же
   11–12 типов; решения по options — отдельными ADR до массовых запусков
   (первый, ADR-0011 динамометрические ключи, выполнен 2026-07-21).

### Current-state corpus (amendment 2026-07-21, P0.1)

Training corpus НЕ равен «всем applied changes». После ADR-0011 remediation
товары 12957/12959 имеют по два applied changes с разными labels
(`klyuchi-gaechnye` исторически, `dinamometricheskie-klyuchi` текущий).
Контракт корпуса:

1. Одна строка на `product_id`.
2. Текущий label — из актуального tool_type PAV (источник истины).
3. Provenance — последний applied change, чей `after_value` совпадает с
   текущим PAV (option_id/option_slug).
4. В строке: `change_id`, PAV ID, source/confidence, `applied_at`, snapshot
   фактов (name/original_name/brand/source_group/article) и `facts_hash`.
5. Публикуются счётчики: raw applied changes, distinct products, размер
   current-label corpus, historical-label collisions.
6. Duplicate product IDs и conflicting current labels запрещены schema- и
   regression-тестами.

Ожидаемые счётчики на 2026-07-21: raw applied = 56 (54 Phase 5 + 2
remediation), distinct products = 54, current-label corpus = 54,
historical-label collisions = 2 (12957/12959). Это baseline observations,
перед Task 4 они перепроверяются свежим SELECT.

## Предлагаемый контур (proposal-only / shadow)

### Этап 6.0 — shadow rules engine (без записей)

- Извлечь кандидатные правила из current-state corpus: brand/series +
  keyword + source_group → option_slug; зафиксировать ruleset в репозитории
  как versioned JSON (`data/catalog_processing_rules/tool_type.v1.json`),
  с версией и каноническим `ruleset_hash` (поля уже есть в `CatalogChange`).
  Rule mining — **analyst-curated** (amendment 2026-07-21, P1.3): каждое
  правило сопровождается ручным обоснованием в derivation report;
  детерминированный auto-miner не обещается.
- Семантические ограничения candidate rules (amendment 2026-07-21, P0.2):
  минимум **два непустых измерения** match; минимум **два уникальных
  положительных product ID** в `derived_from`; нормализованные значения
  непусты (keyword ≥ 3 символов после normalize) и уникальны внутри
  измерения; keyword-only правило допустимо только как tier
  `shadow_regression`; каждое candidate-правило имеет минимум одну
  привязанную к нему negative fixture; явно дублирующие predicates —
  validation error.
- Negative fixtures — **rule-scoped** (amendment 2026-07-21, P1.1):
  `fixture_ref`, `rule_refs`, frozen facts, ожидаемый результат для
  указанных правил. Fixture не обязана быть negative для несвязанных
  правил. Проверка `len(fixtures) >= len(candidate)` покрытием не считается.
- Title matching contract (amendment 2026-07-21, P1.2): раздельные
  измерения `original_name_keywords_any` и `name_keywords_any`; в
  verdict/evidence сохраняется, какое поле и какой keyword вызвали match;
  документированные границы токенов/фраз, нормализация пробелов и
  разделителей, минимальная длина keyword.
- Прогнать правила **только вычислительно** над in-stock пулом и над
  полным untyped пулом без stock-фильтра: coverage, коллизии правил между
  собой, доля совпадений с существующими Codex-результатами.
- Replay на applied-корпусе — **только regression-check**, не gate:
  правила выведены из этих же товаров, поэтому replay не доказывает
  precision (training leakage).
- Gate-выборка (amendment 2026-07-21, P0.3): собрать **≥ 100 rule
  predictions на товарах вне applied-корпуса** (независимая выборка из
  пула) и проверить все вручную. Артефакты:
  - `gate_sample.json` (versioned): на строку — product ID, frozen
    name/original_name/brand/source_group/article, `facts_hash`, predicted
    option slug, все rule refs, `ruleset_hash`, `matcher_version`,
    `taxonomy_hash`, sampling seed, pool, `pool_filter_version`;
  - `gate_labels.json` (versioned): на строку — `correct | incorrect |
    identity_problem | taxonomy_gap | unverifiable`, corrected slug (если
    применимо), reviewer ID, `reviewed_at`, reason/evidence, hash исходного
    gate sample.
  Gate не завершён, пока все строки не получили финальный label
  `correct`/`incorrect`; `unverifiable` НЕ исключается из знаменателя
  молча. Validator подтверждает: sample не пересекается с training corpus,
  product IDs уникальны, при накоплении нет повторов, все labels относятся
  к одному `ruleset_hash`/`matcher_version`, label-файл ссылается на hash
  исходного sample.
- Метрики shadow (amendment 2026-07-21): coverage по пулу и по каждому
  правилу (raw/prediction/collision/same-slug-multi hits, отдельно по
  tiers), agreement с Codex, precision на независимой выборке,
  `rewrite_attempts=0`, доля predictions в eligible universe, список
  коллизий, regression replay на applied-корпусе.
- Версионирование отчёта (amendment 2026-07-21, P1.4/P1.5): report содержит
  `report_schema_version`, `matcher_version`, code SHA, pool-filter version,
  input universe hash, command arguments, start/end timestamps; файл —
  уникальное имя (timestamp), атомарная запись (tmp + `os.replace`), права
  `0600`, отказ от перезаписи без `--force`, SHA-256 файла и канонический
  hash содержимого. Чтение universe — в транзакции
  `REPEATABLE READ READ ONLY` (P1.6).
- Артефакт: read-only отчёт + versioned ruleset JSON в репозитории, без
  кода записи в каталог.

### Этап 6.1 — rules как proposals (только после gate 6.0)

- `kind=rules` run через существующий `catalog_queue_create`: правила
  создают **только proposed** `CatalogChange` (importer уже блокирует apply
  без модерации); moderation и apply — теми же сервисами, что и в Phase 5.
  В evidence рядом с `ruleset_hash` попадают `matcher_version` и code SHA.
- Первый run — малый явный список (≤ 50) из shadow-hits с наивысшей
  уверенностью; batch-контроль идемпотентности как в batch-50.
- Gate включения 6.1 (все условия обязательны):
  - **≥ 100 независимо проверенных predictions суммарно** (выборка вне
    applied-корпуса; накопление допустимо по нескольким shadow-прогонам);
  - **precision ≥ 99%** (цель 100%) на этой выборке — по наблюдаемой
    precision (см. «Gate-метрики» ниже);
  - **0 конфликтующих rule hits** (правила → разные slugs);
  - **0 попыток перезаписать существующий `tool_type`**;
  - **все predictions проверены человеком**.

### Этап 6.2 — Codex research для длинного хвоста

- Товары без rule-hit идут в research-блоки по протоколу batch-50
  (identity gate, source policy, allowed options, dry-run → commit →
  moderation → apply).
- Правила пополняются только из applied-результатов (human-in-the-loop
  rule mining), без автогенерации правил из непроверенных данных.

## Non-scope (явно)

- auto-apply любых proposals;
- массовый запуск по полному untyped пулу без отдельного решения;
- создание/изменение taxonomy options в этом плане (только ADR-список
  gap-типов: компрессометры, воронки, ледоступы, ESD-браслеты, FastClip,
  лодочные моторы, мерные ёмкости, нагрузочные вилки, досмотровые зеркала,
  отсосы припоя; динамометрические ключи закрыты ADR-0011);
- изменение `Product`/PAV вне существующих сервисов moderation/apply;
- вызов Codex из HTTP/Celery — контур остаётся по явной команде пользователя.

## Gate-метрики Phase 6 (утверждено 2026-07-20; precision уточнён 2026-07-21)

- precision на независимой выборке: **минимум 99%, цель 100%** — до
  включения 6.1. Семантика (P0.4): gate использует **наблюдаемую**
  precision `correct / all_final_labels >= 99%` (знаменатель — все строки
  с финальными labels, `unverifiable` не исключается молча).
  Статистическая нижняя доверительная граница считается отдельно **per
  rule** и используется только для последующей калибровки confidence
  (решение 2): при n=100 и 100/100 односторонняя 95% Clopper-Pearson
  ≈ 97.0%, поэтому aggregate gate по observed precision НЕ продвигает
  автоматически правило с малой собственной выборкой — правила со слабой
  per-rule поддержкой остаются shadow-only до отдельного решения. Если
  когда-либо потребуется lower bound ≥ 99%, минимальный размер выборки
  пересчитывается (для zero-failure one-sided 95% это n ≈ 300).
- rules proposal precision после модерации: **≥ 99%** на первых двух runs,
  иначе откат в shadow;
- независимая проверка: **≥ 100 predictions, все — человеком**;
- **0 конфликтующих rule hits; 0 попыток перезаписи существующего
  `tool_type`** (`rewrite_attempts=0`);
- moderator acceptance ≥ 90%;
- 0 прямых/неподтверждённых записей; baseline-конфликты блокируются
  механизмом `baseline_hash` + provenance (подтверждено контрактными
  тестами и pre-check каждого apply);
- coverage отчёт по пулу после каждого ruleset-релиза.

## Решения по открытым вопросам (утверждены 2026-07-20; дополнены 2026-07-21)

1. **Ruleset — versioned JSON в репозитории**, не таблица БД. Отдельный
   контракт `data/catalog_processing_rules/tool_type.v1.json`; legacy
   `data/tool_type_rules.json` не перегружать. В БД сохраняются `rule_ref`
   и канонический `ruleset_hash`; с 2026-07-21 в evidence добавляются
   `matcher_version` и code SHA (для Phase 6.1).
2. **Confidence — эмпирический** по независимой проверке, с учётом размера
   выборки (консервативная нижняя граница оценки per rule, максимум 99); не
   фиксированный по типу правила. Confidence **никогда** не разрешает
   auto-apply. Aggregate gate precision (observed) и per-rule lower bound —
   разные показатели, см. «Gate-метрики».
3. **Коллизии**:
   - несколько правил → один slug: одно предложение, все rule refs
     сохраняются в evidence;
   - правила → разные slugs: abstention/collision, предложение не
     создаётся;
   - конфликт с Codex proposal: второй change не создаётся, требуется
     ручное решение;
   - существующий `tool_type`: товар исключается, перезапись запрещена.
4. **Первый ruleset** — только точные conjunctive family/brand-series
   правила с обязательными rule-scoped negative fixtures (семантические
   ограничения — в §6.0). Общие keyword-only правила остаются
   shadow-регрессией: выборка 4/4 из batch-50 слишком мала.
5. **Taxonomy ADR** — первым: динамометрические ключи. **Выполнен**:
   ADR-0011 принят, option `dinamometricheskie-klyuchi` материализована
   (327 → 328), remediation 12957/12959 завершена 2026-07-21. Taxonomy
   changeset остаётся отдельным от Phase 6.
