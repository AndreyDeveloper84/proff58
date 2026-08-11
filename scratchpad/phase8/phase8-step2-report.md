# Phase 8 · ступень 2 — протокол: real batch 10, строго dry-run

Дата: 2026-07-27. Ветка `dev`, HEAD `3f5037650ad89ca45a33811d1373b98d5c315250`
(на 56 коммитов позади `origin/dev`; дерево не обновлялось — git-мутация без
запроса владельца запрещена; baseline сверен на текущем HEAD, дельта
атрибутирована ниже). Окно: одно. БД: локальная dev `proff58`
(`postgres://proff:proff@localhost:5432/proff58`). Regression: отдельная БД
`proff58_ph8reg2` (`--create-db`). Staging не трогался. `--commit` не выполнялся
ни разу (доказательство — §6).

Окружение всех команд:

```bash
export DJANGO_SETTINGS_MODULE=config.settings.dev PYTHONIOENCODING=utf-8 \
       FEATURE_CATALOG_PROCESSING=True \
       DATABASE_URL="postgres://proff:proff@localhost:5432/proff58"
```

---

## 0. Стартовое чтение

Прочитано ровно три источника, в указанном объёме:

1. `scratchpad/phase8/phase8-step1-orchestrator-report.md` — целиком.
2. `docs/plans/2026-07-16-CATALOG_RESEARCH_QUEUE_ROADMAP.md` — §Phase 8
   (последовательность пилота, quality gates), §«Архитектурные инварианты»,
   §«Файловый контракт» (outbox/inbox), §«Модель данных» (state machine
   batch/item/import), §«Правила web research» (identity gate).
3. `.kimi-code/skills/catalog-research/SKILL.md` + `references/source-policy.md`,
   `references/result-contract.md`, `references/taxonomy-routing.md` +
   `apps/catalog/schemas/catalog_research_result_v1.json`.

## 1. БЛОК 0 — разбор G6 (read-only, гейт)

**Вопрос:** очередь использует legacy DB-order `taxonomy_hash`
(`b357be6048…326b` на staging), контур после H4 — canonical
`fc13be7804…14d8`. Влияет ли это на корректность?

### 1.1 Откуда очередь берёт taxonomy_hash, как считается, с чем сверяется

По коду:

- `apps/catalog/queue_contract.py:65-79` — `_allowed_tool_type_options()`
  читает `AttributeOption` из **живой БД** (`order_by("slug")`, порядок —
  DB collation), `_taxonomy_hash()` = `sha256(json.dumps(options,
  sort_keys=True, ensure_ascii=False))`. Сериализация байт-в-байт та же, что у
  canonical `_canonical_json` (`apps/catalog/taxonomy_manifest.py:49-50`);
  разница хэшей — только из порядка списка: DB collation vs code-point sort
  (`taxonomy_identity_hash`, `taxonomy_manifest.py:53-64`). Отсюда две разные
  идентичности одного и того же набора options.
- Export (`catalog_queue_export.py:35-68`): считает legacy-хэш от живой БД,
  кладёт в export-файл и в `run.taxonomy_hash` (`:145-154`); повторный export
  при изменившемся словаре отклоняется (`:38-39`).
- Import (`catalog_queue_import.py:230-236`): пересчитывает legacy-хэш от
  **текущей** БД и требует `result.taxonomy_hash == run.taxonomy_hash` **и**
  `current == run.taxonomy_hash`; slugs валидируются против `allowed_options`,
  пересчитанных из живой БД (`:236, 392-393`).

Canonical-хэш в контуре очереди **не используется вообще**: в queue-командах
он не встречается; его потребители — `rules_gate.py:375` и
`rules_release.py:143` (гейт/release tooling контура правил).

### 1.2 Осознанная привязка или недосмотр

Осознанная, задокументированная в самих артефактах:

- `data/catalog_processing_rules/tool_type_taxonomy.v1.json` (строки 7, 13):
  «basis: staging live taxonomy (identity == pinned b357be60… legacy DB-order
  hash, verified 2026-07-23)»; «Legacy _taxonomy_hash (DB-order, b357be60…) не
  смешивается с hashes этого manifest».
- Докстринг `taxonomy_manifest.py:12-13`: «Hashes (раздельные; НЕ смешиваются
  с legacy `queue_contract._taxonomy_hash`, который order-sensitive и зависит
  от DB collation)».

То есть: manifest волной 7.1 выведен из staging-словаря, опознанного
legacy-хэшем `b357be60…` (зафиксирован 7C/7D 2026-07-23), а canonical identity
hash введён H-серией как environment-independent идентичность для контура
правил. Legacy-хэш оставлен очереди как snapshot-binding guard. Не недосмотр,
переживший H4, — раздельный дизайн.

### 1.3 Что будет при изменении словаря между export и import

