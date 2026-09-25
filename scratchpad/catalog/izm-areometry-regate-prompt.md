# Стартовый промпт окна — новый тип `izm-areometry` + re-gate

Заведено оркестратором 2026-07-28 по решению владельца, после перепроверки ступени 2
Phase 8. Процедура уровня H4: меняется canonical manifest, значит едет идентичность
словаря и привязка gate-артефактов.

---

# TT-01 · Каталог · новый tool_type `izm-areometry` с re-gate
# Проект «Профессионал», ветка dev. Общение только на русском.
# Это изменение canonical manifest — самая охраняемая сущность контура.

## КОНТЕКСТ

Phase 8 ступень 2 и её перепроверка на полном словаре показали: **9 из 10 товаров
(ареометры АНТ-1/АНТ-2, Вымпел, SPARTA, Jonnesway, KRAFT) упираются в catch-all
`izm-analizatory`**, потому что подходящего типа в словаре нет. Перепроверка на всех
328 values дала дельту ноль — дыра реальна, а не артефакт. Все 17 `izm-*` типов
перебраны: `izm-analizatory` — про влагомеры и газоанализ, `izm-termometry` — про
температуру, остальные — геометрия, электрика, оптика.

**Решение владельца: завести тип.** Предложение стадии: slug `izm-areometry`,
value «Ареометры (денсиметры)».

## ГЛАВНОЕ ПОСЛЕДСТВИЕ — почему это не «строчка в JSON»

`taxonomy_identity_hash` считается по составу манифеста. Сейчас он `fc13be78…`, и к нему
**привязаны замороженный gate-sample и labels волны 7.1**. Добавление опции меняет хэш →
привязка ломается → гейт падает. Это ровно та ситуация, которую разбирала стадия H4,
и порядок действий тот же.

## СТАРТОВОЕ ЧТЕНИЕ

1. `scratchpad/wave7/wave7-h4-orchestrator-report.md` — как делалась перепривязка
   (§5 «Ключевое доказательство: смена binding, а не переразметка») и скрипт
   `scratchpad/wave7/h4_rebind_sample.py`;
2. `docs/catalog/tool-type-taxonomy-manifest.md` — контракт манифеста;
3. `docs/catalog/rules-release-manifest.md` — процедура перевыпуска;
4. `apps/catalog/taxonomy_manifest.py` — что входит в каждый из хэшей.

## ЗАДАЧИ

### 1. Добавить опцию в canonical manifest

`data/catalog_processing_rules/tool_type_taxonomy.v1.json`: slug `izm-areometry`,
value «Ареометры (денсиметры)», метаданные по образцу соседних записей
(`origin_kind`, `origin_ref`, `review_status=approved`, `review_ref`) — обоснование
взять из §П6 протокола ступени 2.

**Вопрос владельцу, не решать самому:** поднимать ли `manifest_version` 1 → 2. Это
первое реальное изменение состава манифеста; H5 строил reverse-map именно под переход
`N → N-1`, и bump сделает его впервые применимым. Предложить вариант с обоснованием
и вынести.

### 2. Пересчитать хэши и перепривязать gate-артефакты

- новый `taxonomy_identity_hash` и `manifest_semantic_hash` — зафиксировать оба;
- `apps/catalog/tests/fixtures/phase7d-gate-sample-official.json` — обновить
  `taxonomy_hash`;
- `apps/catalog/tests/fixtures/phase7d-labels.json` — обновить производный `sample_hash`.

**КЛЮЧЕВОЕ ТРЕБОВАНИЕ, оно же главный критерий приёмки: разметку НЕ переразмечать.**
`git diff` по обоим артефактам обязан быть **ровно две строки** — `taxonomy_hash` и
`sample_hash`. `rows=103`, `correct=102`, `unverifiable=1` не должны сдвинуться ни на
единицу. Множество `product_id`, ground truth, `decision`, `rationale`, `reviewer_id`,
`reviewed_at` — идентичны прежним. Подгонка labels под ruleset — тот самый дефект
доверия, ради которого затевалась вся волна 7.1.

