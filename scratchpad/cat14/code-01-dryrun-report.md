# CODE-01 · Штатный dry-run для `enrich_attributes` — отчёт

Дата: 2026-08-03. Окно: только код. Периметр CAT-14B (`data/attribute_rules.json`,
`apps/catalog/test_attribute_extract.py`) **не тронут** — рабочее дерево содержит их
параллельные правки, в diff этого окна они не входят.

## Что реализовано

`apps/catalog/management/commands/enrich_attributes.py`:

- Флаг `--dry-run` с алиасом `--report-only` (один `dest="dry_run"`) и опция
  `--json-report <файл>`. **Обоснование выбора:** это байт-в-байт конвенция соседней
  команды `enrich_tool_type` (ENRICH-DRYRUN-ALIASES: те же два имени флага, тот же
  смысл, тот же `--json-report`). Единообразие двух enrich-команд важнее нового
  слова: оператор, знающий `enrich_tool_type --dry-run`, получает ровно тот же
  интерфейс здесь.
- Dry-run = **тот же extraction/write-decision path**, что и apply. Цикл решений
  общий; различие только в финальном шаге:
  - все четыре write-вызова (`delete` / `bulk_create` / `bulk_update` /
    `flush_attrs_cache_merged`) обёрнуты в `if not dry_run`;
  - `ImportRun` в dry-run не создаётся вовсе (`run = None`), его сохранение и
    обработка исключения под `if run is not None`. Отдельный диагностический режим
    с записью ImportRun **не понадобился**: вся диагностика уходит в JSON-отчёт,
    журналировать «не-запуск» в боевой журнал импорта смысла нет;
  - на каждом решении (тем же кодом, что решает в бою) добавляется строка отчёта
    через no-op-хелпер `add_report_row` (в боевом режиме возвращается сразу).
- По-позиционные строки: `product_id`, `tool_type` (slug из PAV
  `value_option.slug` — карта `product_tt` строится из PAV, не из `attrs_cache`),
  `attribute`, `current_value` (через эталонное ядро `attr_value_to_json`),
  `proposed_value` (через то же ядро `extracted_value_to_json`, что пишет
  `attrs_cache` в бою), `source_fragment`, `action`, `reason` + дополнительное
  поле `source` (источник предлагаемого/текущего значения — провенанс для CAT-14C).
- Агрегаты: `totals.by_action`, `by_tool_type` (total + by_action), `by_attribute`
  (total + by_action). Machine-readable JSON — основа вывода; человекочитаемая
  сводка (та же строка, что и раньше) — сверх: при `--json-report` печатается в
  stdout, иначе уходит в stderr, чтобы stdout оставался чистым JSON.

### `source_fragment` без правки движка

Промпт исходил из того, что `AttrValue` фрагмент не несёт. По факту кода поле
`AttrValue.matched` **уже содержит** нужный фрагмент: select/boolean — сработавшее
ключевое слово, number — полный regex-матч (`m.group(0)`), derive — строка
`(inferred)`. Поэтому `attribute_extract.py` **не изменялся вообще**: формат правил
и поведение `extract` для 41 блока нетронуты, `source_fragment = av.matched`.

## Семантика `action` — точно по коду

| action | Условие (код) | Что сделает apply |
|---|---|---|
| `create` | Движок извлёк значение; PAV по `(product, attribute)` отсутствует; для select вариант загружен | `bulk_create` нового PAV + ключ в `attrs_cache` |
| `update` | PAV есть; `priority[new_source] >= priority[pav.source]` | `bulk_update` PAV (перезапись **всегда**, даже при совпадающем значении — текущий код значения не сравнивает) + ключ в `attrs_cache` |
| `skip` | (а) `priority[new_source] < priority[pav.source]` — приоритетная защита (`stats.skipped_priority`); (б) select-вариант не загружен в БД (молчаливый `continue` в боевом режиме) | ничего |
| `prune` | Атрибут управляемый для tool_type; движок значение больше не извлекает; PAV есть и `source ∈ PRUNABLE_SOURCES = {regex, keyword, inferred}` | `delete` PAV + удаление ключа из `attrs_cache` |
| `keep` | Атрибут управляемый; движок не извлёк; PAV есть и `source ∉ PRUNABLE_SOURCES` (manual/import_1c/rules/scraper/web/marketplace/llm) | ничего — значение остаётся |

`confidence` ни в одном решении не участвует (только приоритет источника) — это
зафиксировано и в reason-строках (`приоритет regex (40) < manual (100)`).

### Исходы, которых НЕ существует в текущем коде

- **`moderation`** — в `enrich_attributes` нет очереди/статусы модерации, ни один
  путь кода не откладывает решение «на человека». Не выдуман. Возможное наполнение:
  значения с `source=llm` (confidence 60) при конфликте с engine-значением — сейчас
  они молча проигрывают/выигрывают по приоритету (llm=20 проигрывает всем, кроме
  inferred=10); отдельного исхода нет.
