# CODE-02 — движок: opt-in `word_boundary` + `kind: text`

Ветка: `feature/catalog-cat14-attribute-schemas` (от CAT-14D: `e7bcd48` CODE-01,
`d39cb5f` CAT-14B, `062f4c7` docs). Push/PR не делались.
`data/attribute_rules.json` НЕ тронут (периметр CAT-14C), staging не использовался,
миграций БД нет (`value_text`/`AttributeType.TEXT`/`VALUE_FIELDS` уже существовали).

## Что добавлено

### Задача 1 — opt-in `word_boundary` для select

- `apps/catalog/tool_type.py:73-77` — `_keyword_ends_at_word_boundary(norm_name, end)`:
  симметричная проверка КОНЦА вхождения поверх того же `_WORD_CHAR` (tool_type.py:32).
- `apps/catalog/tool_type.py:80-99` — публичная `keyword_at_word_boundary(norm_name,
  norm_keyword)`: вхождение целым словом, границы с ОБЕИХ сторон; переиспользует
  существующую `_keyword_starts_at_word_boundary` (tool_type.py:67) + новую проверку
  конца. Логика символ-в-символ не дублируется — обе проверки живут рядом с исходной
  механикой TT-17.
- `apps/catalog/attribute_extract.py:79` — поле `AttrRule.word_boundary: bool = False`;
  парсинг в `_rule` — attribute_extract.py:143 (`a.get("word_boundary", False)`).
- `apps/catalog/attribute_extract.py:207-225` — ветка SELECT: при `word_boundary=True`
  матч через `keyword_at_word_boundary`, иначе прежняя голая подстрока
  `normalize(kw) in norm`. `matched` заполняется сработавшим ключевым словом, как раньше.

**Переиспользование механики**: выбран импорт из `tool_type.py`
(`attribute_extract.py:43`), а не вынос в третий модуль: `_WORD_CHAR` и обе
граничные проверки — единое целое, потребителей ровно два движка, новый модуль
ничего не упростил бы. Доказательство, что `tool_type` не сломан: полный файл
`test_tool_type.py` зелёный (см. прогоны ниже) — поведение `find_keyword_match`
не менялось, новые функции чисто аддитивны.

**Доказательство неизменности default**: тест
`test_select_without_word_boundary_matches_substring_as_before` — правило БЕЗ флага
на тех же данных: «l» матчится внутри STELS, «m» — внутри MAKITA (старое
подстроковое поведение). Все 51 существующих select-правил не несут флага —
полный регресс `apps/catalog` без новых падений (ниже).

### Задача 2 — `kind: text`

- `apps/catalog/attribute_extract.py:48` — константа `TEXT = "text"`.
- `apps/catalog/attribute_extract.py:94` — поле `AttrValue.text: str = ""`.
- `apps/catalog/attribute_extract.py:276-300` — ветка TEXT в `_extract_one`: первый
  сработавший паттерн выигрывает (как у number); значение — группа 1, вырезанная
  из ИСХОДНОГО названия по span матча (normalize сохраняет длину: регистр + ё→е),
  поэтому «CB-155» не теряет регистр; при экзотике Unicode (длина изменилась) —
  откат на normalize()-нный фрагмент. Trim; пустое после trim → паттерн
  пропускается. `matched` = `m.group(0)`, как у number.
  `_extract_one` получил третий параметр `raw` (исходное название) — единственный
  вызов в `extract()` (attribute_extract.py:147).
- `apps/catalog/management/commands/enrich_attributes.py:473-474` — write-path:
  `kind == TEXT` → `pav.value_text = av.text`; обнуление остальных value-полей
  уже было в шапке `_apply_value` (стр. 462-466) и не менялось.
- `apps/catalog/read_models.py:89-92` — ветка сериализации: `extracted_value_to_json`
  отдаёт `text=av.text or ""` (для остальных kinds — пустая строка, отбрасываемая
  как пустое значение, поведение не изменилось). Это и есть «ветка сериализации
  значения», разрешённая периметром; `attr_value_to_json` (current_value) трогать
  не потребовалось — TEXT-атрибут сериализуется из `pav.value_text` штатно.
