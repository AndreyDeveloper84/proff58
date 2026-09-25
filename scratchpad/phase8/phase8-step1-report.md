# Phase 8 · ступень 1 — synthetic batch: протокол

Дата: 2026-07-27. Ветка: `dev`, HEAD=`3f50376`. Исполнитель: окно Phase 8 / ступень 1.
Опора: `scratchpad/phase8/phase8-step1-prompt.md`,
`docs/plans/2026-07-16-CATALOG_RESEARCH_QUEUE_ROADMAP.md` §Phase 8.

---

## 0. Итог одной строкой

Контур research-queue прогнан end-to-end на пяти синтетических cases в
изолированной БД-песочнице: все пять обязательных доказательств получены с
пруфами, негативная матрица (17 сценариев) пройдена, guard'ы доказаны двумя
независимыми mutation-наборами (6 guard'ов importer + 2 pytest guard-теста),
инвариант «отмена batch не меняет каталог ни на байт» доказан хэшем до/после,
каталог за весь цикл не изменился (`8a2dab32…` на входе == на выходе, 15
независимых снимков), regression в двух независимых прогонах без третьего
падения. Найдено 6 отклонений/наблюдений (G1–G6), из них два требуют решения
владельца до real batch с commit.

## 1. Среда и изоляция

- Рабочая БД — **изолированная песочница** `proff58_phase8` (localhost PostgreSQL),
  отдельная от dev-БД `proff58` и от staging. Скрипт сида
  (`scratchpad/phase8/seed_synthetic.py`) **отказывается работать**, если в БД есть
  хоть один несинтетический товар.
- Содержимое песочницы: 1 категория-маркер `ph8-syn-sandbox` («PH8-SYN SANDBOX
  (не каталог)») и 8 фиктивных товаров с маркерами `PH8-SYN-001…008` во всех
  идентификаторах (`code_1c`, `article`, `name`, `original_name`, `source_group`).
  Проверено запросом: `products_total=8`, `non_synthetic=0`.
  Товары 1–5 — cases batch; 6–8 — «свидетели» вне batch.
- Feature flag: `FEATURE_CATALOG_PROCESSING=True` через env (`config/settings/base.py:283`).
- Ни один реальный товар в batch не попадал — гарантировано архитектурно
  (песочница) и проверено фактически (все `product_ref` ∈ {1..8}, маркер `PH8-SYN`).
- Отпечаток каталога: `scratchpad/phase8/catalog_fingerprint.py` — SHA-256 по
  канонической проекции неприкасаемых полей (`code_1c`, `article`, `name`,
  `category_id`, `price`, `stock_quantity`, `status`, `is_active`, slug опции
  `tool_type`) всех товаров песочницы.

**Опорный отпечаток (seed, до всех run):**
`8a2dab32fc27754c6b3bb7c98cbe0cf93f2221505ef957ac7b1409299c93243c`
(`PRODUCTS=8`, `PAV_TOOL_TYPE=0`) — `artifacts/fingerprint-00-seed.json`.

Замечание о git: фактическое состояние — HEAD `3f50376` на **42 коммита позади**
`origin/dev` (`8d128b4`); в промпте указан устаревший `71cb035`. Tracked-файлы
не изменялись (`git diff` пуст на финише), staging не выполнялся, push не было.

**Параллельное окно.** Ступень фактически исполнялась двумя окнами в общей
песочнице: параллельное окно работало 12:06–12:25 (артефакты `01`–`09`,
`N-A`, `N-B`, `C1`/`C2`, `fingerprint-00…10`, `make_*.py`, `run_*.py`,
`negatives/`), это окно — 12:15–12:35 (артефакты `10-create-r3`…`60`). Нумерация
артefактов у окон разошлась без перезаписей. Конфликтов по состоянию не
возникло: выводы обоих окон независимо совпали до последнего хэша (см. §4, §6).
Финальное состояние runs сверено этим окном после завершения параллельного.

## 2. Runs песочницы

| Run | Ключ идемпотентности | Назначение | Финальный статус |
|---|---|---|---|
| `8cc21405-866e-4d0a-9276-3f5f2bd9f63f` | `phase8-step1-synthetic-batch` | happy path (первый заход) | `completed` (`completed_with_review`) |
| `22b4f0d1-45b2-4a07-a8a0-87f2ac62afb7` | `phase8-step1-happy-r3` | happy path, полный протокол | `completed` (`completed_with_review`) |
| `aa41cc90-ecac-410e-823a-66929c1fd2f8` | `phase8-step1-cancel-invariant` | инвариант отмены + guard'ы cancelled | `cancelled` |
| `08b74147-0d1a-4341-a942-b118a88473ff` | `phase8-step1-finalize-without-import` | finalize без импорта → отмена до/после | `cancelled` |
| `5ecbf02e-40d6-4c90-b636-e4eed72b7b3b` | `phase8-step1-negative-matrix` | негативная матрица файлов | `running` (оставлен для продолжения) |
| `a9fb709d-…`, `df26469d-…` | `phase8-step1-stale-probe(-2)` | stale input snapshot probe | `cancelled` |

## 3. Happy path (run `22b4f0d1`, ids 1–5) — пять обязательных доказательств

Result-файл: `var/catalog-processing/inbox/22b4f0d1-….result.json`
(`result_checksum=b4b3ffb0…`). Решения: 1 → `perforatory` (researched, conf 90),
2 → `dreli-shurupoverty` (researched, conf 75), 3 → `unknown`, 4 → `review`,
5 → `identity_failed`. Все evidence — `https://synthetic.invalid/…` (фиктивные).

### 3.1 Create + детерминированный export

- `catalog_queue_create --explicit-ids 1,2,3,4,5 --idempotency-key phase8-step1-happy-r3`
  → «Создан run 22b4f0d1… с 5 items» (`artifacts/10-create-r3.txt`).
- Два экспорта подряд (`artifacts/11-export-r3-a.json`, `…-b.json`):
  - поле `checksum` **одинаковое**: `9b027e1a40e81db97376ddf7c04187fc8c36cc27041b4e86de253f8d43c4bd84`;
  - sha256 файлов **различаются** (`f134da91…` vs `a798aa7b…`) — единственное
    отличие payload — `exported_at` (доказано: payload без `exported_at`
    идентичен, см. вывод в протоколе шага);
  - то же воспроизведено на run `8cc21405` (checksum `b5dfb865…` оба раза).
  - **Отклонение G2**: побайтовая идентичность повторного экспорта НЕ выполняется
    (в файл пишется `exported_at`; checksum считается без него — см. комментарий
    в `catalog_queue_export.py:107`). Детерминирован checksum, не файл.
    Приёмка формулировала «байт в байт» — фактический контракт слабее.
- Checksum привязан к run (в payload входит `run_id`): у другого run тот же
  снапшот даёт другой checksum (`9b027e1a…` vs `b5dfb865…` vs `459a2c8e…`) —
  подмена файла между run ловится сверкой `export_checksum`.

### 3.2 Импорт: dry-run ничего не пишет, двойная валидация

- Dry-run (`artifacts/13-import-r3-dryrun.txt`, EXIT=0):
  `would_create=2, skipped=3, errors=0`. После: `changes=0`, все items `pending`
  (`artifacts/13-import-r3-dryrun-dbcheck.txt`) — **ноль записей**.
- Валидация двухъярусная и доказана в негативной матрице (§5): JSON Schema
  (N2/N2b), домен/таксономия (N5 unknown option, N12 identity, N13 https,
  N14 duplicates) + сверки `export_checksum`/`taxonomy_hash`/`input_hash`/snapshot.

### 3.3 Findings — в модерацию, не в каталог; apply — отдельная авторизация

- Commit (`artifacts/14-import-r3-commit1.txt`, EXIT=0): `created=2, skipped=3`.
  Созданы ровно 2 `CatalogChange(status=proposed)`: ref 1 → `perforatory`,
  ref 2 → `dreli-shurupoverty`. Items 3/4/5 → `needs_review` с кодами
  `unknown`/`review`/`identity_failed`. **`PAV tool_type = 0`** — каталог не тронут
  (`artifacts/14-import-r3-commit-dbcheck.txt`).
- Попытка apply без модерации (`artifacts/16-apply-without-auth-r3.txt`):
  `apply_catalog_change(proposed)` → `invalid / change_not_approved`; change
  остался `proposed`; `PAV tool_type = 0`. Авторизация = модерация
  (`review_catalog_change` → approved), без неё apply отказывает.
- `catalog_queue_status` (`artifacts/15-status-r3.txt`): items 2 processing +
  3 needs_review, changes 2 proposed, pending_review=2, errors по 3/4/5.

### 3.4 Идемпотентность повторного импорта

- Повторный commit того же файла (`artifacts/14-import-r3-commit2.txt`, EXIT=0):
  `created=0, existing=2, skipped=5`. Дублей нет (idempotency key
  `sha256(result_checksum:run:ref:tool_type:slug)`). На run `8cc21405` то же
  зафиксировано в `stats.recent_imports`: `created=2` → `existing=2`.

### 3.5 Закрытие цикла: модерация → finalize → идемпотентный finalize

- `review_catalog_change(×2, rejected, reviewer_id=1)` → оба `rejected`, items
  ушли в `needs_review` (`artifacts/17-review-r3.txt`).
- `catalog_queue_finalize` → `completed`, `outcome=completed_with_review`,
  EXIT=0 (`artifacts/17-finalize-r3-1.txt`).
- Повторный finalize → `already_finalized=true`, EXIT=0
  (`artifacts/17-finalize-r3-2.txt`).
- **Отпечаток после полного цикла == до цикла == seed**:
  `8a2dab32…` (`artifacts/12-fingerprint-r3-preimport.json`,
  `18-fingerprint-r3-postcycle.json`).

## 4. Инвариант «отмена batch не меняет каталог ни на байт»

Доказан тремя независимыми срезами, все — хэшем, не декларацией:

1. **До/после отмены** (run `08b74147`, ids 6–7): отпечаток до отмены
   `8a2dab32…` == после отмены `8a2dab32…`
   (`artifacts/21-fingerprint-precancel-08b7.json`,
   `21-fingerprint-postcancel-08b7.json`, вердикт `21-cancel-invariant-verdict.txt`).
2. **Глобально за всю ступень**: отпечаток seed (до любых run) == финальный
   отпечаток после create/export/import×4/commit×3/review/finalize/отмены трёх
   run и всех негативных сценариев: `8a2dab32…` == `8a2dab32…`
   (`artifacts/50-fingerprint-final.json`, вердикт `50-final-verdict.txt`).
   В том числе отмена run `aa41cc90`, у которого остались 2 `proposed` findings.
3. **Каталожные записи значений**: `ProductAttributeValue(tool_type)` = 0 строк
   на каждом контрольном шаге — findings живут только в `CatalogChange`
   (аудит-таблица), каталог не материализуется.
4. **Пошаговая цепочка параллельного окна**: 11 снимков `fingerprint-00…10`
   (seed → after-dryrun → after-commit → after-apply-attempt → after-reject →
   after-finalize → before-cancel → after-cancel → after-mutations → final →
   after-apply-cancelled) — все `8a2dab32…`. Итого по обоим окнам **15
   независимых снимков** за ступень, один хэш.

Guard'ы отменённого run (`artifacts/22-cancelled-run-guards.txt`):
- import в отменённый run → `CommandError: … не находится в status=running`, **EXIT=1**;
- export отменённого run → `CommandError: … экспорт невозможен`, **EXIT=1**;
- finalize отменённого run → `run_not_running:cancelled`, **EXIT=1**.

Дополнительно (`artifacts/23-approve-apply-in-cancelled.txt`): модерация может
одобрить finding в отменённом run (`review` → `approved`), но **apply блокируется**
`run_not_running` → change `invalid`, `PAV=0`. Двойной контур защиты держится
(наблюдение G5: `review_catalog_change` статус run не проверяет — безвредно,
т.к. apply перепроверяет под блокировкой, но стоит зафиксировать).

**Отклонение G3**: management-команды отмены run не существует — отмена
выполнена статусным переходом через ORM (`status=cancelled`). Роадмап
(«Rollback: отменить batch») и state machine (`CatalogProcessingRunStatus.CANCELLED`)
предполагают операцию, инструмента нет.

## 5. Негативная матрица (все сценарии, коды выхода)

Испорченные файлы создавались только во временном подкаталоге
`var/catalog-processing/inbox/ph8-tmp/` (после прогона удалён). Рабочий run —
`5ecbf02e` (export checksum `459a2c8e…`).

### Файловый уровень — CommandError, EXIT=1 (`artifacts/31-negative-filelevel.txt`)

| # | Сценарий | Ответ контура | EXIT |
|---|---|---|---|
| N1 | Битый JSON | `Невалидный JSON: Expecting value…` | 1 |
| N2 | Не по схеме (`schema_version=2.0`) | `JSON Schema: schema_version…` | 1 |
| N2b | Не по схеме (нет `export_checksum`) | `JSON Schema: <root>: required property` | 1 |
| N4 | Чужой/несуществующий batch | `Run 11111111-… не найден` | 1 |
| N11 | `export_checksum` не совпадает | `export_checksum не совпадает с последним export` | 1 |
| N12 | changes без `identity=matched` | `changes запрещены без identity.status=matched` | 1 |
| N13 | evidence не HTTPS | `evidence.url должен быть абсолютным HTTPS URL` | 1 |
| N14 | duplicate `product_ref` | `items[1]: duplicate product_ref 1` | 1 |
| N17 | Файл вне inbox | `Файл должен находиться внутри …\inbox` | 1 |

### Item-уровень — EXIT=0, `errors=1`, `created=0` (`artifacts/32-negative-itemlevel.txt`, `33-negative-commit.txt`)

| # | Сценарий | Ответ контура | Запись в БД |
|---|---|---|---|
| N5 | `tool_type` вне манифеста (`phantom-type-ph8`) | `unknown option phantom-type-ph8` | dry-run: 0; commit: `changes=0`, `PAV=0` |
| N6 | `product_ref` не из batch (6) | `item не найден` | dry-run: 0; commit: `changes=0`, `PAV=0` |
| N15 | `input_hash` не совпадает | `input_hash не совпадает` | 0 |
| N16 | Товар изменился после export (live: переименован товар 6 после export) | `current input snapshot изменился` (`artifacts/41-negative-stale-input-full.txt`) | 0; имя товара 6 восстановлено, отпечаток вернулся к `8a2dab32…` |

EXIT=0 при item-ошибках — дизайн роадмапа («ошибка одного item не откатывает
валидные items всего batch»): отказ фиксируется в `stats.errors`, а в commit —
`item → needs_review` (аудит). **Наблюдение G4**: оператор обязан читать
`errors` в выводе, а не только код выхода.

### Имя файла и run_id — отклонение G1

| # | Сценарий | Факт | EXIT |
|---|---|---|---|
| N3 | Валидный контент run `5ecbf02e` под чужим именем файла | **Импортируется успешно** (`skipped=1, errors=0`) — имя файла с `run_id` НЕ сверяется | 0 |
| N3b | Тот же файл + `--run <другой uuid>` | `--run не совпадает с run_id внутри JSON` | 1 |

Роадмап (§Валидация importer) требует «batch id совпадает с именем/содержимым»;
в коде сверка есть только через опциональный `--run`. Проблема смягчается тем,
что `export_checksum` и `taxonomy_hash` всё равно связывают файл с конкретным
run, но имени файла контур не доверяет и не проверяет.

### Остальные обязательные сценарии

| # | Сценарий | Где доказан | Вердикт |
|---|---|---|---|
| N7 | Повторный импорт | §3.4, `created=0/existing=2` | идемпотентен |
| N8 | Импорт в отменённый batch | §4, EXIT=1 | отвергнут |
| N9 | Finalize без импорта | `items_not_final`, EXIT=1 (`artifacts/20-finalize-without-import.txt`) | отвергнут |
| N10 | Apply без авторизации | §3.3, `change_not_approved`, `PAV=0` | отвергнут |

Ни в одном сценарии запись в каталог не произошла (`changes=0`/`PAV=0`,
отпечаток неизменен).

### Mutation probe: guard'ы падают при снятии проверки (два независимых набора)

Набор A (параллельное окно, `artifacts/09-mutations.txt`, уровень кода importer
с откатом БД): 6 guard'ов доказаны парой «включён/снят» — JSON Schema
(`items` required), `allowed_options` (словарь tool_type), identity gate
(`_domain_validation`), сверка `export_checksum`, сверка `item.input_hash`,
сверка `taxonomy_hash`. По каждому: «ВЕРДИКТ: GUARD ДОКАЗАН».

Набор B (это окно, `artifacts/60-mutation-probe.txt`, уровень pytest):
- снята проверка unknown option → `test_import_rejects_unknown_option` **FAILED**;
- снята проверка `input_hash` → `test_import_rejects_changed_input_hash` **FAILED**;
- оба восстановлены, тесты снова зелёные, `git diff` пуст.

Guard-покрытие в репозитории (`apps/catalog/tests/test_queue_commands.py`):
deterministic export, dry-run без записей, unknown option, changed input hash,
stale current input, идемпотентность, run override mismatch, external path,
taxonomy/export mismatch, reexport при сменившейся taxonomy, контрактные
ошибки researched/unknown/identity_failed с changes, finalize rejects pending
и др. (28 тестов модуля).

## 6. Regression (отдельная БД)

Команда: `pytest --create-db -q` с `DATABASE_URL=…/proff58_ph8_regress`
(тестовая БД `test_proff58_ph8_regress`). Лог: `artifacts/regression-full.log`.

**Два независимых полных прогона** (это окно и параллельное,
`artifacts/10-regression.txt`) дали идентичную арифметику:

```
2 failed, 1934 passed, 1 skipped in 590.18s (0:09:50)   # окно A
2 failed, 1934 passed, 1 skipped in 575.37s (0:09:35)   # окно B
FAILED tests/test_regression_mvp.py::test_healthcheck_returns_ok   (нет Redis — known)
FAILED tests/test_deploy_release.py::test_release_script_is_executable (Windows exec bit — known)
```

Прогоны частично пересекались во времени; `DeadlockDetected` не возникло ни в
одном логе — предупреждение ступени о параллельных прогонах не материализовалось.

**Арифметика.** Baseline ступени: `2 failed (known), 1941 passed, 1 skipped`.
Факт: `2 failed (те же known), 1934 passed, 1 skipped`. Третьего падения нет —
регрессии нет. Δ passed = −7 атрибутуется состоянию дерева, а не работой окна:
локальный HEAD `3f50376` на 42 коммита позади `origin/dev` (`8d128b4`), где
добавлены тестовые модули (`apps/catalog/test_attribute_extract.py`,
`apps/promotions/tests/`, `apps/reviews/tests/` и др. — `git diff HEAD origin/dev
--numstat`). Tracked-файлы окном не менялись. История локальных прогонов того
же дерева: wave7 h4 = 1839, h5 = 1920, h6 = 1938 passed — число плавает с
коммитом, два падения стабильно окружение.

## 7. Границы — соблюдены

- Реальных товаров в batch не было: песочница, маркеры `PH8-SYN`, проверка
  `non_synthetic=0`.
- Apply к каталогу не выполнялся (только негативные пробы, отвергнутые контуром).
- Контур `tool_type` (matcher, ruleset v2, applied corpus, canonical manifest,
  артефакты гейта) не трогался; tracked-файлы не менялись вообще (`git diff`
  пуст; mutation-probe — временные правки с немедленным откатом).
- Глобальные команды (`enrich_attributes` без `--path`, `rebuild_attrs_cache`)
  не запускались.
- Всё локально; staging не трогался; push/PR не было.
- `git add` не выполнялся; чужие изменения не откатывались.
- Regression — на отдельной БД с `--create-db`.

## 8. Отклонения и наблюдения (для решения владельца)

| ID | Суть | Критичность для ступени 2 |
|---|---|---|
| G1 | Имя result-файла не сверяется с `run_id` (guard только через опциональный `--run`) | Средняя: файл всё равно привязан к run через `export_checksum`/`taxonomy_hash`; до real commit решить — принять или добавить сверку имени |
| G2 | Повторный export не побайтово идентичен (`exported_at`); детерминирован только `checksum` | Низкая: приёмку формулировать как «checksum-детерминизм»; либо убрать/зафиксировать `exported_at` |
| G3 | Нет management-команды отмены run (только ORM-переход) | Средняя: для rollback-runbook нужен операторский инструмент |
| G4 | Item-ошибки дают EXIT=0; отказ виден только в `stats.errors` | Низкая: зафиксировать в runbook — «смотреть errors, не только exit code» |
| G5 | `review_catalog_change` не проверяет статус run (approve возможен в отменённом; apply всё равно блокируется) | Низкая: безвредно, но стоит решение «запретить review вне running» |
| G6 | `taxonomy_hash` контура очереди = `b357be60…` (DB-order), не canonical `fc13be78…` | Информационно: хэш внутренне консистентен (export↔import), canonical binding гейта он не заменяет и не обязан |

## 9. Калибровка для владельца: основание для ступени 2 (real batch 10, dry-run)

Доказано на синтетике:
1. create/export/import/status/finalize работают по контракту; dry-run пишет
   ноль байт в БД; commit создаёт только `proposed` findings.
2. Двойная валидация результата (схема + домен/таксономия), `tool_type` вне
   словаря отвергается, guard-тесты реально держат проверки (mutation probe).
3. Идемпотентность повторного импорта; отмена batch не меняет каталог
   (хэш-доказательство); apply без модерации невозможен; изменение товара
   после export детектируется (stale snapshot).
4. Regression без третьего падения.

Предлагаемая планка перехода (решение за владельцем):
- **Достаточно для real batch 10 в режиме dry-run уже сейчас**: dry-run по
  иерархии риска ниже доказанного здесь synthetic commit + cancel — каталог
  dry-run не меняет по построению (0 записей, доказано дважды).
- **До первого commit на реальных данных** (ступень 3): получить решения по
  G1 (сверка имени файла) и G3 (команда отмены), принять G2/G4 как документированные
  свойства, подтвердить, что `allowed_options` экспорта соответствуют canonical
  manifest (328 опций — совпало по числу; сверка хэшей — G6).

## 10. Состояние для продолжения

- Песочница `proff58_phase8` сохранена as-is (8 синтетических товаров, runs §2;
  аудит: 2 rejected findings run `22b4f0d1`, 2 rejected run `8cc21405`,
  2 invalid/run_not_running run `aa41cc90`, items 1–2 последнего — `failed`).
  Удаление — отдельное решение.
- Артефакты обоих окон: `scratchpad/phase8/artifacts/` — серия параллельного
  окна (`01`–`09`, `10-regression.txt`, `N-A`, `N-B`, `C1`/`C2`,
  `fingerprint-00…10`, `export-run1/2.json`, `result-canonical.json`) и серия
  этого окна (`10-create-r3`…`18`, `20`–`23`, `30`–`33`, `40`–`41`, `50`, `60`,
  `regression-full.log`); скрипты `seed_synthetic.py`, `catalog_fingerprint.py`,
  `env.sh`, `make_result.py`, `make_negatives.py`, `run_mutations.py`,
  `run_negatives.sh` в `scratchpad/phase8/`.
- Испорченные файлы матрицы этого окна удалены (`inbox/ph8-tmp/`); у
  параллельного окна остались `scratchpad/phase8/tmp-negatives/` и
  `artifacts/negatives/` — оставлены его владельцу.
- Ступень 2 НЕ начиналась.

---

## 11. Приложение окна B (артефакты серии `01`–`09`, `10-regression`, `13-runs-state`)

Дописано вторым окном после сведения протокола. Ничего не перезаписывает —
только добавляет пруфы, которых нет выше.

### 11.1 Арифметика regression: доказательство, что тесты не «потерялись»

Δ passed = −7 относительно baseline 1941 объяснена в §6 состоянием дерева.
Дополнительное машинное подтверждение, что дельта не создана прогоном:

```
$ uv run pytest -p no:pylama --collect-only -q | tail -1
1937 tests collected in 2.67s
```

`2 failed + 1934 passed + 1 skipped = 1937` — прогон покрыл **весь** собранный
набор, ни один тест не был пропущен молча.

```
$ git status --short --untracked-files=no
(пусто)
$ git merge-base --is-ancestor HEAD 71cb035   # HEAD 3f50376
да
```

То есть локальный HEAD — предок того `origin/dev`, на котором мерился baseline;
за окно не изменён ни один отслеживаемый файл, поэтому окно физически не могло
убрать 7 тестов. `git diff --stat HEAD origin/dev` по тестовым путям:
+1397/−122 строк (`apps/promotions/tests/*`, `apps/reviews/tests/test_reviews.py`,
`apps/catalog/tests/test_h5_negative_matrix.py`, `apps/catalog/test_attribute_extract.py`,
`apps/orders/tests/test_cart_promo_api.py`, `apps/core/tests/test_theme_api.py`).

### 11.2 Детерминированность export — численно (run `8cc21405`)

| Прогон | EXIT | `checksum` в файле | sha256 файла | sha256 payload без `exported_at` |
|---|---|---|---|---|
| 1 | 0 | `b5dfb8655b555f05…e916bed01` | `a9288753daeb5aee…40c1b796` | `5bd9ce089247e57c…8d7a86ca` |
| 2 | 0 | `b5dfb8655b555f05…e916bed01` | `1d8bb87671a36e83…090a042a` | `5bd9ce089247e57c…8d7a86ca` |

`exported_at`: `2026-07-27T09:06:55.058663+00:00` против `…09:07:06.235765+00:00` —
единственный источник расхождения (отклонение G2). Файлы сохранены целиком:
`artifacts/export-run1.json`, `artifacts/export-run2.json`.

### 11.3 Идемпотентность `catalog_queue_create`

- тот же ключ + тот же scope → `Run с таким idempotency key уже существует:
  8cc21405-…`, EXIT=0, второй run не создан (`artifacts/11-create-idempotent.txt`);
- тот же ключ + другой scope (`--explicit-ids 1,2`) → `CommandError: Idempotency
  key уже используется run с другим scope.`, EXIT=1
  (`artifacts/12-create-key-conflict.txt`).

### 11.4 Изоляция от dev-БД — проверено read-only

```
dev-БД proff58: товаров всего 47226
dev-БД proff58: товаров с маркером PH8-SYN 0
пересечение run окна B с CatalogProcessingRun dev-БД: []
```

Ни один синтетический товар и ни один run ступени в dev-БД не попал.
Staging не трогался вообще.

### 11.5 Дамп состояния run

`artifacts/13-runs-state.json` — полный снимок четырёх run окна B
(`8cc21405`, `aa41cc90`, `08b74147`, `5ecbf02e`) с `status`, `scope`, `stats`,
`taxonomy_hash`, всеми `input_hash`/`baseline_hashes` items и всеми
`CatalogChange` (id, статус, `proposed_value`, `idempotency_key`). Снят до
завершения параллельного окна — служит контрольной точкой на случай утраты
песочницы.

### 11.6 Коммиты

**Локальных коммитов не создано — намеренно.** Основания:
1. ни один отслеживаемый файл не изменён (`git status --untracked-files=no` пуст),
   коммитить в коде нечего;
2. `scratchpad/` в этом репозитории **никогда не коммитился**
   (`git ls-files scratchpad/` → 0 файлов), это рабочая область, а не артефакт
   истории;
3. каталог `scratchpad/phase8/` содержит файлы двух окон одновременно; коммит
   затянул бы в историю чужие незавершённые файлы.

Если владелец решит зафиксировать протокол в истории, безопасная команда —
точечная и без чужих временных файлов:

```bash
git add scratchpad/phase8/phase8-step1-report.md \
        scratchpad/phase8/*.py scratchpad/phase8/env.sh scratchpad/phase8/run_negatives.sh
git commit -m "docs(catalog): протокол Phase 8 ступень 1 — synthetic batch"
```
