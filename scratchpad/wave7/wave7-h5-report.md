# Wave 7.1 / H5 — reverse migration hardening. Протокол стадии

**Дата:** 2026-07-27. **Ветка:** `dev`. **Вход:** `origin/dev = b6361d6` (H4 принят и запушен,
CI зелёный). **Статус: ВЫПОЛНЕНА.**

---

## 1. Итог одной строкой

У контура распознавания `tool_type` появился обратный путь: применённые предложения
откатываются командой по паре снимков с conflict-guard'ом и post-audit, а понижение
версии словаря `N → N-1` имеет read-only план, который fail-closed блокирует любой
неоднозначный откат. Процедура проверена 81 тестом, 12 ключевых guard'ов подтверждены
обеими сторонами (мутацией), end-to-end прогон выполнен на реальном каноническом
манифесте из 328 опций.

## 2. Зачем стадия существовала

До H5 контур был односторонним.

- **Словарь.** Форвардный путь — манифест плюс fail-closed seed `load_tool_types`,
  который создаёт недостающие опции и **никогда ничего не удаляет**. Если опция
  исчезала из манифеста, товары оставались висеть на записи, которой в словаре больше
  нет, и обнаружить это можно было только `catalog_taxonomy_reconcile` постфактум.
- **Применённые предложения.** Откат существовал только в виде текстовой политики
  (`docs/catalog/operations/rollback.md`: «зафиксируйте rollback-map») и pg_dump.
  pg_dump — инструмент грубый: он откатывает всю БД, включая чужие изменения,
  случившиеся после записи.

Стадия закрывает обе дыры **проверяемой** процедурой, а не документом: откат
исполняется командой, идемпотентен, отказывается работать поверх изменившегося
baseline и подтверждается post-audit.

## 3. Коммиты — **в `origin/dev`**

```
28c7bef  docs(plans): решение владельца по option_uid
81def09  docs(plans): статус H5 и открытый вопрос по option_uid
664a4f0  docs(catalog): процедура reverse-migration tool_type и политика отката
de2d796  feat(catalog): reverse-map манифеста N → N-1 и команда понижения версии
fcf7a45  feat(catalog): контур отката применённого tool_type
```

Запушено владельцем 2026-07-27. Коммиты **перевыпущены ребейзом** поверх merge
PR #594 (`592e96c`), поэтому SHA сменились: прежние локальные `db358c2`, `39804c2`,
`4ef134e`, `2b9e33c`, `bbb540c` больше не актуальны. Сверено живой командой:
`origin/dev = HEAD = 28c7bef`, ahead/behind `0 0`, рабочее дерево по tracked-файлам
чистое. Тесты H5 перепроверены **на ребейзнутом дереве**: 81 passed.

## 4. Архитектура

### 4.1 Два контура, один исполнитель записи

| Контур | Модуль | Команды |
|---|---|---|
| Откат применённого `tool_type` | `apps/catalog/tool_type_rollback.py` | `catalog_tool_type_snapshot`, `catalog_tool_type_rollback` |
| Понижение версии словаря `N → N-1` | `apps/catalog/taxonomy_reverse.py` | `catalog_taxonomy_downgrade` |

Ключевое архитектурное решение: **понижение версии не имеет собственной ветки
записи**. Перенос товаров с исчезающих опций оно исполняет через контур отката
(`snapshot_pair_for_remap` → `plan_rollback` → `apply_rollback`). Поэтому у понижения
ровно та же семантика идемпотентности, конфликта и атомарности — второй, менее
строгой реализации записи не существует.

### 4.2 Почему пара снимков, а не один

Откат исполняется по **паре**: `--from` (состояние, ожидаемое в БД сейчас) и `--to`
(цель отката).

| live | решение | почему |
|---|---|---|
| `== to` | `noop` | уже откачено → идемпотентность повторного запуска |
| `== from` | `write` | штатный откат |
| ни то, ни другое | `conflict` | baseline изменился после записи |

По одному снимку «до» отличить «изменение, которое мы откатываем» от «чужого
изменения поверх» **невозможно** — любой откат по одному снимку является молчаливой
перезаписью. Это та же логика, что у `CatalogProcessingItem.baseline_hashes`
(`docs/catalog/operations/README.md`): изменение baseline после снимка → `conflict`.

