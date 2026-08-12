# Review: Phase 6.0 Shadow Rules Engine

Дата ревью: 2026-07-21.

Статус: **требуются amendments до продолжения реализации**.

## Scope ревью

Проверены полностью:

- `docs/plans/2026-07-20-PHASE6_PROPOSAL_SHADOW_PLAN.md`;
- `docs/plans/2026-07-21-PHASE6_0_SHADOW_RULES_IMPLEMENTATION.md`.

Планы сопоставлены с:

- `docs/plans/2026-07-17-CATALOG_RESEARCH_QUEUE_ROADMAP_V2.md`;
- `docs/catalog/phase5-batch50-closure-report.md`;
- текущими моделями и processing-контрактами `apps/catalog`;
- уже начатой реализацией в ветке `feat/phase6-shadow-rules`.

На момент ревью в ветке уже присутствовали три коммита:

- `6c6a039` — schema + loader;
- `7e97169` — matching и collision semantics;
- `cb781de` — read-only команда `catalog_rules_shadow`.

Targeted suite:

```text
17 passed
```

Зелёный targeted suite подтверждает реализованные примеры, но не закрывает
контрактные проблемы ниже.

## Итоговый вердикт

Архитектурное направление правильное, однако передавать текущий план агенту для
Task 4/Task 5 без поправок нельзя. Сначала необходимо закрыть четыре P0-блокера,
затем усилить уже реализованные Tasks 1–3.

Task 4 (извлечение applied-корпуса и создание реального ruleset) до этого
начинать нельзя. Staging shadow-прогон также остаётся отдельным stop-gate.

## P0 — блокеры

### P0.1. Applied-корпус извлекается из истории changes, а не из текущей истины

Implementation plan предлагает:

```python
CatalogChange.objects.filter(status="applied", target_kind="tool_type")
```

и ожидает 54 записи.

После ADR-0011 это ожидание неверно:

- исходный applied-корпус содержал 54 applied changes;
- remediation добавила два applied changes для существующих товаров 12957 и
  12959;
- исходные Phase 5 changes для этих товаров сохранили статус `applied`;
- сырой запрос теперь возвращает исторические и текущие labels для одних и тех
  же product ID.

Риск: ruleset одновременно обучится на старом `klyuchi-gaechnye` и текущем
`dinamometricheskie-klyuchi`.

Обязательная поправка:

1. Строить корпус с одной строкой на `product_id`.
2. Текущий label брать из актуального `tool_type` PAV.
3. Привязывать последний applied change, `after_value` которого совпадает с
   текущим PAV.
4. Сохранять `change_id`, PAV ID, source/confidence, `applied_at`, snapshot
   фактов и snapshot hash.
5. Отдельно публиковать:
   - число raw applied changes;
   - число distinct products;
   - размер current-label corpus;
   - historical-label collisions.
6. Запретить duplicate product IDs и conflicting current labels schema- и
   regression-тестами.

Ожидаемое состояние после ADR-0011: raw applied changes больше размера
уникального current-state корпуса; жёсткое ожидание `54 changes` использовать
нельзя.

### P0.2. Контракт conjunctive candidate rules не обеспечен

Основной план разрешает первый candidate ruleset только как точные
family/brand-series правила с несколькими измерениями. Текущие schema и loader
при этом допускают:

- keyword-only правило;
- автоматический tier `candidate`;
- пустой `derived_from`;
- derivation из одного товара;
- пустые после нормализации значения;
- дубликаты в match arrays.

Базовая тестовая фикстура сейчас сама является keyword-only candidate.

Обязательная semantic validation:

- `candidate` содержит минимум два непустых измерения match;
- keyword-only правило допустимо только как `shadow_regression`;
- `candidate.derived_from` содержит минимум два уникальных положительных
  product ID;
- нормализованные значения непусты и уникальны;
- каждый candidate имеет хотя бы одну привязанную к нему negative fixture;
- явно дублирующие predicates отклоняются либо выдаются как validation error.

Нужны regression-тесты на каждый запрет.

### P0.3. Gate sample не является проверяемым audit-артефактом

Команда сохраняет в `sample` только product IDs. Этого недостаточно для ручной
проверки, воспроизводимости и доказательства precision.

Нужны два versioned-артефакта.

#### `gate_sample.json`

Для каждой prediction:

- product ID;
- frozen `name`, `original_name`, `brand`, `source_group`, `article`;
- product snapshot hash;
- predicted option slug;
- все rule refs;
- ruleset hash;
- matcher version;
- taxonomy hash;
- sampling seed;
- pool и pool-filter version.

#### `gate_labels.json`

Для каждой строки sample:

- `correct | incorrect | identity_problem | taxonomy_gap | unverifiable`;
- corrected slug, если применимо;
- reviewer ID;
- `reviewed_at`;
- reason/evidence;
- hash исходного gate sample.

Gate нельзя считать завершённым, пока все строки не получили окончательное
решение `correct` или `incorrect`. `Unverifiable` нельзя молча исключать из
denominator.

Команда или отдельный validator должны подтверждать:

