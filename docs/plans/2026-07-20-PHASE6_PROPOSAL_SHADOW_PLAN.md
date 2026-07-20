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
непустой `article`, `content_locked=False`, без `tool_type` (`value_option`
не NULL).

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
   15 batch-20 + 4 пилота).
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
  keyword + source_group → option_slug; зафиксировать ruleset с версией и
  `ruleset_hash` (поля уже есть в `CatalogChange`).
- Прогнать правила **только вычислительно** над in-stock пулом (190) и над
  8 403 без stock-фильтра: считать coverage, коллизии правил между собой,
  долю совпадений с существующими Codex-результатами (replay против
  batch-20/50 export → сравнение с фактическими applied).
- Метрики shadow: coverage по пулу, agreement с Codex, precision replay на
  applied-корпусе (цель ≥ 98% до любого proposal-mode), список коллизий.
- Артефакт: read-only отчёт + versioned ruleset JSON в репозитории (docs/
  или config/), без кода записи в каталог.

### Этап 6.1 — rules как proposals (только после gate 6.0)

- `kind=rules` run через существующий `catalog_queue_create`: правила
  создают **только proposed** `CatalogChange` (importer уже блокирует apply
  без модерации); moderation и apply — теми же сервисами, что и в Phase 5.
- Первый run — малый явный список (≤ 50) из shadow-hits с наивысшей
  уверенностью; batch-контроль идемпотентности как в batch-50.
- Gate включения: shadow precision ≥ 98% на replay, 0 коллизий с
  противоречиями, moderator workload приемлем (предложения с confidence
  калибровкой: auto-propose только при single-rule hit).

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

## Gate-метрики Phase 6 (предложение)

- shadow replay precision на applied-корпусе: ≥ 98% до включения 6.1;
- rules proposal precision после модерации: ≥ 98% на первых двух runs,
  иначе откат в shadow;
- moderator acceptance ≥ 90%;
- 0 прямых/неподтверждённых записей; 100% baseline-конфликтов блокируются
  (механизм уже есть — `baseline_hash` + provenance);
- coverage отчёт по пулу после каждого ruleset-релиза.

## Открытые вопросы (нужны решения до 6.0)

1. Формат ruleset: отдельный versioned JSON в `config/` vs таблица в БД
   (roadmap V2 предполагает файловый контракт — уточнить).
2. Калибровка confidence правил: фиксированная по типу правила vs
   эмпирическая из replay.
3. Политика коллизий rule vs rule и rule vs существующий Codex proposal.
4. Состав первого ruleset: только brand/series-правила из applied-корпуса
   или также keyword-правила batch-50 (покрытие 1/190 — ценность низкая).
5. Очередь taxonomy ADR: динамометрические ключи — первый кандидат
   (3 in-stock + 2 abstention + расхождение с Phase 5 прецедентом).
