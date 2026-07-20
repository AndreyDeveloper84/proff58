# Phase 6 — proposal-only / shadow plan: детерминированные правила tool_type

Статус: **proposal** (2026-07-20). Подготовлен по разрешению после закрытия
Phase 5 с risk exception. Документ — только план и read-only анализ:
**никаких изменений staging, taxonomy, массовых запусков и auto-apply**.
Первый live run, создание options и merge реализации — только по отдельным
решениям.

Базовые документы: роадмап `2026-07-17-CATALOG_RESEARCH_QUEUE_ROADMAP_V2.md`
(§18 Phase 6), закрытие batch-50
`docs/catalog/phase5-batch50-closure-report.md`.

## Цель Phase 6 (по роадмапу)

Детерминированные массовые правила: brand + model series, устойчивые
слова/фразы в названии, исходная категория 1С, артикул/префикс, существующие
атрибуты. Правила работают **только как proposals с модерацией**; Codex
research остаётся для неоднозначного длинного хвоста. Auto-apply не
вводится никогда в рамках этого плана.

## Read-only impact analysis (staging, 2026-07-20; только SELECT)

Критерии пула = `catalog_queue_create`: `is_active`, `available_quantity > 0`,
непустой `article`, `content_locked=False`, без заполненного `tool_type`
(NOT EXISTS PAV с `attribute=tool_type` и `value_option IS NOT NULL`).

| Показатель | Значение |
|---|---|
| active товаров всего | 22 156 |
| без `tool_type` (весь каталог, без stock-фильтра) | 8 403 |
| **in-stock пул (критерии batch-50)** | **190** |
| shadow-hits валидированных правил | **1/190** (`krep-shplinty` — «шплинт»; `puskovye-provoda` — 0) |

Частота taxonomy-gap типов batch-50 в in-stock пуле: динамометрический ключ —
**3** (системный gap: плюс 2 abstention в самом batch-50 и прецедент Phase 5),
воронка — 2, FastClip — 2, компрессометр 1, ледоступы 1, ESD-браслет 1,
лодочный мотор / мерная ёмкость / отсос припоя — 0.

Top source_groups пула: Электроинструмент 26, Слесарно-столярный 24,
Хозтовары/сад 18, Запчасти 14, СИЗ 13, Наборы инструмента 13,
Аккумуляторный 12, Автомобильный 10, Измерительный 8.

### Выводы из анализа

1. Детерминированные правила, валидированные на batch-50, покрывают
   **~0,5%** in-stock пула — keyword-правила дают малый вклад; массовый
   выигрыш Phase 6 возможен только за счёт системных family/brand-series
   правил, которые ещё предстоит вывести из applied-корпуса (35 batch-50 +
   15 batch-20 + 4 пилота). Важно: applied-корпус — это training data;
   доказательство precision на тех же товарах было бы training leakage
   (см. gate 6.1 — независимая выборка ≥ 100 predictions).
2. In-stock пул мал (190): Codex research остаётся основным инструментом;
   экономический смысл Phase 6 — снижение стоимости повторных research
   (family-repeatability показала 7/9 applied) и пред-модерационная
   подсветка, а не замена research.
3. Главный блокер покрытия — taxonomy gaps: 22% abstention в batch-50.
   До расширения rules любые массовые прогоны будут упираться в те же
   11–12 типов; решения по options (прежде всего «динамометрические ключи»)
   — отдельными ADR до массовых запусков.

## Предлагаемый контур (proposal-only / shadow)

### Этап 6.0 — shadow rules engine (без записей)

- Извлечь кандидатные правила из applied-корпуса (54 товара): brand/series +
  keyword + source_group → option_slug; зафиксировать ruleset в репозитории
  как versioned JSON (`data/catalog_processing_rules/tool_type.v1.json`),
  с версией и каноническим `ruleset_hash` (поля уже есть в `CatalogChange`).
- Прогнать правила **только вычислительно** над in-stock пулом (190) и над
  8 403 без stock-фильтра: считать coverage, коллизии правил между собой,
  долю совпадений с существующими Codex-результатами.