Обходного флага у отсутствия `--from` нет: без него conflict-детекция невозможна,
поэтому оба аргумента обязательны. Это осознанный отказ от «удобства» в пользу
fail-closed.

### 4.3 Артефакт снимка

Каноническая сериализация — **та же рецептура, что у release manifest H3**
(`rules_release.canonical_bytes` / `canonical_hash_of`), а не новая: одна рецептура
на все артефакты контура.

```json
{"canonical": {"schema_version": 1, "attribute_slug": "tool_type",
               "selector": {"kind": "explicit_ids", "value": [101, 102]},
               "live_taxonomy_identity_hash": "fc13be78…", "rows_count": 2,
               "rows": [{"product_id": 101, "option_slug": "bury",
                         "option_value": "Буры", "attrs_cache_tool_type": "Буры"}]},
 "canonical_hash": "<sha256 canonical>"}
```

Что даёт каждое поле:

- `rows` — явные `product_id`, как требует `rollback.md` («все id в карте — явные,
  не „по правилу“»);
- `attrs_cache_tool_type` — read-model восстанавливается вместе с EAV по явной
  записи, а не «пересоберётся когда-нибудь сигналом»; post-audit сверяет и его;
- `live_taxonomy_identity_hash` — тот же recipe, что `taxonomy_identity_hash` из H1;
  дрейф словаря между снимком и откатом → отказ, переплан обязателен;
- `canonical_hash` — подделка любой строки ловится при загрузке.

Сравнение состояний идёт по `option_slug` — по значению EAV, единственному источнику
правды. `attrs_cache` производен: он восстанавливается по снимку, но расхождение в нём
конфликта не создаёт.

### 4.4 Решения reverse-map

| disposition | условие | действие |
|---|---|---|
| `keep` | есть в обоих манифестах, `value` совпадает | ничего |
| `reappearing` | есть только в N-1 | вернёт `load_tool_types` (шаг 4) |
| `drop` | исчезает, товаров нет | удаляется (шаг 3) |
| `remap` | исчезает, товары есть, владелец задал явную цель | перенос (шаг 2), затем удаление |
| `blocked` | однозначного отката нет | понижение не исполнимо |

**Почему remap только явный.** Без `option_uid` переименование slug машинно
неотличимо от «удалили одну опцию, добавили другую». Автоматически выбрать цель
переноса — значит молча переклеить товары. Поэтому цель переноса всегда решение
владельца, а машина проверяет его на исполнимость (см. §6).

Порядок операций жёсткий и обеспечен механически: удаление опций проверяет usage
**внутри транзакции** в момент выполнения, поэтому шаг переноса нельзя перепрыгнуть —
опция с товарами отменяет удаление целиком.

## 5. Проверки, доказывающие ключевые утверждения

### 5.1 Идемпотентность

`test_apply_is_idempotent_second_run_writes_nothing`: после успешного отката повторный
`plan_rollback` + `apply_rollback` возвращает `{"written": 0, "noop": 1}`, значение в
БД не меняется. То же на уровне удаления опций:
`test_drop_is_idempotent` → второй прогон `dropped=[]`, `already_absent=['koronki']`.

### 5.2 Частичный сбой не оставляет полуприменённого состояния

`test_partial_failure_leaves_no_half_applied_state`: два товара к откату, сбой
инжектируется в `flush_attrs_cache_merged` **после** записи PAV обоих товаров.
После исключения оба товара остаются в состоянии «после forward-прогона»
(`koronki`), `attrs_cache` тоже не тронут. Мутационная проверка G3 подтверждает, что
тест держится именно на `transaction.atomic()`.

### 5.3 Conflict вместо молчаливой перезаписи

Три независимых сценария:

- `test_plan_reports_conflict_when_live_drifted_from_both_snapshots` — live ушёл в
  третье состояние → `conflict`, `feasible=False`;
- `test_apply_refuses_plan_with_conflicts` — применение отклоняется, значение в БД
  остаётся чужим (проверено после исключения);
- `test_rollback_conflict_exits_1_and_writes_nothing` — CLI: exit 1, в БД ничего.

Плюс `test_plan_reports_conflict_when_product_disappeared` (`reason=product_missing`).

### 5.4 End-to-end на РЕАЛЬНОМ каноническом манифесте