- Select-options для открытых кодов НЕ создаются: `load_attributes` создаёт
  варианты только для `kind == "select"` (load_attributes.py:96), enrich пишет
  только `value_text`. Покрыто тестом `test_text_kind_creates_no_select_options`.

**Доказательство «dry-run с text ничего не пишет»**: тест
`test_dry_run_reports_text_values_and_writes_nothing` — снимки PAV (все value-поля
+ source + confidence), `attrs_cache` и списка `ImportRun` до/после `--dry-run`
равны; при этом строки отчёта показывают `current_value`/`proposed_value`
(«СТАРЫЙ» → «13-102» для update, `None` → «CB-155» для create).

## Тесты

Новые (все демонстрационные правила инлайн через `AttributeRules.from_dict`,
словарь CAT-14C не используется):

- `test_attribute_extract.py` — `word_boundary`: 6 негативов (S/STELS, L/ANSELL,
  M/MAKITA, L/KRAFTOOL, модельная L2000, XL/XLR-200), 5 позитивов (размер L,
  р-р XL, XXL, диапазоны S-M и L-XL), регрессия default-поведения.
- `test_tool_type.py` — `test_keyword_at_word_boundary_requires_both_sides`:
  обе границы, краевые случаи (пустые строки, начало/конец строки).
- `test_attribute_extract.py` — `kind: text`: «13-102», «CB-155» (регистр),
  числобуквенная A41X, первый паттерн выигрывает, отсутствие совпадения,
  пустое после trim.
- `test_enrich_attributes_text.py` (новый файл, tmp-словарь): запись в
  `value_text` с обнулением остальных полей + attrs_cache, отсутствие
  select-options, перезапись regex≥regex, блокировка перезаписи manual>regex,
  dry-run без записи со снимком БД.

## Числа прогонов (БД `proff58_code02`, свой DATABASE_URL, `--create-db` на 1-м прогоне)

- Baseline (HEAD `062f4c7`, до изменений): **1304 passed, 1 skipped**.
  Оговорка: `scratchpad/cat14/env.sh` выставляет `FEATURE_CATALOG_PROCESSING=True` —
  с ним падает `test_finalize_feature_disabled` (env-эффект, не код; без флага тест
  зелёный — проверено отдельным прогоном). Все прогоны окна — БЕЗ этого флага.
- RED `word_boundary`: 7 failed / 6 passed (позитивы и регрессия зелёные уже на RED —
  это стражи, а не доказательства; падают ровно негативы и тест новой функции).
- GREEN `word_boundary`: `test_tool_type.py` + `test_attribute_extract.py` —
  **325 passed**.
- RED `kind: text`: 7 failed / 5 passed (no-match/trim/manual — стражи).
- GREEN `kind: text`: extract + dryrun + consistency + text —
  **298 passed**.
- Полный регресс `pytest apps/catalog` после всех изменений: **1328 passed,
  1 skipped** (baseline 1304 + 24 новых теста окна, пропущенный тот же).
- `ruff check` по файлам окна: **All checks passed!**
- `black --check -l 100` по файлам окна: чисто (новый тест-файл отформатирован black'ом).

## git diff --stat (только файлы окна)

```
 apps/catalog/attribute_extract.py                  |  56 ++++++-
 .../management/commands/enrich_attributes.py       |   4 +-
 apps/catalog/read_models.py                        |   6 +-
 apps/catalog/test_attribute_extract.py             | 164 +++++++++++++++++++++
 apps/catalog/test_tool_type.py                     |  27 ++++
 apps/catalog/tool_type.py                          |  28 ++++
 6 files changed, 276 insertions(+), 9 deletions(-)
```
(плюс новый файл `apps/catalog/test_enrich_attributes_text.py`, в diff не попадает —
untracked до коммита; 195 строк)

Коммит: **TODO**