Импорт **отвергнет**: пересчитанный от живой БД хэш не сойдётся с
`run.taxonomy_hash` → `CommandError("Текущая taxonomy изменилась после
export")`, EXIT=1 (`catalog_queue_import.py:234-235`). Находки, посчитанные на
другом словаре, молча не пройдут. Дополнительно: результат, посчитанный на
чужом export, не пройдёт сверку `export_checksum` (`:214-218`), а slug вне
живого словаря отбраковывается на item-уровне (`unknown option`, `:392-393`).

### 1.4 Эмпирическая проверка на локальной БД (read-only shell)

```
DB options: 300
legacy (DB)        : ea3105025045e344131bca33e88c565546c2d7abd1590af82b80d9fe7ddcfd0c
identity (DB)      : 978a3562501f01b0fa8f1d2b39e0e6f39a7a8554156d950f9a2b49c763a9bcc3
manifest identity  : fc13be7804b06713dccde5cd2888a437a1a7521772d5911acc7d9d93636714d8
manifest options   : 328
diff: only_in_DB=4 ['drel','hoz-lupy','hoz-provoloka','hoz-zamki']
      only_in_manifest=33 ['aksessuary-dlya-klyuchey', …, 'tochila-nazhdaki', …]
      value_mismatch на общих 295 slug'ах: 0
```

То есть на **локальной** dev-БД словарь (300 options) отстаёт от canonical
manifest (328): 4 legacy-slug'а есть только в БД, 33 новых типа есть только в
manifest, на общих slug'ах расхождений значений нет. Legacy-хэш локальной БД —
третий (`ea310502…`), не staging-овый `b357be60…` и не canonical `fc13be78…`.

### 1.5 Вывод по гейту

**Расхождение на корректность dry-run НЕ влияет — гейт не срабатывает, батч
начат.** Обоснование по коду:

- Внутри контура очереди «находки валидируются против одного словаря, а
  применяются к другому» **не возникает**: и export (allowed_options), и
  import (валидация + сверки), и будущий apply работают против одного и того
  же живого DB-словаря; legacy-хэш гарантирует его неизменность между export и
  import. Canonical manifest в этой цепочке не участвует — смешения двух
  словарей в одном контуре нет.
- Выборка товаров (`catalog_queue_create`) от taxonomy_hash не зависит
  (`_products_without_tool_type`, `catalog_queue_create.py:47-58`).
- Сторонний эффект другой природы: **локальный DB-словарь отстаёт от
  manifest** (300 vs 328). Для ступени 2 это безопасно (dry-run, самосогласованный
  контур), но это вынесено владельцу в калибровке ступени 3: 33 типа manifest
  предложить невозможно (будут отбракованы как `unknown option` — guard
  работает корректно), а 4 legacy-slug'а БД (`drel`, `hoz-*`) прошли бы
  валидацию очереди, но конфликтуют с canonical-таксономией контура правил.
- Код не правился (ни в этой ступени вообще).

## 2. БЛОК 1 — G1 закрыт процедурно

**Жёсткое правило runbook ступени (и всех следующих): каждый вызов
`catalog_queue_import` — только с `--run <run_id>`, без исключений.**
Причина (дефект G1, доказан ступенью 1): имя result-файла не сверяется с
`run_id` внутри — файл одного batch под именем другого импортируется с EXIT=0;
единственный guard — опциональный `--run` (`catalog_queue_import.py:200-206`:
`--run не совпадает с run_id внутри JSON` → CommandError). На реальных данных
перепутанный файл обнаружился бы только после модерации — поэтому `--run`
обязателен процедурно, до починки кода.

Замечание по синтаксису: у команды **нет флага `--dry-run`** — dry-run является
режимом по умолчанию, `--commit` — единственный opt-in
(`catalog_queue_import.py:166-170, 245`). Формулировка промпта
«import --dry-run --run» исполняется как «import без `--commit`, с `--run`».

Соблюдение правила — оба импорта ступени, команды целиком (EXIT=0 оба):

```bash
# импорт №1
uv run python manage.py catalog_queue_import \
  --file var/catalog-processing/inbox/fe48c2c8-387a-4eeb-ba13-b0b82c93bbf6.result.json \
  --run fe48c2c8-387a-4eeb-ba13-b0b82c93bbf6
# импорт №2 (повторный, контроль идемпотентности dry-run)
uv run python manage.py catalog_queue_import \
  --file var/catalog-processing/inbox/fe48c2c8-387a-4eeb-ba13-b0b82c93bbf6.result.json \
  --run fe48c2c8-387a-4eeb-ba13-b0b82c93bbf6
```

Других вызовов импорта в ступени не было.

## 3. БЛОК 2 — цикл

### 3.1 Критерий отбора (дословно)