- **`conflict`** — приоритетное сравнение бинарно: `>=` → перезапись, `<` → skip.
  Равный приоритет с **разным** значением (regex 18В против regex 12В) молча
  перезаписывается — формально это `update`. Не выдуман. Возможное наполнение:
  помечать `update` с `current_value != proposed_value` при равном приоритете как
  `conflict` в отчёте (поведение записи при этом не меняется). Оставлено за
  пределами окна: это меняет отчётную семантику боевого решения, а не фиксирует её.

## Поведение пишущего режима — не изменилось

Изменения файла, видимые write-режиму:

1. `add_arguments`: два новых флага (по умолчанию выключены).
2. `run = None if dry_run else ImportRun.objects.create(...)` и симметричные
   `if run is not None` — при `dry_run=False` тот же код, что был.
3. Четыре flush-вызова под `if not dry_run` — при `dry_run=False` выполняются в тех
   же местах, с теми же батчами.
4. `select_related("attribute")` → `select_related("attribute", "value_option")` —
   только форма чтения префетча (убирает N+1 для `current_value` в dry-run); набор
   полей и семантика записи не меняются.
5. Строка сводки собирается в переменную `summary` перед печатью — текст и канал
   (stdout, `style.SUCCESS`) прежние; команда по-прежнему возвращает `str(run.pk)`,
   который `BaseCommand.execute()` автоматически печатает (как и раньше).
6. В prune-цикле составное условие `pav is None or pav.pk is None or source not in
   PRUNABLE_SOURCES` развернуто в явную ветку `keep` — порядок и результат ветвлений
   идентичны (это и покрывает эквивалентность-тест).

Доказательство — тест `test_apply_mode_unchanged` (ImportRun создан, статус done,
команда вернула его pk, значения и `attrs_cache` записаны как раньше) плюс весь
прежний набор `apps/catalog` (см. ниже) без новых падений.

## Доказательство «dry-run ничего не пишет»

Тест `test_dry_run_writes_nothing`: полный снимок всех PAV (значение через
`attr_value_to_json` + `source` + `confidence`), снимок `attrs_cache` всех товаров и
счётчик `ImportRun` до и после прогона `--dry-run` — попарно равны. Отчёт при этом
непуст (решения принимались). Тот же снимок повторно проверяется внутри
эквивалентность-теста после dry-run и до apply.

## Доказательство эквивалентности dry-run и apply

Тест `test_dry_run_decisions_match_apply`: смешанный набор из 4 товаров
(create / skip-manual + prune / update / keep-manual). Алгоритм проверки:

1. Снимок всех PAV «до»; прогон `--dry-run`; снимок после dry-run == снимку «до».
2. Строки отчёта применяются к снимку как предсказание: `create` → новый ключ с
   `proposed_value`/`source`; `update` → замена значения; `prune` → удаление ключа;
   `skip`/`keep` → значение обязано равняться `current_value`.
3. Боевой `enrich_attributes`; фактический снимок сравнивается с предсказанным
   **целиком**: совпадение множества ключей, значений и источников.
4. `attrs_cache`: для каждого товара управляемые ключи равны предсказанным
   `proposed_value` (create/update), prune-ключи отсутствуют.

## Результаты проверок

Изоляция БД: `DATABASE_URL=postgres://proff:proff@localhost:55432/proff58_code01`,
своя база (`--create-db` на первом прогоне, далее `--reuse-db`).

- `pytest apps/catalog/test_enrich_attributes_dryrun.py` — **12 passed** (RED→GREEN:
  до реализации те же тесты падали с `unrecognized arguments: --dry-run`).
- `pytest apps/catalog` целиком: **6 failed, 1240 passed, 1 skipped** (7 м 21 с).
  Все 6 падений — `apps/catalog/test_attribute_extract.py` (тесты блока
  `metchiki-plashki`, `KeyError: 'diameter'` и т.п.) — периметр CAT-14B, который
  в этот момент активно правил `data/attribute_rules.json` (в диффе окна этих
  файлов нет, `enrich_attributes` они не импортируют). Доказательство внешности:
  повторный прогон того же файла через несколько минут на неменявшемся коде окна
  дал **другой** набор падений (`1 failed` — `test_mp_vorotok_no_size`, ранее
  зелёный): состав падающих тестов гуляет вслед за правками соседнего окна.
- Контрольный прогон после финального black/ruff:
  `pytest apps/catalog/test_enrich_attributes_dryrun.py apps/catalog/test_attribute_pipeline.py`
  — **21 passed** (12 новых + 9 прежних pipeline-тестов пишущего режима).
- `ruff check` обоих файлов — чисто; `black --check -l 100` — чисто.

## `git diff --stat` (только файлы окна)

```
 apps/catalog/management/commands/enrich_attributes.py | 250 ++++++++++++++++++---
 1 file changed, 222 insertions(+), 28 deletions(-)
 apps/catalog/test_enrich_attributes_dryrun.py         | 411 строк (новый файл)
```

Замечание: `git status` показывает чужие правки (`data/attribute_rules.json`,
`apps/catalog/test_attribute_extract.py`, `.gitignore`, `scratchpad/phase8/…`) — это
параллельное окно CAT-14B; в состав этого окна они не входят и здесь не менялись.