`apps/catalog/tests/test_h5_canonical_downgrade_e2e.py` — контур проверен не только на
синтетике из трёх опций. Берётся настоящий `tool_type_taxonomy.v1.json` (328 опций),
из него строится пара «N=2 → N=1», где в N-1 отсутствуют ровно те четыре опции с
нулевым usage, которые H4 оставил как тестовый материал: `hoz-schetchiki`,
`metchiki`, `osnastka-rezbonarez`, `plashki`.

| Проверка | Результат |
|---|---|
| seed реального манифеста воспроизводит canonical identity | live identity == `fc13be78…`, 328 опций |
| план понижения | `feasible=True`, `keep=324`, `drop=4`, `blocked=0`, drop-список == те самые 4 slug |
| выполнение drop | опций 328 → 324 |
| **приземление на цель** | live `taxonomy_identity_hash` == identity манифеста N-1 |
| товар на исчезающей опции | план `feasible=False`, `orphaned_products`, опция не удалена |
| полная процедура с remap (4 шага) | товар переехал, `attrs_cache` обновлён, post-audit PASS, drop выполнен, live identity == identity N-1 |

Последняя строка — главное доказательство стадии: после процедуры живой словарь
**побитово по identity-рецепту** совпадает с целевым манифестом, то есть БД
приземлилась на предыдущую версию, а не «примерно на неё». Цель переноса в тесте
выбрана произвольно ради демонстрации механики; продуктового решения о слиянии типов
не принималось, в манифест ничего не писалось.

### 5.5 Байт-стабильность артефактов

`test_snapshot_is_byte_stable_across_runs`, `test_snapshot_command_writes_byte_stable_artifact`
(два прогона команды → `read_bytes()` идентичны), `test_plan_document_is_byte_stable`.

### 5.6 Read-only по умолчанию

`test_plan_writes_nothing_to_database` (счётчики options/PAV/products до и после),
`test_snapshot_command_writes_nothing_to_database`,
`test_rollback_dry_run_does_not_write`, `test_downgrade_plan_is_read_only_and_reports_drop`,
`test_downgrade_apply_drop_requires_apply_flag`.

## 6. Негативная матрица — 40 сценариев, все заблокированы

Испорченные артефакты создавались **только во временных каталогах** (`tmp_path`).

