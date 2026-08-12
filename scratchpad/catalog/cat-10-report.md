# CAT-10 · Протокол спасения правил `svar-electrody` / `str-valiki` / `str-kisti`

## Резюме

Три секции правил извлечения характеристик, ранее прогнанные окном CAT-06
scoped-файлом, перенесены в общий словарь `data/attribute_rules.json`.
Воспроизводимость проверена поштучно на 383 значениях из
`scratchpad/catalog/cat-06/plan_staging.json`.

## Использованные артефакты

- `scratchpad/catalog/cat-06/scoped/attribute_rules.json` — локальная копия правил.
- `scratchpad/catalog/cat-06/plan_staging.json` — зеркало стендового прогона
  (CREATE=383).
- `scratchpad/catalog/scoped_rules_verify.py` — переиспользуемый скрипт сверки.

## Сверка scoped-файла с планом

```bash
python scratchpad/catalog/scoped_rules_verify.py \
    --rules scratchpad/catalog/cat-06/scoped/attribute_rules.json \
    --plan scratchpad/catalog/cat-06/plan_staging.json
```

Результат:

- Всего записей в плане: 383
- Совпало: 383
- Не совпало: 0
- Не извлечено: 0

По attr|tt:

- `diameter|str-kisti`: 23/23
- `diameter|svar-electrody`: 238/238
- `length|str-valiki`: 122/122

## Миграция в общий словарь

В `data/attribute_rules.json` добавлены три секции в конец массива `tool_types`:

- `svar-electrody` → `diameter`
- `str-valiki` → `length`
- `str-kisti` → `diameter`

Диф содержит только добавление; `version`, `note` и `source_priority` не изменены.
Количество секций: 38 → 41.

## Сверка общего словаря с планом

```bash
python scratchpad/catalog/scoped_rules_verify.py \
    --rules data/attribute_rules.json \
    --plan scratchpad/catalog/cat-06/plan_staging.json
```

Результат:

- Всего записей в плане: 383
- Совпало: 383
- Не совпало: 0
- Не извлечено: 0

## Влияние на другие типы

Движок `AttributeRules` изолирует правила по ключу `tool_type`: `extract()`
читает только `rules_for(slug)`. Добавление новых секций физически не затрагивает
остальные 38 типов. `source_priority` в scoped-файле и общем словаре идентичен,
поэтому общий ресурс приоритетов не переписан.

## Тест-якорь

Добавлен параметризованный тест `test_cat10_rescued_rules_extract_numbers` в
`apps/catalog/test_attribute_extract.py`. Покрывает 9 реальных названий
(по 3 на каждый тип).

Проверка на снятие защиты:

- При временном удалении секции `svar-electrody` из `data/attribute_rules.json`
  3 теста для этого типа падают.
- После восстановления секции все 9 тестов проходят.

## Baseline тестов

```bash
pytest apps/catalog/test_attribute_extract.py apps/catalog/tests/test_rules_*.py -q
```

Результат: `352 passed, 1 skipped`. Новых падений нет.

## Коммиты

- `cat-10: add reusable scoped_rules_verify.py`
- `cat-10: add svar-electrody/str-valiki/str-kisti attribute rules`
- `cat-10: add regression tests for rescued attribute rules`
- `cat-10: add report`