> **Первые 10 товаров по возрастанию `id` из целевой выборки «товары без
> заполненного `tool_type`»**, где «без `tool_type» — отсутствие
> `ProductAttributeValue` по атрибуту `slug='tool_type'` с непустым
> `value_option` (`catalog_queue_create._products_without_tool_type()`),
> без дополнительных фильтров (без `--in-stock`); воспроизведение:
> `catalog_queue_create --only-untyped --limit 10 --mode tool_type` — команда
> сортирует по `pk` ASC и берёт первые 10.

Проверка достаточности: товаров без `tool_type` в локальной БД — **9120** из
47226, критерий применим без подгонки. Итоговые id: **1, 4, 5, 6, 7, 8, 9, 10,
11, 12**. Cherry-pick не выполнялся; то, что id=1 оказался тестовым
артефактом («Smoke Test 1C»), зафиксировано как есть — исключать его было бы
подгонкой.

Команды (EXIT=0):

```bash
uv run python manage.py catalog_queue_create --only-untyped --limit 10 \
  --mode tool_type --kind research --idempotency-key "phase8-step2-real10-dryrun"
# → Создан run fe48c2c8-387a-4eeb-ba13-b0b82c93bbf6 с 10 items

uv run python manage.py catalog_queue_export \
  --run fe48c2c8-387a-4eeb-ba13-b0b82c93bbf6 --pretty
# → items: 10, checksum: 569a816c5600e76d4f0090a996f041649249b52ac7f0470e190058ad730d592d
# → var/catalog-processing/outbox/fe48c2c8-387a-4eeb-ba13-b0b82c93bbf6.json
```

Параметры export: `target_kind=tool_type`, `taxonomy_hash=ea310502…` (legacy
локальной БД, см. §1.4), `allowed_options=300`, `checksum=569a816c…`.

### 3.2 Research (скилл catalog-research, шаги 3–4 — первое реальное исполнение)

Identity gate и источники — по `references/source-policy.md`; web research
выполнен реальными поисковыми запросами (WebSearch), все URL в evidence —
из реальных выдач, выдуманных нет; схемная валидация (HTTPS, формат) — штатно.
Ручная сверка достоверности источников (открытие страниц) **отложена по
решению владельца → долг до ступени 3** (§7).

| id | Товар (категория: Автоинструмент / Диагностика и контроль) | Identity (основание) | status | Предложение | conf |
|---|---|---|---|---|---|
| 1 | Smoke Test 1C (SMOKE-1C-001) — тестовый артефакт dev-БД | unknown: идентичности в сети не существует | **identity_failed** | — | — |
| 4 | Ареометр АНТ-1 (710-770) ГОСТ 18481-81 | matched: тип АНТ-1 + диапазон + ГОСТ, мультиисточник (rm-pro PDF, шифр 111) | review | `izm-analizatory` | 60 |
| 5 | Ареометр АНТ-1 (830-890) ГОСТ 18481-81 | matched: тип+диапазон+ГОСТ (rm-pro PDF, шифр 113) | review | `izm-analizatory` | 60 |
| 6 | Ареометр АНТ-2 (РФ) 750-830 | matched: тип+диапазон (pnsk-online) | review | `izm-analizatory` | 60 |
| 7 | Ареометр Вымпел АР-02 5002 | matched: точное brand+model (orionspb, vseinstrumenti) | review | `izm-analizatory` | 65 |
| 8 | Ареометр SPARTA 549125 | matched: точный артикул (vseinstrumenti, oma.by) | review | `izm-analizatory` | 65 |
| 9 | Ареометр АНТ2 830-910 с поверкой РФ | matched: тип+диапазон+поверка (izm.by, 5drops) | review | `izm-analizatory` | 60 |
| 10 | Ареометр охлаждающей жидкости (AR030002) | matched: точный артикул на **manufacturer** jonnesway.ru | review | `izm-analizatory` | 70 |
| 11 | Ареометр универсальный KRAFT KT 835570 | matched: точный артикул (vseinstrumenti, illva) | review | `izm-analizatory` | 65 |
| 12 | Ареометр электролита аккумулятора AR030001 (article в БД 048520 — код поставщика) | matched: модель AR030001 на **manufacturer** jonnesway.ru | review | `izm-analizatory` | 70 |

Result-файл: `var/catalog-processing/inbox/fe48c2c8-387a-4eeb-ba13-b0b82c93bbf6.result.json`
(собран `scratchpad/phase8/make_result_step2.py` — решения заданы явно,
`input_hash`/`taxonomy_hash`/`export_checksum` подставлены из export-файла во
избежание ошибок переписывания). Локальная валидация по JSON Schema:
**0 ошибок**.

Обоснование target value (общее): в `allowed_options` (300 слугов) **нет
выделенного типа «ареометр/денсиметр»** (проверено поиском по slug/value:
ближайшие — `izm-analizatory` «Влагомеры, анализаторы, приборы»,
`izm-indikatory`, `izm-termometry`). По `taxonomy-routing.md`: «нет явно
подходящего option → `unknown`; правдоподобно, но не очевидно → `review`».
Ареометр — измерительный прибор, поэтому `izm-analizatory` (хвост «приборы»)
правдоподобен, но не очевиден → везде `review`, а не `researched`; `unknown`
не выбран, т.к. кандидат существует и разумен. В 33 недостающих в БД типах
manifest «ареометров» тоже нет — дыра таксономии системная.

### 3.3 Import (два dry-run, оба с `--run`, EXIT=0) и status

Оба прогона (команды — §2):

```json
{"total": 10, "created": 0, "would_create": 9, "existing": 0,
 "skipped": 1, "errors": 0, "dry_run": true,
 "result_checksum": "f45338b5cf37c9eda0ddf0e5da39f57553c3fc4723a6eb80cec86bf2a12331fd",
 "export_checksum": "569a816c5600e76d4f0090a996f041649249b52ac7f0470e190058ad730d592d"}