| # | Сценарий | Реакция | Тест |
|---|---|---|---|
| 1 | снимок без селектора | отказ | `test_snapshot_requires_exactly_one_selector` |
| 2 | снимок с двумя селекторами | отказ | `test_snapshot_with_two_selectors_is_rejected` |
| 3 | снимок по несуществующему товару | отказ | `test_snapshot_fails_closed_on_unknown_product_id` |
| 4 | селектор по slug вне live-словаря | отказ | `test_snapshot_selector_with_unknown_option_slug_is_rejected` |
| 5 | подделан `canonical_hash` снимка | отказ | `test_load_snapshot_rejects_tampered_canonical_hash` |
| 6 | снимок по чужому атрибуту | отказ | `test_snapshot_with_foreign_attribute_slug_is_rejected` |
| 7 | неподдерживаемый `schema_version` | отказ | `test_snapshot_with_unsupported_schema_version_is_rejected` |
| 8 | дубликаты `product_id` в rows | отказ | `test_snapshot_with_duplicate_product_rows_is_rejected` |
| 9 | `rows_count` не совпадает с rows | отказ | `test_snapshot_with_wrong_rows_count_is_rejected` |
| 10 | документ без секции `canonical` | отказ | `test_snapshot_without_canonical_section_is_rejected` |
| 11 | битый JSON снимка | отказ | `test_snapshot_file_with_broken_json_is_rejected` |
| 12 | снимки покрывают разные множества товаров | отказ | `test_plan_rejects_snapshots_covering_different_products` |
| 13 | целевая опция отсутствует в live-словаре | отказ | `test_plan_rejects_target_option_absent_in_live_taxonomy` |
| 14 | taxonomy дрейфовал между снимком и live | отказ | `test_plan_rejects_taxonomy_drift_between_snapshot_and_live` |
| 15 | baseline изменился (третье состояние) | `conflict` | `test_plan_reports_conflict_when_live_drifted_from_both_snapshots` |
| 16 | товар удалён после снимка | `conflict` | `test_plan_reports_conflict_when_product_disappeared` |
| 17 | применение конфликтного плана | отказ, БД не тронута | `test_apply_refuses_plan_with_conflicts` |
| 18 | товар удалён **между планом и применением** | отказ, БД не тронута | `test_product_deleted_between_plan_and_apply_aborts_write` |
| 19 | опция удалена между планом и применением | отказ, БД не тронута | `test_option_deleted_between_plan_and_apply_aborts_write` |
| 20 | несмежные версии манифеста (v3 → v1) | отказ | `test_plan_rejects_non_adjacent_manifest_version` |
| 21 | обратное направление (v1 → v2) | отказ | `test_plan_rejects_forward_direction` |
| 22 | манифесты по разным атрибутам | отказ | `test_manifests_for_different_attributes_are_rejected` |
| 23 | live-словарь не приведён к манифесту N | blocking | `test_plan_blocks_when_live_taxonomy_is_not_at_from_manifest` |
| 24 | исчезающая опция с товарами без remap | blocking | `test_disappearing_option_with_products_blocks_without_remap` |
| 25 | remap для не исчезающего slug | отказ | `test_remap_for_surviving_slug_is_rejected` |
| 26 | цель remap отсутствует в N-1 | blocking | `test_remap_target_absent_in_target_manifest_blocks` |
| 27 | цель remap сама исчезает | blocking | `test_remap_to_option_that_also_disappears_is_blocked` |
| 28 | цель remap есть в N-1, но нет в live | blocking | `test_remap_to_option_absent_in_live_is_blocked` |
| 29 | смена `value` выжившей опции | blocking | `test_value_change_between_manifests_blocks_as_manual` |
| 30 | удаление опции, на которой висят товары | отказ, опция цела | `test_drop_refuses_when_option_still_carries_products` |
| 31 | удаление опций на неисполнимом плане | отказ | `test_drop_refuses_infeasible_plan` |
| 32 | пара снимков из неисполнимого плана | отказ | `test_snapshot_pair_refuses_infeasible_plan` |
| 33 | пара снимков из плана без remap | отказ | `test_snapshot_pair_refuses_plan_without_remap_entries` |
| 34 | CLI: битый артефакт отката | exit 2 | `test_rollback_invalid_artifact_exits_2` |
| 35 | CLI: отсутствующий артефакт | exit 2 | `test_rollback_missing_artifact_exits_2` |
| 36 | CLI: перезапись снимка без `--force` | exit 2, файл цел | `test_snapshot_command_refuses_to_overwrite_without_force` |
| 37 | CLI: `--emit-from` без `--emit-to` | exit 2 | `test_cli_emit_from_without_emit_to_is_rejected` |
| 38 | CLI: `--remap` не плоское отображение строк | exit 2 | `test_cli_remap_file_must_be_flat_string_mapping` |
| 39 | CLI: `--remap` файл отсутствует | exit 2 | `test_cli_missing_remap_file_is_rejected` |
| 40 | CLI: заблокированный план + `--drop-options --apply` | exit 1, словарь цел | `test_cli_downgrade_writes_nothing_when_plan_is_blocked` |

**Итого 40 негативных сценариев, все заблокированы** (планка H4 — 19/19).

Одна находка получена самой матрицей: сценарий 27 показал, что диагностика выдавала
`remap_target_unknown` там, где точный диагноз — `remap_target_disappearing`
(цель, которая сама исчезает, формально «отсутствует в N-1»). Порядок проверок
исправлен, точный диагноз выдаётся первым.

## 7. Двусторонняя проверка guard'ов — 12/12

Требование планки: тест обязан **падать** при искусственном возврате дефекта и быть
зелёным на чистом состоянии. Проверено скриптом `scratchpad/wave7/h5_mutation_matrix.py`
(лог: `scratchpad/wave7/h5-mutation-matrix.log`): для каждого guard'а исходник портится,
привязанный тест гоняется и обязан упасть, файл восстанавливается (`finally`).