- sample не пересекается с training corpus;
- product IDs уникальны;
- при накоплении отсутствуют повторы;
- все labels относятся к одному замороженному `ruleset_hash` и
  `matcher_version`;
- label-файл соответствует исходному sample hash.

### P0.4. Не определена статистическая семантика precision >= 99%

В документах одновременно используются:

- gate precision >= 99% на выборке >= 100 predictions;
- консервативная нижняя граница оценки для confidence.

Это разные показатели. При 100/100 наблюдаемая precision равна 100%, но
консервативная нижняя доверительная граница заметно ниже 99%. Поэтому выборки
100 недостаточно, если gate должен применяться к confidence lower bound.

Рекомендуемый контракт:

- gate 6.0 использует наблюдаемую precision:
  `correct / all_final_labels >= 99%`;
- статистическая lower bound рассчитывается отдельно для каждого правила и
  используется при последующей калибровке confidence;
- публикуются aggregate и per-rule numerator/denominator;
- aggregate gate не разрешает автоматически продвигать правило с малой или
  слабой собственной выборкой;
- правила с недостаточной per-rule поддержкой остаются shadow-only до
  отдельного решения.

Если требуется именно lower bound >= 99%, минимальный размер выборки должен
быть пересчитан и будет значительно больше 100.

## P1 — существенные замечания

### P1.1. Negative fixtures не привязаны к конкретным rules

Сейчас fixtures — общий список, а проверка требует, чтобы каждая fixture не
совпала ни с одним правилом. Это неверно: товар может быть отрицательным
примером для одного правила и корректным положительным примером для другого.

Нужно добавить:

- `fixture_ref`;
- `rule_refs` или один `rule_ref`;
- frozen product facts либо product ID + snapshot hash;
- ожидаемый результат для указанного правила;
- проверку, что каждый candidate rule имеет минимум одну собственную fixture.

Проверка вида `len(fixtures) >= len(candidate_rules)` не доказывает покрытие
каждого правила.

### P1.2. Семантика title matching неоднозначна

Текущий matcher использует `original_name`, а `name` только как fallback. Это
опасно после обнаруженного товара 35610, где исходное имя содержало неверную
модель.

Нужно выбрать и зафиксировать одно из решений:

1. Раздельные условия `original_name_keywords_*` и `name_keywords_*`.
2. Явная политика согласия двух полей.

В verdict/evidence обязательно сохранять, какое поле и какое условие вызвали
match.

Простая проверка подстроки после `lower()` и `ё -> е` недостаточна для
model-series правил. Требуются документированные границы токенов/фраз,
нормализация пробелов и разделителей и ограничения на слишком короткие
keywords.

### P1.3. Rule mining объявлен детерминированным, но недоопределён

План не задаёт:

- tokenization;
- stop-word список;
- tie-breaking;
- минимальный article prefix;
- порядок выбора измерений;
- процедуру выбора negative fixture.

Допустимы два честных варианта:

1. Реализовать отдельный детерминированный и тестируемый candidate-miner.
2. Обозначить процесс как analyst-curated и сохранять derivation report с
   ручным обоснованием каждого правила.

Для первого небольшого ruleset рекомендуется analyst-curated подход. Он лучше
соответствует high-precision и human-in-the-loop ограничениям.

### P1.4. Ruleset hash не идентифицирует исполняемую семантику

Один JSON ruleset при изменении Python matcher может дать другой результат, а
`ruleset_hash` останется прежним.

В отчёт и provenance нужно добавить:

- `report_schema_version`;
- `matcher_version`;
- code SHA;
- pool-filter version;
- input universe hash;
- command arguments;
- start/end timestamps;
- candidate/regression rule counts.

Для Phase 6.1 matcher version и code SHA должны попадать в evidence рядом с
`ruleset_hash`.

### P1.5. Отчёты перезаписываются и пишутся неатомарно

Default filename зависит только от ruleset hash и pool, поэтому повторный
прогон перезапишет предыдущий audit-артефакт.

Нужно:

- уникальное имя с timestamp/report ID;
- запись во временный файл и атомарный `os.replace`;
- права `0600`;
- отказ от перезаписи существующего пути без явного `--force`;
- SHA-256 итогового файла;
- отдельный канонический hash содержимого отчёта.

### P1.6. Нет консистентного snapshot чтения

Команда делает отдельные `count()` и последующую итерацию. Параллельный импорт
может изменить universe внутри одного отчёта.