```

Повторный dry-run идентичен (стабильность). `catalog_queue_status` после:
items 10 × `pending` (dry-run статусы не двигает — корректно), changes 0.
`finalize` не выполнялся (не требуется для dry-run цикла).

### 3.4 Что измерено

- Предложение `tool_type` дали **9 из 10** (все — `izm-analizatory`, все
  `status=review`, т.е. в commit-режиме ушли бы в модерацию, не в auto-apply).
- Не дали ничего: **1 из 10** — id=1, `identity_failed` (тестовый артефакт;
  корректный отказ контура).
- В `needs_review` ушло бы **10 из 10** в commit-режиме: 9 — как findings
  `proposed` для модерации, 1 — как item-отбраковка `identity_failed`
  (`catalog_queue_import.py:379-385`). Ошибок валидации: **0**.

### 3.5 Где контур ошибся бы, если бы применял (главный результат)

1. **Массовое попадание в catch-all.** Все 9 предложений — один slug
   `izm-analizatory` («Влагомеры, анализаторы, приборы»). Это не «найденный
   тип», а ближайший зонтик. Если бы контур применял: ареометры трёх разных
   подвидов (ГОСТ-денсиметры для нефтепродуктов АНТ-1/АНТ-2; авто-ареометры
   электролита; ареометры ОЖ/тосола) легли бы в «влагомеры/анализаторы» —
   семантически спорно и плохо для навигации покупателя. Защита сработала
   правильно: все 9 — `review` с умеренным confidence (60–70), авто-применения
   не было бы.
2. **Дыра таксономии маскируется.** Скилл обязан выбирать только из
   `allowed_options`; тип «ареометры/денсиметры» отсутствует и в DB-словаре
   (300), и в manifest (328). 9 из 10 товаров batch упёрлись в отсутствующий
   тип — контур это не сигнализирует отдельно, это видно только ручным
   разбором. Предложение владельцу: решить судьбу типа «ареометры»
   (добавление — через контур manifest, отдельная стадия) до массовых batch.
3. **Категорийная слепота.** ГОСТ-ареометры АНТ-1/АНТ-2 (id 4,5,6,9) —
   лабораторно-метрологический товар, но лежат в «Автоинструмент / Диагностика
   и контроль». Контур tool_type этого не оценивает (и не должен в v1), но
   модератору ступени 3 такие кейсы нужно показывать с `category_path` —
   export это поле несёт.
4. **Расхождение article vs model.** id=12: поле `article` в БД (`048520`) —
   код поставщика, модель производителя (AR030001) живёт только в
   наименовании. Identity взят по модели из наименования; при менее удачном
   наименовании был бы `partial`/`unknown`. Автоматического guard'а нет,
   компенсируется identity gate скилла.
5. **Мусор в выборке.** id=1 — тестовый артефакт в dev-БД без маркера
   (в отличие от синтетики PH8-SYN ступени 1). Контур отказал корректно
   (`identity_failed`), но на ступени 3 выборка «первые N по id» снова
   захватит его — учесть в калибровке.

## 4. Границы — подтверждение

- `--commit` не выполнялся ни разу (§6 — доказательство).
- Контур `tool_type` не тронут: tracked-дерево чисто
  (`git status --short --untracked-files=no` — пусто, проверено после всех
  операций; HEAD остался `3f50376`). Matcher, ruleset v2, corpus, manifest,
  артефакты гейта не изменялись.
- Глобальные команды (`enrich_attributes` без `--path`, `rebuild_attrs_cache`)
  не запускались.
- Локальная БД `proff58`; staging не трогался; regression — отдельная БД
  `proff58_ph8reg2` с `--create-db`, pytest с `-p no:pylama`, вывод в файл
  `artifacts-step2/pytest-before.log` (фоновый запуск, прогресс виден).
- Push/PR не выполнялись. `git add` не выполнялся.
- Новые файлы только untracked: этот протокол, `make_result_step2.py`,
  `artifacts-step2/*`, export/result в `var/catalog-processing/` (по контракту
  вне git).

## 5. Regression

```bash
DATABASE_URL=postgres://proff:proff@localhost:5432/proff58_ph8reg2 \
  uv run pytest -p no:pylama --create-db -q
# 2 failed, 1934 passed, 1 skipped in 351.73s
# FAILED tests/test_regression_mvp.py::test_healthcheck_returns_ok      (нет Redis — known)
# FAILED tests/test_deploy_release.py::test_release_script_is_executable (Windows exec bit — known)
# uv run pytest -p no:pylama --collect-only -q → 1937 tests collected
```

| | собрано | failed | passed | skipped |
|---|---|---|---|---|
| Ориентир (ст. 1, тот же HEAD `3f50376`) | 1944* | 2 | 1941 | 1 |
| Baseline/факт (ст. 2) | 1937 | 2 | 1934 | 1 |
| Δ | −7 | **0** | −7 | 0 |

\* ориентир ступени 1 был измерен на её дереве; на текущем HEAD фактический
набор — 1937 (`--collect-only`, совпадает с прогоном). Δ −7 к ориентиру —
разница деревьев, атрибутирована ещё ступенью 1 (локальный HEAD позади
`origin/dev`; с тех пор отставание выросло 42 → 56 коммитов, набор тестов
HEAD не изменился — 1937 и тогда, и сейчас). **Третьего падения нет.**

Прогон один, до батча; после батча повтор не требуется: tracked-дерево не
изменилось ни на байт (§4), тестовая БД — отдельная и пересоздаётся
`--create-db`. Арифметика: 1937 собрано = 2 known failed + 1934 passed +
1 skipped; новых тестов окно не добавляло: 1937 + 0 = 1937. Сходится.

## 6. Доказательство отсутствия `--commit`

Независимые пруфы (не утверждение):

1. **`CatalogChange` по items run — 0** (ORM-запрос после всех импортов;
   все 6 существующих в БД `CatalogChange` датированы 2026-07-17/18 и
   принадлежат другим run — предшествуют окну).
2. **`run.stats.recent_imports` отсутствует** — это поле пишется только
   commit-веткой импорта (`catalog_queue_import.py:279-294`).
3. **Все 10 items остались `pending`** — commit перевёл бы их в `processing`
   / `needs_review` (`:380-385, 441-445`).
4. **Отпечаток каталога до == после** (методика ст. 1,
   `scratchpad/phase8/catalog_fingerprint.py`, поля `code_1c, article, name,
   category_id, price, stock_quantity, status, is_active` + slug опции
   `tool_type`; 47226 товаров, 38106 PAV):

```
ДО    09f404ddb66b803c72b5dc3c1407bdf5bd40515463534c4f4107a2a36e29e64a
ПОСЛЕ 09f404ddb66b803c72b5dc3c1407bdf5bd40515463534c4f4107a2a36e29e64a
diff полных построчных проекций (rows) — пусто (rows equal: True)
```

Снимки: `artifacts-step2/fingerprint-before.json`, `fingerprint-after.json`.

## 7. Долги и вынесенное владельцу

1. **Долг (зафиксирован по требованию промпта): ручная сверка evidence
   обязательна до ступени 3** — на ступени 2 по решению владельца не
   выполнялась; на ступени 3 findings пойдут в модерацию и дальше в каталог,
   автоматического guard'а на достоверность URL в контуре нет.
2. Дыра таксономии «ареометры/денсиметры» (§3.5 п. 2) — решение до массовых
   batch.
3. Локальный DB-словарь (300) отстаёт от canonical manifest (328): 4 legacy
   slug'а, 33 недостающих типа (§1.4) — решить, на каком словаре идёт пилот
   ступени 3 (прогнать `load_tool_types` локально или осознанно зафиксировать
   DB-словарь).
4. Калибровка выборки ступени 3: «первые N по id» дал 9/10 одного семейства
   (ареометры) + тестовый артефакт — предложить «каждый K-й по id» или
   стратификацию по категориям для репрезентативности, критерий — на
   утверждение владельца.

## 8. Артефакты

- Этот протокол: `scratchpad/phase8/phase8-step2-report.md`
- Лог regression: `scratchpad/phase8/artifacts-step2/pytest-before.log`
- Отпечатки: `artifacts-step2/fingerprint-before.json`, `fingerprint-after.json`
- Снимок items export: `artifacts-step2/export-items.txt`
- Генератор result: `scratchpad/phase8/make_result_step2.py`
- Export: `var/catalog-processing/outbox/fe48c2c8-….json`
- Result: `var/catalog-processing/inbox/fe48c2c8-….result.json`
  (`result_checksum f45338b5…`)
- Run `fe48c2c8-387a-4eeb-ba13-b0b82c93bbf6` оставлен в статусе `running`
  (отмена/удаление — отдельное решение; management-команды отмены не
  существует — G3).

---

# Перепроверка на полном словаре (2026-07-27, второе окно)

Продолжение ступени 2 после приёмки: прогон `fe48c2c8` шёл на неполном словаре
(300 опций против 328 в canonical manifest), поэтому вывод о дыре таксономии
требовал перепроверки на полном. Run `fe48c2c8` отменён оркестратором до этого
окна (CatalogChange = 0, отпечаток до/после совпал). Границы прежние: `--commit`
запрещён, контур tool_type не трогаем, новые опции в манифест НЕ добавляем,
глобальные команды запрещены, staging/push/PR не трогаем. Окружение команд — то
же (§0 основного протокола).

## П1. Обновление дерева

- `git fetch` + `git merge --ff-only origin/dev`: `3f50376` → **`8ff3f32`**
  (56 коммитов). Предварительная сверка: ни один untracked-файл рабочей копии не
  пересекается с добавляемыми в `origin/dev` (comm по спискам — пусто), чужие
  незакоммиченные файлы не тронуты.
- Манифест, `load_tool_types`, queue-команды (`create/export/import`) между
  `3f50376..8ff3f32` **не изменялись** (`git log` по этим путям пуст) — правила
  контура те же, что в первом прогоне.

## П2. load_tool_types: fail-closed сработал, разбор, filtered seed

**Первый запуск (canonical manifest, без флагов) — EXIT=1, создано 0:**

```
CommandError: incompatible slug/value mapping: value 'Лупы' уже есть в БД
под slug 'hoz-lupy', manifest предлагает 'izm-lupy'
```

Команда атомарна — транзакция откачена, ни одна опция не создана и не удалена.
Это и есть штатная fail-closed работа: `semantic_duplicate_allowlist` в
манифесте пуст, unique-правило `(attribute, value)` не допускает дубликат
value, поэтому «300 → 328» без решения по legacy-slug'ам невозможно физически.

**Судьба 4 legacy-slug'ов (только в БД; маппинг одобрен владельцем в H1 как
`legacy_aliases` collision-winners, но на локальной БД не исполнен):**

| legacy slug | value | canonical slug (manifest) | PAV на опции | судьба в этом окне |
|---|---|---|---|---|
| `hoz-lupy` | Лупы | `izm-lupy` | 24 | оставлен как есть (remap — отдельное решение) |
| `hoz-provoloka` | Проволока | `krep-provoloka` | 20 | оставлен |
| `hoz-zamki` | Замки и скобянка | `krep-zamki` | 250 | оставлен |
| `drel` | Дрель | — (в manifest value отсутствует, конфликта нет) | 0 | оставлен |

**Побочная находка:** дубль slug'а `steplery` — две строки: id 16 «Степлеры и
заклёпочники» (sort 15) и id 73 «Степлеры (скобозабивные)» (sort 28). Manifest
хранит «Степлеры (скобозабивные)» под slug `steplery` и «Степлеры и
заклёпочники» под `steplery-i-zaklepochniki`; `filter(slug).first()` упирается
в id 16 → ещё два fail-closed конфликта того же класса (PRESENT value-mismatch
+ CREATE value-collision).

**Решение владельца (запрошено в окне): filtered seed через `--manifest`** —
временная копия манифеста без 5 конфликтующих slug'ов (`izm-lupy`,
`krep-provoloka`, `krep-zamki`, `steplery`, `steplery-i-zaklepochniki`), хэши
пересчитаны (`taxonomy_identity_hash`/`manifest_semantic_hash` проверяются
загрузчиком fail-closed). Файл:
`scratchpad/phase8/tool_type_taxonomy.recheck-filtered.json` (323 options).
Canonical манифест **не изменялся**, опции в него не добавлялись.

**Второй запуск — EXIT=0:**

```
Атрибут tool_type готов (manifest v1, 323 options).
created=29, present=294, display_updated=0, display_mismatch=46.
```

- `created=29` (30 кандидатов минус `steplery-i-zaklepochniki`), `present=294`,
  `display_updated=0` (без `--update-display` — 46 расхождений sort_order
  только доложены, список в stdout; display-метаданные сознательно не тронуты).
- **No-delete подтверждён:** удалений нет по построению команды и по факту —
  все 4 legacy-slug'а и обе строки `steplery` на месте, PAV не изменялись.
- Итог словаря: **329 строк / 328 distinct slugs**; **все 328 manifest values
  доступны матчеру** (4 значения — под legacy-slug'ами), отсутствуют только
  slug'и `izm-lupy`, `krep-provoloka`, `krep-zamki`, `steplery-i-zaklepochniki`.
  К перепроверяемым товарам (ареометры) эти 4 типа отношения не имеют.

## П3. Перепрогон тех же 10 товаров

Тот же критерий и команды, новый idempotency-key:

```bash
uv run python manage.py catalog_queue_create --only-untyped --limit 10 \
  --mode tool_type --kind research --idempotency-key "phase8-step2-recheck-full-dict"
# → run bf0cef40-3dd3-4cfd-b893-2ebf67d7f1fd, 10 items
uv run python manage.py catalog_queue_export --run bf0cef40-… --pretty
```

- Items: **[1, 4, 5, 6, 7, 8, 9, 10, 11, 12]** — тот же состав, что в прогоне
  `fe48c2c8` (каталог между окнами не менялся — см. отпечатки).
- Export: `allowed_options=329` (было 300), `taxonomy_hash=6f1140e3…` (был
  `ea310502…` — хэш живого словаря, закономерно новый),
  `checksum=b3744575770bbfad750957116a43ed49a3674970d943264de154ce6c3e935b84`.
- Research: контролируемый эксперимент — меняется только словарь, поэтому
  identity-решения и evidence взяты из первого прогона без изменений (identity
  gate словарь-независим; retrieved_at evidence честно указывает на дату
  первичного сбора). Единственный пересмотр — target option по новому
  `allowed_options`: среди 29 новых slug'ов (и всех 328 values) подходящего
  типа для ареометров нет → решения идентичны. Result собран тем же скриптом
  (`make_result_step2_recheck.py` — копия `make_result_step2.py` с подстановкой
  нового RUN_ID, хэши/чексуммы из нового export-файла), JSON Schema: 0 ошибок.
- Import (dry-run по умолчанию, `--commit` отсутствует, `--run` обязателен):

```bash
uv run python manage.py catalog_queue_import \
  --file var/catalog-processing/inbox/bf0cef40-3dd3-4cfd-b893-2ebf67d7f1fd.result.json \
  --run bf0cef40-3dd3-4cfd-b893-2ebf67d7f1fd
# EXIT=0: total 10, created 0, would_create 9, existing 0, skipped 1, errors 0,
# dry_run true, result_checksum eaaf5c11…, export_checksum b3744575…
```

Форма результата **идентична** первому прогону (9 would_create + 1 skipped +
0 errors): все 9 предложений `izm-analizatory` прошли валидацию против нового
словаря, отбраковок `unknown option` нет.

## П4. Сравнение «было → стало» поимённо

| id | Товар | Тип до (300 опций) | Тип после (полный словарь) | conf |
|---|---|---|---|---|
| 1 | Smoke Test 1C | identity_failed | identity_failed | — |
| 4 | Ареометр АНТ-1 (710-770) | izm-analizatory | izm-analizatory | 60 |
| 5 | Ареометр АНТ-1 (830-890) | izm-analizatory | izm-analizatory | 60 |
| 6 | Ареометр АНТ-2 (РФ) 750-830 | izm-analizatory | izm-analizatory | 60 |
| 7 | Ареометр Вымпел АР-02 5002 | izm-analizatory | izm-analizatory | 65 |
| 8 | Ареометр SPARTA 549125 | izm-analizatory | izm-analizatory | 65 |
| 9 | Ареометр АНТ2 830-910 с поверкой | izm-analizatory | izm-analizatory | 60 |
| 10 | Ареометр ОЖ Jonnesway AR030002 | izm-analizatory | izm-analizatory | 70 |
| 11 | Ареометр KRAFT KT 835570 | izm-analizatory | izm-analizatory | 65 |
| 12 | Ареометр электролита Jonnesway AR030001 | izm-analizatory | izm-analizatory | 70 |

Дельта: **ноль**. Ни один из 9 товаров не получил более точного типа на полном
словаре.

## П5. Вывод по дыре в таксономии

**Дыра «ареометры/денсиметры» ПОДТВЕРЖДАЕТСЯ на полном словаре — это не
артефакт неполного словаря.** Два независимых основания:

1. Эмпирия: перепрогон с 329-доступными опциями (все 328 manifest values) дал
   те же 9 предложений в catch-all `izm-analizatory`, дельта поимённо — ноль.
2. Перебор: среди 33 типов, ранее недоступных матчеру, нет ни одного про
   плотность/денсиметры (перечень: aksessuary-dlya-klyuchey,
   armiruyushchie-lenty-binty, betonosmesiteli, bp-nabory-pnevmoinstrumenta,
   bp-osnastka-pnevmomolotkov, bp-podgotovka-vozduha, dinamometricheskie-klyuchi,
   fiksatory-germetiki-rezby, izm-lupy, kobury-dlya-instrumenta,
   kovshi-shtukaturnye, krep-provoloka, krep-shplinty, krep-zamki,
   kukhonnye-razdelochnye-nozhi, metchiki, nabory-metchikov-plashek,
   osnastka-rezbonarez, otreznye-mashiny-metall, plashki, puskovye-provoda,
   rukoyatki-dlya-instrumenta, skruchevateli-provoloki, spetsialnye-klyuchi,
   spetsialnye-nozhi, stanki-zatochnye, steplery-i-zaklepochniki,
   sterzhni-kleevye, stroitelnye-lesa-vyshki, sumki-poyasnye, sverlilnye-stanki,
   tochila-nazhdaki, vibratory-betona). Полный список `izm-*` на полном словаре
   (17 типов): analizatory, dalnomery, indikatory, kalibry, kleshchi, kleyma,
   kolesa, lineyki, lupy, mikrometry, multimetry, niveliry, ruletki, shtangen,
   shtativy, termometry, ugolniki, urovni — денсиметров среди них нет.

## П6. Предложение владельцу (НЕ применено)

Тип: **slug `izm-areometry`, value «Ареометры (денсиметры)»** — в manifest,
через штатный контур H-серии, отдельным решением.

- Почему slug `izm-areometry`: следует сложившейся схеме `izm-*` для
  измерительного инструмента; ареометр — самостоятельный фасетный тип
  (измерение плотности), покрывающий все три подвида из batch: ГОСТ-денсиметры
  для нефтепродуктов (АНТ-1/АНТ-2), авто-ареометры электролита, ареометры
  ОЖ/тосола. Синоним «денсиметры» в value — для поисковой видимости.
- Почему не подходит ни один из 328: ближайший `izm-analizatory` — «Влагомеры,
  анализаторы, приборы» — семантически про влажность/газоанализ, хвост
  «приборы» — catch-all, а не тип; `izm-termometry` — температура (у ГОСТ
  АНТ термометр лишь встроенный); `izm-indikatory` — индикаторы/пробники без
  шкалы измерения плотности. Остальные `izm-*` — геометрия/электрика/оптика.
- Альтернатива на усмотрение владельца: value «Ареометры» без уточнения, либо
  разделение на лабораторные/автомобильные — но для фасетной навигации
  магазина единый тип практичнее (объём ниши в выборке — десятки SKU).

## П7. Границы и пруфы (второе окно)

- **`--commit` не выполнялся:** `CatalogChange` по run `bf0cef40` — **0**
  (всего в БД 6, те же до-оконные); `run.stats.recent_imports` отсутствует;
  все 10 items остались `pending`; оба вызова import — без `--commit`, с
  `--run` (команды приведены дословно в П3).
- **Отпечаток каталога до == после** (методика ст. 1, тот же
  `catalog_fingerprint.py`; 47226 товаров, 38106 PAV):

```
ДО    09f404ddb66b803c72b5dc3c1407bdf5bd40515463534c4f4107a2a36e29e64a
ПОСЛЕ 09f404ddb66b803c72b5dc3c1407bdf5bd40515463534c4f4107a2a36e29e64a
rows equal: True
```

  Тот же хэш, что и в первом окне (и до, и после) — каталог не менялся ни в
  первом окне, ни между окнами, ни во втором. Снимки:
  `artifacts-step2/fingerprint-recheck-before.json`,
  `fingerprint-recheck-after.json`. Seed словаря отпечатку не виден по
  построению (проекция — поля товара + slug PAV; options словаря в неё не
  входят, PAV не изменялись).
- **Tracked-дерево чисто** (`git status --short --untracked-files=no` — пусто
  после всех операций; HEAD `8ff3f32`). Контур tool_type (matcher, ruleset,
  corpus, canonical manifest, gate-артефакты) не изменялся. Новые файлы —
  только untracked: filtered manifest, `make_result_step2_recheck.py`,
  снимки отпечатков, export/result в `var/catalog-processing/`.
- Глобальные команды не запускались; staging не трогался; push/PR не
  выполнялись; ступень 3 не начиналась. Regression не перепрогонялся:
  tracked-изменений контура нет, а обновление дерева 3f50376→8ff3f32 —
  чужая протестированная история origin/dev (свежий baseline набора тестов —
  отдельное решение владельца, в задание окна не входил).

## П8. Вынесенное владельцу (дополнение к §7 основного протокола)

1. **Remap 4 legacy-slug'ов** (`hoz-lupy`→`izm-lupy`, `hoz-provoloka`→
   `krep-provoloka`, `hoz-zamki`→`krep-zamki`, судьба `drel`): маппинг одобрен
   в H1 (`legacy_aliases`), но на локальной БД не исполнен и блокирует полный
   seed (`300 → 328` через canonical manifest невозможен, только filtered).
   294 PAV. Исполнение — через контур reverse/remap (см.
   `docs/catalog/tool-type-reverse-migration.md`) либо осознанная фиксация
   локального словаря.
2. **Дубль `steplery`** (id 16/73, два значения под одним slug) — та же
   семья legacy-коллизий; на staging словарь чистый (identity == manifest),
   расхождение только локальное.
3. **46 расхождений sort_order** с manifest — не синхронизированы
   (`--update-display` не применялся, display-метаданные вне периметра окна).
4. Тип `izm-areometry` (§П6) — решение до массовых batch, добавление только
   через контур manifest.
5. Run `bf0cef40-3dd3-4cfd-b893-2ebf67d7f1fd` оставлен в статусе `running`
   (отмена — как для `fe48c2c8`, решение оркестратора; команды отмены нет — G3).

## П9. Артефакты второго окна

- Filtered manifest: `scratchpad/phase8/tool_type_taxonomy.recheck-filtered.json`
- Генератор result: `scratchpad/phase8/make_result_step2_recheck.py`
- Отпечатки: `artifacts-step2/fingerprint-recheck-{before,after}.json`
- Export: `var/catalog-processing/outbox/bf0cef40-….json` (checksum `b3744575…`)
- Result: `var/catalog-processing/inbox/bf0cef40-….result.json`
  (`result_checksum eaaf5c11…`)