| # | Guard | Мутация | Результат |
|---|---|---|---|
| G1 | conflict-детекция | чужой baseline → `write` вместо `conflict` | тест упал ✔ |
| G2 | apply отклоняет конфликтный план | `if not plan.feasible` → `if False` | упал ✔ |
| G3 | атомарность записи | `transaction.atomic()` → `if True` | упал ✔ |
| G4 | снимки покрывают одно множество товаров | проверка снята | упал ✔ |
| G5 | дрейф `taxonomy_identity` | проверка снята | упал ✔ |
| G6 | целевая опция есть в live | список unknown обнулён | упал ✔ |
| G7 | самосогласованность `canonical_hash` | проверка снята | упал ✔ |
| G8 | смежность версий N → N-1 | проверка снята | упал ✔ (оба теста) |
| G9 | исчезающая опция с товарами блокирует | `if pav_count == 0` → `if True` | упал ✔ |
| G10 | remap только для исчезающих slug | список stray обнулён | упал ✔ |
| G11 | удаление опций fail-closed по usage | проверка снята | упал ✔ |
| G12 | удаление запрещено на неисполнимом плане | проверка снята | упал ✔ |

Чистый прогон после восстановления всех файлов: **PASS**. Скрипт завершился `exit=0`.

## 8. Regression

| Проверка | Результат |
|---|---|
| Полный прогон | **2 failed, 1920 passed, 1 skipped** (355 s); junit `tests=1923 failures=2 errors=0 skipped=1` — совпадает со сбором (1923) |
| — известные environmental | redis-healthcheck + Windows exec bit — только они |
| Арифметика | 1839 (baseline H4) + 81 (новые H5) = **1920 passed** ✔ |
| Сверка сбор ↔ выполнение | collect-only 1923 = junit 1923 (потерянных тестов нет) |
| Тесты H5 в junit-отчёте | 20 + 20 + 17 + 20 + 4 = **81**, все выполнены |
| `manage.py check` | 0 issues |
| `makemigrations --check --dry-run` | No changes detected |
| ruff / black | clean |

**CI на GitHub (run `30241631114`, `28c7bef`):** `tests / test` — success,
`tests / lint` — success, `tests / catalog-rules-gate` — **success** (гейт без
поблажки на ребейзнутом дереве), `tests / frontend` — success. Это же снимает
оговорку локального прогона: два известных падения (redis-healthcheck и Windows
exec bit) — окружение рабочей машины, в CI суита зелёная целиком.

### 8.1 Сверка арифметики

Числу «1920 passed» предшествовала проверка: первый полный прогон отчитался
`1916 passed` при 1923 собранных тестах, то есть четыре теста в том прогоне не
выполнились. Разбор:

- `apps/catalog` отдельно: собрано 983, выполнено 983 (982 passed + 1 skipped);
- всё остальное отдельно: собрано 940, выполнено 940 (938 passed + 2 failed);
- контрольный полный прогон с `--junitxml`: `tests=1923 failures=2 errors=0
  skipped=1` — **сбор и выполнение совпадают**, все 81 тест H5 присутствуют в
  отчёте поимённо.

Причина недосчёта в первом прогоне не установлена; на вердикт она не влияет
(ни одного падения там тоже не было), но принята к сведению: итоговая цифра
взята из прогона, где сбор и выполнение сверены машинно, а не из «хвоста лога».

### 8.2 Ложная тревога, разобранная в окне

В середине окна `apps/catalog/tests/test_processing_concurrency.py` выдал 8–12 ошибок
`psycopg.errors.DeadlockDetected` на `TRUNCATE` в teardown транзакционных тестов.
Разбор:

- на чистом `HEAD` (`git stash -u`) те же тесты проходили → выглядело как регрессия H5;
- `pg_stat_activity` показал **ноль** висящих сессий;
- три подряд прогона с полным набором изменений H5 → `8 passed` каждый раз.

Причина — не код: мутационная матрица запускала pytest подпроцессами против той же
тестовой БД, и полный прогон стартовал, пока их блокировки ещё не разошлись.
Deadlock на `TRUNCATE` воспроизводится только при перекрытии прогонов.
**Вывод для последующих окон: не запускать pytest параллельно с другим прогоном
против общей тестовой БД.** Финальный regression выполнен без параллельной нагрузки.

## 9. Границы соблюдены