Для PostgreSQL shadow-read следует выполнять в транзакции:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
```

Allowed options нужно прочитать один раз и использовать одновременно для
validation и `taxonomy_hash`.

### P1.7. Pool contract расходится между документом и кодом

Основной план утверждает, что pool criteria равны `catalog_queue_create`.
Фактический `catalog_queue_create` не добавляет обязательные фильтры
`is_active`, `content_locked=False` и непустой article. Implementation plan уже
называет shadow pool более строгим.

Нужно исправить основной документ и определить:

- whitespace-only article считается пустым;
- `pool.size` означает untyped eligible pool;
- typed eligible universe публикуется отдельно;
- `excluded_existing_tool_type` не равен rewrite attempts;
- отдельный `rewrite_attempts` обязан оставаться равным нулю.

Числа 190, 8 403 и PAV 60 896 являются baseline observations на конкретный
момент, а не вечными assertions. Staging-проверка должна сравнивать pre/post
снимки текущего запуска.

### P1.8. Метрики команды неполны

Добавить:

- raw hits по каждому rule;
- prediction hits;
- collision hits;
- same-slug multi-rule hits;
- regression collisions;
- coverage по каждому rule;
- долю predictions в eligible universe;
- `rewrite_attempts=0`;
- отдельные метрики candidate и shadow-regression tiers.

### P1.9. Недостаточное test coverage

Обязательные дополнительные тесты:

- keyword-only не может быть candidate;
- candidate требует минимум два dimensions и два `derived_from`;
- fixture привязана к конкретному rule;
- duplicate и empty normalized values;
- invalid JSON, missing file, empty ruleset;
- inactive/locked/out-of-stock products;
- blank и whitespace-only article;
- различие `all` и `in-stock`;
- collision полностью отражается в отчёте;
- sample исключает training corpus;
- повторный запуск не перезаписывает artefact;
- atomic output и mode `0600`;
- corpus product IDs уникальны;
- historical/current label conflict после ADR-0011;
- DB rows не создаются и не обновляются;
- report schema и hashes;
- consistent snapshot при конкурентном изменении данных.

## Сильные стороны текущего плана

Следующие решения следует сохранить:

- versioned ruleset отделён от legacy taxonomy manifest;
- Phase 6.0 не создаёт `CatalogChange` и не изменяет каталог;
- Phase 6.1 отделена явным gate;
- auto-apply отсутствует;
- replay признан regression-check, а не доказательством precision;
- conflicting slugs приводят к collision/abstention;
- существующий `tool_type` исключается;
- confidence не назначается до независимой проверки;
- staging и merge разделены stop-gates;
- read-only команда не требует включения catalog processing feature flag;
- Codex research остаётся для длинного хвоста.

## Обязательная очередь реализации

### Шаг 1. Amendment документов

До продолжения кода исправить оба Phase 6 документа:

- current-state corpus вместо всех historical applied changes;
- semantic constraints candidate rules;
- versioned sample/label contract;
- точное определение precision/confidence;
- исправленный pool contract;
- rule-scoped negative fixtures;
- статус ADR-0011 и завершённой remediation.

### Шаг 2. Усиление Tasks 1–3

В текущей ветке исправить:

- JSON Schema и semantic validator;
- title/token matching contract;
- negative fixture mapping;
- matcher/report versioning;
- consistent read snapshot;
- unique atomic output;
- gate sample artifact;
- полный набор regression-тестов.

### Шаг 3. Локальная проверка

```powershell
.\.venv\Scripts\python.exe -m pytest `
  apps/catalog/tests/test_rules_engine.py `
  apps/catalog/tests/test_rules_shadow_command.py -q

.\.venv\Scripts\python.exe -m pytest apps/catalog -q
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m ruff check apps/catalog
.\.venv\Scripts\python.exe -m black --check apps/catalog
```

Перед PR также обязателен полный repository test suite в CI-equivalent
окружении.

### Шаг 4. Task 4 — только после закрытия P0

По отдельной read-only staging-авторизации:

1. Извлечь current-state corpus.
2. Зафиксировать raw/history/current counters.
3. Подготовить derivation report.
4. Провести human review каждого candidate rule и negative fixtures.
5. Создать versioned ruleset и corpus fixture.
6. Выполнить replay только как regression-check.

### Шаг 5. Task 5 — отдельный checkpoint

Только после merge и отдельного разрешения на staging:

- read-only shadow-run;
- feature flag остаётся False;
- pre/post invariants;
- gate sample artifact;
- ручная разметка отдельным этапом;
- Phase 6.1 не начинается без отдельного решения по gate.

## Handoff constraints для агента

- Не начинать Task 4 до закрытия P0.1–P0.4.
- Не выполнять staging SELECT без отдельного разрешения.
- Не создавать live catalog runs.
- Не включать feature flag.
- Не реализовывать Phase 6.1 и auto-apply.
- Не использовать `git checkout -- .`, `git add .` и широкие cleanup-команды.
- Не трогать чужие modified/untracked файлы рабочего дерева.
- Коммиты делать только с явно перечисленными путями.

## Документальные follow-ups

- `docs/plans/2026-07-20-PHASE6_PROPOSAL_SHADOW_PLAN.md` всё ещё имеет статус
  `proposal`, хотя решения 1–5 уже утверждены.
- `docs/adr/ADR-0011-dinamometricheskie-klyuchi.md` всё ещё помечен как
  «предложено», хотя option материализована и remediation завершена.
- Основной Phase 6 plan должен явно отметить, что existing attributes не входят
  в первый matcher slice и отложены на следующую версию ruleset.

## Review evidence

В рамках ревью выполнено:

```text
pytest apps/catalog/tests/test_rules_engine.py
       apps/catalog/tests/test_rules_shadow_command.py -q

17 passed
```

Код и существующие планы в ходе ревью не изменялись. Этот документ является
единственным созданным артефактом ревью.