- Replay на applied-корпусе — **только regression-check**, не gate:
  правила выведены из этих же товаров, поэтому replay не доказывает
  precision (training leakage).
- Gate-выборка: собрать **≥ 100 rule predictions на товарах вне
  applied-корпуса** (независимая выборка из пула) и проверить все вручную.
- Метрики shadow: coverage по пулу, agreement с Codex, precision на
  независимой выборке (минимум **99%**, цель **100%**), список коллизий,
  regression replay на applied-корпусе.
- Артефакт: read-only отчёт + versioned ruleset JSON в репозитории, без
  кода записи в каталог.

### Этап 6.1 — rules как proposals (только после gate 6.0)

- `kind=rules` run через существующий `catalog_queue_create`: правила
  создают **только proposed** `CatalogChange` (importer уже блокирует apply
  без модерации); moderation и apply — теми же сервисами, что и в Phase 5.
- Первый run — малый явный список (≤ 50) из shadow-hits с наивысшей
  уверенностью; batch-контроль идемпотентности как в batch-50.
- Gate включения 6.1 (все условия обязательны):
  - **≥ 100 независимо проверенных predictions суммарно** (выборка вне
    applied-корпуса; накопление допустимо по нескольким shadow-прогонам);
  - **precision ≥ 99%** (цель 100%) на этой выборке;
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
- массовый запуск по 8 403 без отдельного решения;
- создание/изменение taxonomy options в этом плане (только ADR-список
  gap-типов: динамометрические ключи, компрессометры, воронки, ледоступы,
  ESD-браслеты, FastClip, лодочные моторы, мерные ёмкости, нагрузочные
  вилки, досмотровые зеркала, отсосы припоя);
- изменение `Product`/PAV вне существующих сервисов moderation/apply;
- вызов Codex из HTTP/Celery — контур остаётся по явной команде пользователя.

## Gate-метрики Phase 6 (утверждено 2026-07-20)

- precision на независимой выборке: **минимум 99%, цель 100%** — до
  включения 6.1;
- rules proposal precision после модерации: **≥ 99%** на первых двух runs,
  иначе откат в shadow;
- независимая проверка: **≥ 100 predictions, все — человеком**;
- **0 конфликтующих rule hits; 0 попыток перезаписи существующего
  `tool_type`**;
- moderator acceptance ≥ 90%;
- 0 прямых/неподтверждённых записей; baseline-конфликты блокируются
  механизмом `baseline_hash` + provenance (подтверждено контрактными
  тестами и pre-check каждого apply);
- coverage отчёт по пулу после каждого ruleset-релиза.

## Решения по открытым вопросам (утверждены 2026-07-20)

1. **Ruleset — versioned JSON в репозитории**, не таблица БД. Отдельный
   контракт `data/catalog_processing_rules/tool_type.v1.json`; legacy
   `data/tool_type_rules.json` не перегружать. В БД сохраняются `rule_ref`
   и канонический `ruleset_hash`.
2. **Confidence — эмпирический** по независимой проверке, с учётом размера
   выборки (консервативная нижняя граница оценки, максимум 99); не
   фиксированный по типу правила. Confidence **никогда** не разрешает
   auto-apply.
3. **Коллизии**:
   - несколько правил → один slug: одно предложение, все rule refs
     сохраняются в evidence;
   - правила → разные slugs: abstention/collision, предложение не
     создаётся;
   - конфликт с Codex proposal: второй change не создаётся, требуется
     ручное решение;
   - существующий `tool_type`: товар исключается, перезапись запрещена.
4. **Первый ruleset** — только точные conjunctive family/brand-series
   правила с обязательными negative fixtures. Общие keyword-only правила
   пока остаются shadow-регрессией: выборка 4/4 из batch-50 слишком мала.
5. **Taxonomy ADR** — первым: динамометрические ключи. ADR обязан явно
   решить их отношение к `klyuchi-gaechnye` и динамометрическим отвёрткам.
   Taxonomy changeset остаётся отдельным от Phase 6.