Не тронуты: semantics матчера (`evaluate_product`, `facts_hash`), содержимое ruleset v2,
applied corpus, enrichment/apply pipeline (`enrich_tool_type` не изменялся и не
вызывается новым контуром), дерево категорий, фронт. Опции `tool_type` новый контур
**не создаёт** — целевой slug обязан существовать в live-словаре, а исчезающие опции
только удаляются, и только при нулевом usage. Слияний и сплитов типов не выполнялось.
Записи на staging не производились: GO не запрашивался, стадия его не требует.
Phase 8 (pilot rollout) остаётся **FROZEN** до `WAVE 7.1 ACCEPTED`.

Известный P1 из H4 (полный прогон pytest модифицирует отслеживаемый
`data/attribute_rules.json`) в этом окне **не воспроизвёлся**: `git diff` по файлу
пуст после всех прогонов. H5 его не чинил — вне scope.

---

## 10. Решение владельца: `option_uid` — вводить сейчас или фиксировать как долг

> Стадия готовит обоснование и рекомендацию. **Решение принимает владелец.**

### 10.1 Что это

`future_evolution.immutable_option_identity` в манифесте: у каждой option появляется
`option_uid` (UUIDv5 от namespace + slug на момент создания), не меняющийся при
переименовании `value` или reslug. Потребители (provenance `CatalogChange.evidence`,
release manifest, AI findings, reverse-map) ссылаются на `option_uid`, а не на пару
`(slug, value)`.

### 10.2 Что показал H5

Reverse-map машинно **не может** отличить «slug переименовали» от «одну опцию удалили,
другую добавили»: в обоих случаях в манифесте N есть slug, которого нет в N-1, и
наоборот. Отсюда весь дизайн §4.4 — remap только явный, решением владельца.

Контекст H4 подтверждается и уточняется: тогда 15 записей поменяли метаданные без
изменения identity, и развязка сработала «бесплатно». Но identity считается от пары
`(slug, value)` — значит **и** переименование slug, **и** смена `value` меняют
`taxonomy_identity_hash`, а вместе с ним рвут binding замороженного gate-sample и
release manifest. Такой развязки при удалении/переименовании уже не будет.

### 10.3 Вариант A — ввести `option_uid` сейчас

Объём работ:

1. схема манифеста + `option_uid` для всех 328 опций, `manifest_version` 1 → 2,
   валидация уникальности и неизменности;
2. решение по рецепту `taxonomy_identity_hash`: включать uid — значит сменить
   `fc13be78…`, то есть **перевыпустить замороженный gate-sample, labels и release
   manifest** (повтор работы H4); не включать — стабильности identity при rename не
   появится, то есть половина выгоды теряется;
3. `AttributeOption` в БД uid не хранит → миграция модели + backfill + reconcile по
   uid; иначе связь uid ↔ живая опция снова держится на slug, и это та же слабость;
4. миграция потребителей: provenance, release manifest, reverse-map, AI findings;
5. тесты манифеста, reconcile, gate, release, reverse-map.

**Цена:** стадия масштаба H1 плюс повтор H4. **Выгода сегодня: нулевая** —
`manifest_version` = 1, ни одного переименования или удаления ещё не происходило,
а reverse-map и так требует явного решения владельца на каждый remap.

Главный контраргумент: это переоткрывает контракт, который волна только что заморозила
и защитила CI. Делать такое внутри волны, чья цель — «зелёный CI снова является полным
доказательством», значит своими руками обесценить доказательство.

### 10.4 Вариант B — зафиксировать как долг

**Цена сегодня — ноль.** Когда понадобится, объём работ тот же, но выполняется
дешевле: процедура понижения версии уже есть, откат исполняется командой, тестовая
база сценариев готова, а требования к uid станут понятнее на реальном первом
переименовании.

**Риск:** долг «на потом» без триггера имеет свойство не возвращаться.

### 10.5 Рекомендация
> **РЕШЕНИЕ ВЛАДЕЛЬЦА, принято 2026-07-27:** вариант **B с жёстким триггером плюс
> закрытие форвардного reslug через `legacy_aliases`**. `option_uid` сейчас не
> вводится; `legacy_aliases` делаются потребляемыми в seed и reverse-map — это
> отдельная задача, планируемая **после `WAVE 7.1 ACCEPTED`**, чтобы не менять
> дифф волны на ревью. От смены `value` алиасы не защищают: там по-прежнему нужен
> `option_uid`, и триггер долга остаётся в силе.


**Вариант B — зафиксировать как долг, но не «когда-нибудь», а с жёстким триггером.**