### 3. Перевыпустить release manifest

`catalog_rules_release_manifest` — тем же коммитом, что и перепривязка sample
(в H4 это проверялось отдельно). Затем `--check` → `ok`.

### 4. Прогнать гейт без поблажки

`catalog_rules_gate_validate` на новом binding: `gate_passed=true`, EXIT=0,
**без** `--allow-legacy-taxonomy-hash`. Флаг в CI не возвращать — это защищено
guard-тестом `test_ci_job_carries_no_legacy_taxonomy_poblazhka`.

### 5. Обновить документацию, где зафиксирован старый хэш

`CLAUDE.md` §7 содержит `taxonomy_identity_hash = fc13be78…` — после смены он врёт.
Проверить также `docs/catalog/tool-type-taxonomy-manifest.md`, `rules-gate-h2.md`,
`rules-release-manifest.md` и план волны на предмет захардкоженных хэшей.

## ЧЕГО НЕ ДЕЛАТЬ

- **Не сидировать тип в БД.** `load_tool_types` сейчас падает fail-closed из-за трёх
  legacy-slug'ов (`hoz-lupy`, `hoz-provoloka`, `hoz-zamki`, 294 PAV) — это отдельная
  задача `scratchpad/catalog/legacy-aliases-prompt.md`. Здесь только манифест и
  артефакты; попадание типа в БД — после remap.
- Не трогать matcher (`evaluate_product`, `facts_hash`), ruleset v2, applied corpus.
- Не менять `value` существующих опций — это сдвинет идентичность ещё раз.
- Не чинить дубль `steplery` (id 16 / id 73) — отдельное решение владельца.
- Не выравнивать 46 расхождений `sort_order` — тоже отдельно.
- Глобальные команды (`enrich_attributes` без `--path`, `rebuild_attrs_cache`) запрещены.
- Staging не трогать. Ступень 3 Phase 8 не начинать.

## ГРАНИЦЫ РАБОТЫ

- Push и PR — только по явной просьбе владельца.
- **Перед любой работой с GitHub** — сначала `git fetch gitlab --prune` и сверка
  `origin/dev` с `gitlab/dev`: там фронтенд-команда, а деплой делает `git reset --hard`.
- Рабочая копия общая: чужие изменения не откатывать, `git add` только точечными путями.
- Regression — на отдельной БД (свой `DATABASE_URL` + `--create-db`), `-p no:pylama`,
  без длинных немых команд. Baseline сверить самостоятельно на актуальном дереве
  (`origin/dev` ушёл далеко вперёд), показать арифметику.

## ПРИЁМКА

- диф gate-фикстур — **ровно две строки**, разметка не переразмечена (доказать `git diff`);
- `rows=103 / correct=102 / unverifiable=1` не изменились;
- `gate_passed=true`, EXIT=0, без поблажки;
- release manifest перевыпущен тем же коммитом, `--check` → `ok`;
- новые `taxonomy_identity_hash` и `manifest_semantic_hash` зафиксированы в протоколе
  и в документации; старый хэш нигде не остался;
- guard-тест на отсутствие поблажки в CI зелёный;
- regression без третьего падения, арифметика показана;
- вопрос про `manifest_version` вынесен владельцу, а не решён;
- протокол `scratchpad/catalog/izm-areometry-report.md`.

---

## Что оркестратор будет проверять при приёмке

1. **Диф фикстур ровно две строки** — это первое и главное. Больше двух означает, что
   разметку тронули.
2. **rows/correct/unverifiable не сдвинулись.**
3. **Release manifest перевыпущен тем же коммитом**, что и sample, а не отдельным.
4. **Старый хэш `fc13be78…` не остался** ни в `CLAUDE.md`, ни в docs.
5. **Тип в БД не сидирован** — это не эта задача.