Условие, которое делает долг безопасным:

> До первого переименования или удаления slug в манифесте вводится `option_uid`
> **либо** переименование slug запрещается процедурно (только `add` + пометка старой
> опции как deprecated, без reslug).

Обоснование: сегодня цена A — повтор H4 и миграция БД при нулевой выгоде; цена B —
ноль. Ошибка варианта B материализуется только в момент первого reslug, а этот момент
контролируем: он проходит через манифест, ревью и `catalog_taxonomy_reconcile`.

### 10.6 Что при этом остаётся незакрытым (назвать явно)

H5 закрыл **обратный** путь. Форвардный reslug остаётся дырой и вариантом B **не**
закрывается: `load_tool_types` при переименовании slug создаст новую опцию и оставит
старую (политика no-delete), товары останутся на старой — тихий раскол, который
поймает только `catalog_taxonomy_reconcile` постфактум (advisory
`manifest_unused_option` на новой опции, `unexpected_in_live` на старой). Это
отдельная задача, не входившая в ТЗ H5.

Промежуточный дешёвый вариант, если владелец захочет закрыть форвардный reslug без
полного `option_uid`: в схеме манифеста уже есть `legacy_aliases`, сегодня audit-only.
Сделав их потребляемыми (новая опция объявляет прежний slug алиасом), можно получить
машинную развязку для случая переименования без миграции БД и без смены рецепта
identity. От смены `value` это не защищает — там нужен именно uid.

---

## 11. Требует решения / действий вне стадии

1. **`legacy_aliases` как потребляемый механизм** — решение владельца принято (§10), реализация вне scope H5, планируется после `WAVE 7.1 ACCEPTED`.
2. **Форвардный reslug** (§10.6) — закрывается пунктом 1; до его выполнения дыра остаётся.
3. **P1 из H4** (полный pytest модифицирует `data/attribute_rules.json`) — в этом окне
   не воспроизвёлся, но задача остаётся за окном Phase 0.5-fix.
4. Release-evidence по-прежнему живёт в `apps/catalog/tests/fixtures/` — вопрос из H3,
   H5 его не трогал (перенос сменил бы пути в release manifest и потребовал бы
   `--check`-перевыпуска).

## 12. Вход для следующего шага (acceptance волны, §7 плана)

Состояние контура на выходе H5 — по первичным входам **не изменилось**:

```
ruleset     tool_type.v2.json        hash=9bf0271a…  rules=38
corpus      applied_corpus…v1.json   items=54
taxonomy    identity=fc13be78…  semantic=d906be2f…  options=328  pending=0
sample      103 строки, taxonomy_hash=canonical
gate        rows=103 correct=102 precision=0.9902912621359223
release     canonical_hash=e0ff608e…  файл sha256=779d4912…
CI          catalog-rules-gate без поблажки + guard-тест
```

H5 не менял ни один первичный вход контура. Проверено прогоном, а не декларацией:

```
manage.py catalog_rules_release_manifest --check
  ruleset  hash=9bf0271a…  rules=38     corpus id=staging-tool-type-6ebb8ac9d856 items=54
  taxonomy identity=fc13be78…  semantic=d906be2f…  options=328
  gate     rows=103 correct=102 precision=0.9902912621359223 wilson95=[0.947041, 0.998284]
  canonical_hash=e0ff608edc771b5d52874046db13107fd69a24f7f27f7b4a706224bc24e81c8d
  check=ok   EXIT=0
```

`canonical_hash` совпадает с зафиксированным в H4 дословно, поэтому CI-джоба
`catalog-rules-gate` и `--check` остаются валидными без перевыпуска. Добавлены только новые модули, команды,
тесты и документация.

Acceptance-окно (§7 плана) получает: сводный отчёт волны, `/codex review` по диффу
волны, полный regression, PR в `dev`, снятие заморозки Phase 8. H5 сам эти шаги не
начинал — это отдельное окно.

---

**Отчёт для оркестратора:** `scratchpad/wave7/wave7-h5-orchestrator-report.md`.
**Процедура:** `docs/catalog/tool-type-reverse-migration.md`.
**Воспроизводимые артефакты:** `scratchpad/wave7/h5_mutation_matrix.py`,
`h5-mutation-matrix.log`, `h5-regression.log`.
