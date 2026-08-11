# Task 7 / Phase 7A — current-state corpus extraction + analyst-curated candidate rules

> **Статус:** Proposed v2, 2026-07-21. Документ — план выполнения для ревью
> ПЕРЕД запуском. Phase 7A не авторизована; старт только после явного
> разрешения пользователя по итогам ревью этого плана.
>
> **Amendment log:**
> - v1 → v2 (ревью пользователя 2026-07-21): P0 — `corpus_id`
>   content-addressed вместо hardcode; `expected_recall` только через
>   human approval (никогда не вычисляется автоматически из measured);
>   Corpus Summary разделяет `source_group` и `category_id`. P1 —
>   byte-identical idempotency check; разделение schema/data/ruleset
>   version; Facts hash = зафиксированный aggregate canonical hash
>   (Merkle-like); ambiguous groups с колонками
>   brand/source_group/category/label/count. P2 — Performance Summary;
>   Human Decision Log.

**Goal:** извлечь current-state training corpus (P0.1) из staging БД строго
read-only и подготовить analyst-curated candidate ruleset v1 с derivation
report — с нулем записей в каталог и с данными, достаточными для
data-quality ревью.

**Architecture:** два контура. Staging-контур (только SELECT в одной
REPEATABLE READ READ ONLY транзакции) производит corpus-артефакт и
extraction report. Локальный контур (без БД) валидирует артефакт через
существующий `load_corpus`, строит Corpus Summary и data-quality отчёт,
готовит draft ruleset + derivation doc. Commit в репозиторий — только
после human review каждого правила пользователем.

**Tech Stack:** staging (`ssh taximeter@194.87.99.126`,
`/home/taximeter/proff58-staging`, ТОЛЬКО `docker compose -f
docker-compose.prod.yml`; web `proff58_staging-web-1`, db
`proff58_staging-db-1`); локально — `./.venv/Scripts/python.exe`,
`apps.catalog.rules_engine.load_corpus`, `canonical_hash`.

## Global Constraints

- Task 7 на 100% наблюдательный: разрешены read-only SELECT, snapshot
  extraction, построение corpus, analyst review, генерация candidate
  rules, создание артефактов.
- ЗАПРЕЩЕНЫ: любые UPDATE/INSERT/DELETE; изменение `tool_type`,
  `AttributeOption`, `attrs_cache`; импорт результатов; создание runs
  или `CatalogChange`; изменение feature flag (остаётся `False` всё
  время, recreate web не требуется); deploy; новые live catalog runs.
- Baseline observations (2026-07-21, перепроверяются свежим SELECT в
  Stage 0, не являются вечными): PAV total = 60 896; tool_type options =
  328; raw applied changes (`status=applied`, `target_kind="tool_type"`)
  = 56; distinct products = 54; current-label corpus = 54;
  historical-label collisions = 2 (12957/12959); незавершённых changes
  (`proposed`/`approved`) = 0; batch-50 run
  `aa9b1df5-41c5-4b10-a6d8-957c2ff57aa9` и remediation run
  `3afffd16-005a-4f73-95fd-d068aa725391` — `completed`.
- Staging ожидается на `dev@175d96a` (post-merge deploy #580 завершён
  успехом); staging SHA подтверждается в Stage 0.
- Хост медленный: каждый `docker exec ... manage.py` занимает 2–4
  минуты — таймауты команд ≥ 280 с, число обращений минимизировано.
- Replay на applied-корпусе — только regression-check, НЕ gate
  (training leakage); gate 6.1 требует ≥ 100 независимых predictions и
  относится к Phase 7B+.

---

## 1. Цели Task 7

### Создаются

| Артефакт | Где | Когда |
|---|---|---|
| `applied_corpus_tool_type.v1.json` | staging `/app/logs/` + локально `scratchpad/phase7a/` | Stage 1 |
| `extraction_report.json` (pre/post инварианты, baseline SELECT, deviations, exclusions, оба прогона, Performance Summary §6.2) | локально `scratchpad/phase7a/` | Stages 0–5 |
| `corpus_summary.md` (Corpus Summary + data-quality review flags) | локально | Stage 5 |
| `docs/catalog/phase6-ruleset-v1-derivation.md` (draft, с Human Decision Log) | локально | Stage 6 |
| `tool_type.v1.json` ruleset (draft) + `ruleset_hash` | локально | Stage 6 |
| replay-результат (`measured_recall`, mismatches) — informational, НЕ gate | локально | Stage 6 |
| repo fixtures: corpus + ruleset + `test_rules_corpus_replay.py` + derivation doc | репозиторий, PR | Stage 7, ПОСЛЕ approval |

Опционально (Task 1, отдельный микро-PR до extraction): четыре deferred
code minors из ревью #579/#580 — см. Task 1. Это единственная задача с
изменением кода; она не трогает каталог и может быть вычеркнута
пользователем без влияния на остальной план (тогда правила пишутся без
`negative_keywords`).

### Не создаются

- Любые записи в БД staging (каталог, processing-таблицы, audit).
- Новые runs, `CatalogChange`, `ContentFinding`, импорт чего-либо.
- Gate sample / gate labels (это Phase 7B).
- Shadow-прогоны по пулу (это Phase 7B).
- Deploy, изменения feature flag, recreate контейнеров.
- Автоматический rule mining (детерминированный miner не обещается —
  деривация analyst-curated, P1.3).

---

## 2. Контракты входных данных

### Источник

Staging PostgreSQL через Django ORM в `manage.py shell` на
`proff58_staging-web-1`. Никаких прямых коннектов к БД вне контейнера;
никаких изменений `.env`/compose.

### Snapshot policy

Весь extraction выполняется в ОДНОЙ транзакции
`REPEATABLE READ READ ONLY` (паттерн `catalog_rules_shadow`): все
SELECT'ы видят один снимок данных; `extracted_at` фиксируется один раз.
Транзакция read-only на уровне SQL — записи невозможны даже при ошибке
скрипта.

### Критерии включения (строка corpus)

Товар включается, ЕСЛИ выполнены все условия:

1. у товара есть ≥ 1 `CatalogChange` со `status="applied"`,
   `target_kind="tool_type"`;
2. у товара есть текущий tool_type PAV с `value_option IS NOT NULL`
   (источник истины о текущем label);
3. существует provenance: ПОСЛЕДНИЙ applied change, чей
   `after_value->>"option_slug"` равен slug текущего PAV.

### Критерии исключения (фиксируются в `exclusions`)

| Случай | reason |
|---|---|
| applied changes есть, текущего PAV нет | `no_current_pav` |
| текущий PAV есть, но ни один applied change не совпадает с его slug | `no_provenance_for_current_label` |

Исключённые товары НЕ попадают в corpus, но попадают в отчёт с
`product_id` и причиной. Ожидание: 0 exclusions; порог аномалии —
более 2 (см. Failure Matrix, F7).

### Historical-label collisions

Если среди applied changes товара есть change с
`after_value.option_slug != текущему slug` — это НЕ ошибка, а
историческая смена label (кейс 12957/12959 после ADR-0011
remediation). Счётчик `historical_label_collisions` ожидается = 2.

### Контракт строки corpus

По `apps/catalog/schemas/applied_tool_type_corpus_v1.json`:
`product_id`, `change_id` (строка PK provenance-change), `pav_id`,
`source`, `confidence`, `applied_at`, `applied_option_slug`, snapshot
фактов (`name`, `original_name`, `brand`, `source_group`, `article`) и
`facts_hash = canonical_hash(пять фактов)`.

---

## 3. Pipeline

Стадии выполняются строго последовательно; каждая стадия завершается
проверкой, при нарушении — переход в Failure Matrix.

- **Stage 0 — pre-checks (staging).** SSH доступен; `/healthz/` → 200;
  `FEATURE_CATALOG_PROCESSING=False`; staging SHA = `dev@175d96a`;
  свежий backup (gzip integrity + pg_dump marker + SHA-256);
  baseline SELECT'ы (PAV total, options count, applied counters,
  non-final changes = 0, статусы двух runs). Сверка с Global
  Constraints; расхождения — по Failure Matrix.
- **Stage 1 — extraction.** Скрипт (полный код — Task 3) доставляется в
  контейнер, выполняется в REPEATABLE READ READ ONLY, пишет
  `/app/logs/applied_corpus_tool_type.v1.json` атомарно (tmp +
  `os.replace`). Печатает counters, exclusions, sha256.
- **Stage 2 — idempotency re-run (byte-identical).** Копия run1
  забирается локально, staging-файл удаляется, extraction повторяется в
  то же имя; byte-сравнение: единственная допустимая разница — строка
  `extracted_at`; `corpus_hash` и `corpus_id` обязаны совпасть. Иначе
  → F9.
- **Stage 3 — transfer + локальная валидация.** Артефакт забирается
  локально; `load_corpus` (JSON Schema, уникальность product_id,
  counters, пересчёт facts_hash) — принятие или F8.
- **Stage 4 — category distribution.** Малый read-only SELECT на
  staging: распределение corpus product_id по `category_id` (для поля
  «Catalog categories» Corpus Summary, §6.3).
- **Stage 5 — Corpus Summary + data-quality отчёт.** Все поля
  контракта пользователя (§6) + review flags (§8).
- **Stage 6 — analyst-curated derivation.** Draft ruleset + negative
  fixtures + derivation doc; локальные проверки: `load_ruleset`,
  `check_negative_fixtures`, `validate_against_taxonomy` (против
  export'а options со staging из Stage 0), `derived_from ⊆ corpus IDs`;
  replay recall (informational, НЕ gate).
- **Stage 7 — STOP → ревью пользователя.** Corpus Summary + derivation
  + каждое правило. После явного approval: repo fixtures + replay-тест
  + PR + CI; merge — по слову пользователя.

---

## 4. Инварианты

Разделяем **инвариант** (что именно проверяется — постоянная часть
процесса) и **baseline текущего запуска** (ожидаемые значения; для
будущих итераций пересчитываются свежим SELECT, документ не
переписывается).

### Инварианты (проверяются pre/post каждым staging-обращением)

- `ProductAttributeValue` total НЕ меняется за время выполнения;
- tool_type `AttributeOption` count НЕ меняется (PK/value/slug/
  sort_order не сверяются построчно — count + отсутствие операций);
- counts `Product`, `CatalogChange`, `CatalogProcessingRun`,
  `CatalogProcessingItem`, `ContentFinding` НЕ меняются;
- содержимое завершённых runs и их items/changes НЕ меняется;
- `FEATURE_CATALOG_PROCESSING=False` всё время; состав контейнеров и
  образов не меняется;
- `/healthz/` → 200 после завершения.

### Baseline текущего запуска (2026-07-21)

| Метрика | Ожидание |
|---|---|
| PAV total | 60 896 |
| tool_type options | 328 |
| raw applied changes (`status=applied`, `target_kind="tool_type"`) | 56 |
| distinct products | 54 |
| current-label corpus | 54 |
| historical-label collisions | 2 (12957/12959) |
| незавершённые changes (`proposed`/`approved`) | 0 |
| batch-50 run `aa9b1df5-…` / remediation run `3afffd16-…` | `completed` / `completed` |

Запрещённые операции: см. Global Constraints (любые writes, flag,
deploy, runs, import). Разрешённые: SELECT, чтение файлов, запись
артефактов в `/app/logs/` (staging) и `scratchpad/phase7a/` (локально).

---

## 5. Failure Matrix

| # | Сбой | Детекция | Действие | Артефакты после | Возобновление |
|---|---|---|---|---|---|
| F1 | SSH/staging недоступен | pre-check | STOP до начала | нет | повтор после восстановления |
| F2 | `/healthz/` ≠ 200 | pre-check | STOP | incident note в отчёте | после инфра-разбора |
| F3 | staging SHA ≠ `dev@175d96a` | pre-check | STOP | нет | deploy-разбор (отдельная авторизация) |
| F4 | drift инвариантов (counts ≠ baseline §4: PAV/options/counts изменились, runs тронуты) | baseline SELECT | STOP | drift report | решение пользователя |
| F5 | есть `proposed`/`approved` changes (> 0) | baseline SELECT | STOP | drift report | расследование, не должно случиться после finalize |
| F6 | applied counters ≠ 56/54 при чистом final state | baseline SELECT | ПРОДОЛЖИТЬ: отклонение + объяснение в extraction report | deviation note | data finding, не инфра-сбой |
| F7 | exclusions > 2 | extraction output | STOP, corpus НЕ публикуется | exclusions report | решение пользователя |
| F8 | `load_corpus` отклоняет артефакт (schema, дубли product_id, counters, facts_hash) | Stage 3 | corpus НЕ принят; диагностика скрипта (bug) | rejected artifact + лог | исправление скрипта, повтор Stage 1–3 |
| F9 | файлы двух прогонов различаются более чем строкой `extracted_at` (byte-diff), либо разные `corpus_hash`/`corpus_id` | Stage 2 byte-compare | STOP: расследование (live writes? bug) | оба файла + diff | решение пользователя |
| F10 | exception в середине extraction | traceback | tmp удалён, published artifact отсутствует | лог | диагностика, повтор |
| F11 | `measured_recall` ниже приемлемого для analyst уровня | Stage 6 | итерация деривации (рабочий цикл); если после итераций measured < 0.90 — STOP перед ревью | derivation с честным measured | решение пользователя |

Автоматический restore БД не выполняется НИКОГДА (записей не было —
восстанавливать нечего); backup Stage 0 — страховка протокола.

---

## 6. Выходные артефакты

### 6.1 `applied_corpus_tool_type.v1.json`

Schema `applied_tool_type_corpus_v1.json`. Поля: `version=1`,
`corpus_id`, `extracted_at`, `source="staging"`, `counters`
(4 счётчика), `items` (контракт §2). Хэши в отчёте: `sha256` файла и
`corpus_hash = canonical_hash(doc без "extracted_at")`.

**Разделение версий (review P1-5)** — три независимых понятия, ни одно
не переопределяет другое:

| Версия | Где живёт | Значение |
|---|---|---|
| `schema_version` | поле `version` артефакта | `1` (const схемы; меняется только со сменой JSON Schema) |
| `data_version` | поле `corpus_id` | content-addressed: `staging-tool-type-<canonical_hash(content без extracted_at)[:12]>` — уникален и воспроизводим (review P0-1); полная provenance (staging SHA, backup SHA-256, timestamps прогонов) — в extraction report |
| `ruleset_version` | `ruleset_id` ruleset | `tool_type.v1`; до human approval в `note` ruleset стоит `draft, pending human approval 2026-07-21` |

Схемы НЕ расширяются (обе имеют `additionalProperties: false` —
новых полей в артефакты не добавляем). Repo-fixture ПОСЛЕ approval =
то же содержимое + `expected_recall` (значение, утверждённое
человеком — см. §6.4); оба хэша фиксируются в derivation doc.

### 6.2 `extraction_report.json`

Pre/post инварианты (все значения §4), baseline SELECT'ы, отклонения от
ожиданий с объяснениями, `exclusions`, хэши и длительности обоих
прогонов, staging SHA, backup SHA-256.

**Performance Summary (review P2-8)** — обязательный блок отчёта
(пригодится при масштабировании на полный пул в Phase 7B):

| Метрика | Источник |
|---|---|
| `extraction_seconds` (run1, run2) | timestamps вокруг `manage.py shell` вызова |
| `validation_seconds` | время `load_corpus` локально |
| `replay_seconds` | время replay (Task 6 Step 4) |
| `derivation_hours` | учёт analyst-времени Stage 6 |
| `peak_ram_mb` | `docker stats --no-stream --format "{{.MemUsage}}" proff58_staging-web-1` сразу после extraction |
| `corpus_size_bytes` | размер файла артефакта |

### 6.3 `corpus_summary.md` — обязательные поля

Ровно в таком виде (интерпретации зафиксированы для ревью):

```
Corpus Summary
Всего товаров: <distinct_products — товары с applied changes>
Всего product_id: <current_label_corpus — строк corpus>
Source groups: <distinct source_group> + распределение count/share по каждой
Catalog categories: <distinct category_id (Stage 4 SELECT)> + распределение count/share
Tool types: <distinct applied_option_slug> + распределение count/share по каждому
Unknown: <exclusions: no_current_pav + no_provenance, count и доля>
Duplicate product_id: 0
Facts hash: <aggregate canonical hash (Merkle-like, review P1-6):
             canonical_hash(отсортированный список per-item facts_hash);
             алгоритм фиксирован этим документом, замена = новая версия отчёта>
Corpus hash: <corpus_hash> / sha256: <sha256 файла>
Corpus ID: <corpus_id> (content-addressed, data_version)
Rules generated: <candidate N + shadow_regression M>
Coverage: <replay recall на corpus, candidate tier> + per-rule hits
Potential collisions: <rule-коллизии на corpus> + historical label collisions (2)
Taxonomy gaps: <labels вне allowed options — ожидание 0> + validate_against_taxonomy=[]
Top ambiguous groups: <топ групп с ≥2 distinct labels; колонки каждой строки
             (review P1-7): brand | source_group | category | label | count | product IDs>
Performance: extraction <с> / validation <с> / replay <с> / derivation <ч> /
             corpus <bytes> / peak RAM <MB, docker stats> — см. §6.2
```

### 6.4 `docs/catalog/phase6-ruleset-v1-derivation.md` (draft)

На каждое candidate-правило: группа товаров (product IDs), общие
измерения (≥ 2), почему именно этот slug, negative fixture и её
источник, риски (близкие группы с другим label). Плюс: сводка
отклонений от baseline, оба хэша corpus, `measured_recall` и его
разбор.

**`expected_recall` — только через human approval (review P0-2).**
Автоматическое превращение measured → expected ЗАПРЕЩЕНО: иначе CI
можно случайно «узаконить» на ухудшенном значении. Поток строго:

```
replay → measured_recall (фиксируется в derivation doc с разбором mismatches)
       → analyst ПРЕДЛАГАЕТ expected_recall (≤ measured, с обоснованием запаса)
       → human approval (явная строка в Decision Log)
       → только тогда expected_recall записывается в repo fixture
```

Локальный draft corpus НЕ содержит `expected_recall` вовсе; поле
появляется только в repo fixture после approval.

**Human Decision Log (review P2-9)** — обязательный раздел derivation
doc; каждое решение человека по ходу Task 7 заносится строкой:

```
| Decision | Reason | Timestamp (UTC) |
|---|---|---|
| corpus run accepted (corpus_id) | hash stable, counters сверены, exclusions=0 | ... |
| expected_recall = 0.9x | measured 0.9y, запас на ... | ... |
| rule tt-xxx approved / rejected | ... | ... |
| deviation F6 accepted | ... | ... |
```

Лог ведётся при evolution ruleset: любая будущая правка правил
добавляет строки, не переписывая историю.

### 6.5 `tool_type.v1.json` (draft)

Schema `tool_type_ruleset_v1.json`. `ruleset_hash = canonical_hash`
фиксируется в derivation doc. Правила удовлетворяют P0.2 (≥ 2 непустых
измерения, ≥ 2 уникальных product ID в `derived_from`, keyword ≥ 3
символов после normalize, уникальность в измерении, keyword-only только
`shadow_regression`, ≥ 1 rule-scoped negative fixture на candidate).

### 6.6 Repo fixtures (только после approval Stage 7)

`data/catalog_processing_rules/applied_corpus_tool_type.v1.json`,
`data/catalog_processing_rules/tool_type.v1.json`,
`docs/catalog/phase6-ruleset-v1-derivation.md`,
`apps/catalog/tests/test_rules_corpus_replay.py` (recall ≥
expected_recall; taxonomy check; fixture coverage — выполняется
loader'ом).

---

## 7. Acceptance Criteria

### Phase 7A успешна, ЕСЛИ все условия выполнены

1. Corpus проходит `load_corpus` без единой ошибки;
   `duplicate product_id = 0`.
2. Counters совпали со свежими baseline SELECT, либо каждое отклонение
   задокументировано с объяснением (F6).
3. Файлы двух прогонов байт-в-байт идентичны вне строки `extracted_at`
   (ровно одна volatile-строка); `corpus_hash` и `corpus_id`
   совпадают.
4. `exclusions ≤ 2`, каждая с `product_id` и объяснённой причиной.
5. Zero-writes доказан: все инварианты §4 идентичны pre/post;
   `/healthz/` → 200; flag `False` не менялся.
6. `corpus_summary.md` содержит ВСЕ поля §6.3 и review flags §8.
7. Каждое candidate-правило: ≥ 2 измерения, ≥ 2 уникальных product ID
   в `derived_from`, ≥ 1 rule-scoped fixture, обоснование в derivation
   doc; `derived_from ⊆ corpus product_ids` (автопроверка).
8. `validate_against_taxonomy == []`, `check_negative_fixtures == []`;
   `measured_recall` измерен и разобран; `expected_recall` УТВЕРЖДЁН
   пользователем явно (строка в Decision Log) — никогда не вычислен
   автоматически из measured.
9. Явное подтверждение пользователя по КАЖДОМУ правилу (human review)
   — до commit'а ruleset.

### Phase 7A автоматически failed, ЕСЛИ

- обнаружен любой write в БД или drift любого инварианта §4;
- schema violation, duplicate product_id, byte-diff вне
  `extracted_at`, разные `corpus_hash`/`corpus_id`;
- exclusions > 2 или exclusion без объяснения;
- `derived_from ⊄ corpus` (leakage);
- candidate-правило без обоснования или нарушающее P0.2;
- `expected_recall` записан в fixture без строки human approval в
  Decision Log;
- staging SHA ≠ `dev@175d96a` на момент extraction.

---

## 8. Review flags (data-quality, для ревью пользователя)

Corpus Summary обязан адресовать каждый пункт; совпадение с ожиданием
НЕ является автоматическим fail, но требует письменного разбора:

1. **Дисбаланс tool_type** — распределение count/share по slug;
   флагируются slug с долей > 30% и slug с 1–2 товарами.
2. **Unknown** — доля exclusions; любая > 0 требует разбора.
3. **Неоднозначность** — число ambiguous-групп и их размер; флаг при
   любой группе ≥ 5 товаров с разными labels при похожих facts.
4. **Слишком узкие правила** — правила с ровно 2 product ID в
   `derived_from` помечаются `narrow`; их доля в отчёте.
5. **Leakage** — автопроверка `derived_from ⊆ corpus IDs`; напоминание:
   replay recall НЕ доказывает precision; gate 6.1 — только на
   независимой выборке (Phase 7B).
6. **Подозрительно высокое покрытие** — recall = 1.0 обязан иметь
   разбор (overfitting check: правила, у которых hits == |derived_from|,
   помечаются).
7. **facts_hash vs статистика** — подтверждение пересчёта всех
   facts_hash через `load_corpus`; расхождений быть не может (F8).
8. **Стабильность corpus_hash** — два прогона, сравнение (F9).

---

## Tasks

### Task 1 (опционально, отдельный микро-PR): deferred code minors

Единственная задача с изменением кода. Состав (подтверждается
пользователем; любой пункт может быть вычеркнут):

1. `counts` shadow-отчёта: сводные `candidate_rules`/`regression_rules`
   (ревью #579).
2. `_load_json`: widening до `OSError` — missing replay-corpus/входной
   файл даёт `CommandError`, а не сырой traceback (ревью #579/#580).
3. Semantic validator: минимальная длина `negative_keywords` в токенах
   (симметрия с positive keywords ≥ 3 символов после normalize) —
   влияет на семантику правил; до merge этого пункта правила в Task 6
   пишутся БЕЗ `negative_keywords` (негативную нагрузку несут fixtures).
4. Rollback restore: `self.stderr.write` при неудачном `os.replace`
   backup (ревью #580; сейчас молчаливый best-effort).

Каждый пункт — TDD (failing test → fix), один PR, CI, ревью, merge по
слову пользователя. Блокирует ли extraction: НЕТ; блокирует только
использование `negative_keywords` в правилах (пункт 3).

### Task 2: Stage 0 — pre-checks + backup (staging, read-only)

- [ ] **Step 1: SSH + health + flag + SHA**

```bash
ssh taximeter@194.87.99.126 "
  cd /home/taximeter/proff58-staging &&
  grep FEATURE_CATALOG_PROCESSING .env &&
  docker exec proff58_staging-web-1 python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz/'); print('healthz 200')\" &&
  (docker exec proff58_staging-web-1 git rev-parse HEAD 2>/dev/null || docker inspect proff58_staging-web-1 --format '{{.Image}}')"
```

Ожидание: `FEATURE_CATALOG_PROCESSING=False` (пустое значение =
False — сверить с действующим `.env`), `healthz 200`, SHA = `175d96a`
(или image digest соответствует deploy run #580). Иначе → F2/F3.

- [ ] **Step 2: Backup**

```bash
ssh taximeter@194.87.99.126 "
  cd /home/taximeter/proff58-staging &&
  mkdir -p backups &&
  docker exec proff58_staging-db-1 pg_dump -U proff_staging proff_staging | gzip > backups/pre_phase7a_\$(date +%Y%m%d_%H%M%S).sql.gz &&
  ls -t backups/pre_phase7a_*.sql.gz | head -1 | xargs -I{} sh -c 'gzip -t {} && zcat {} | tail -3 | grep -c \"PostgreSQL database dump complete\" && sha256sum {}'"
```

Ожидание: gzip OK, marker = 1, SHA-256 записывается в extraction report.

- [ ] **Step 3: Baseline SELECT'ы** (один `manage.py shell` вызов)

```python
from apps.catalog.models import (AttributeOption, CatalogChange,
    CatalogProcessingRun, Product, ProductAttributeValue)
from apps.ai.models import ContentFinding
print("pav_total", ProductAttributeValue.objects.count())                       # 60896
print("options", AttributeOption.objects.filter(attribute__slug="tool_type").count())  # 328
qs = CatalogChange.objects.filter(status="applied", target_kind="tool_type")
print("raw_applied", qs.count())                                                # 56
print("distinct_products", qs.values("product_ref").distinct().count())         # 54
print("non_final", CatalogChange.objects.filter(status__in=["proposed", "approved"]).count())  # 0
print("products", Product.objects.count())
print("changes_total", CatalogChange.objects.count())
print("runs_total", CatalogProcessingRun.objects.count())
print("batch50", CatalogProcessingRun.objects.get(pk="aa9b1df5-41c5-4b10-a6d8-957c2ff57aa9").status)      # completed
print("remediation", CatalogProcessingRun.objects.get(pk="3afffd16-005a-4f73-95fd-d068aa725391").status)  # completed
print("findings", ContentFinding.objects.count())
```

Сверка с Global Constraints → drift: F4/F5; counters ≠ 56/54 при
чистом состоянии: F6 (продолжить с фиксацией).

### Task 3: Stage 1 — extraction (staging, REPEATABLE READ READ ONLY)

- [ ] **Step 1: локально сохранить скрипт** `scratchpad/phase7a/extract_corpus.py`:

```python
import hashlib, json, os, tempfile
from django.db import connection, transaction
from django.utils import timezone
from apps.catalog.models import CatalogChange, ProductAttributeValue
from apps.catalog.processing import canonical_hash

OUT = "/app/logs/applied_corpus_tool_type.v1.json"

with transaction.atomic():
    with connection.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    extracted_at = timezone.now().isoformat()
    applied = (CatalogChange.objects
               .filter(status="applied", target_kind="tool_type")
               .order_by("product_ref", "applied_at", "pk"))
    by_product = {}
    for ch in applied:
        by_product.setdefault(ch.product_ref, []).append(ch)

    pav_by_product = {
        p.product_id: p
        for p in (ProductAttributeValue.objects
                  .filter(product_id__in=list(by_product),
                          attribute__slug="tool_type",
                          value_option__isnull=False)
                  .select_related("value_option", "product"))
    }
    items, collisions, exclusions = [], 0, []
    for pid in sorted(by_product):
        changes = by_product[pid]
        pav = pav_by_product.get(pid)
        if pav is None:
            exclusions.append({"product_id": pid, "reason": "no_current_pav"})
            continue
        slug = pav.value_option.slug
        if any((c.after_value or {}).get("option_slug") != slug for c in changes):
            collisions += 1
        current = next(
            (c for c in reversed(changes)
             if (c.after_value or {}).get("option_slug") == slug),
            None,
        )
        if current is None:
            exclusions.append({"product_id": pid,
                               "reason": "no_provenance_for_current_label"})
            continue
        p = pav.product
        facts = {"name": p.name or "", "original_name": p.original_name or "",
                 "brand": p.brand or "", "source_group": p.source_group or "",
                 "article": p.article or ""}
        items.append({
            "product_id": pid, "change_id": str(current.pk), "pav_id": pav.pk,
            "source": pav.source or "", "confidence": pav.confidence,
            "applied_at": current.applied_at.isoformat() if current.applied_at else "",
            "applied_option_slug": slug, **facts,
            "facts_hash": canonical_hash(facts),
        })
    # corpus_id — content-addressed (review P0-1): уникален и воспроизводим.
    # Считается ДО вставки по содержимому без volatile extracted_at:
    # одинаковые данные → одинаковый corpus_id при любом перезапуске.
    doc = {"version": 1, "extracted_at": extracted_at, "source": "staging",
           "counters": {
               "raw_applied_changes": sum(len(v) for v in by_product.values()),
               "distinct_products": len(by_product),
               "current_label_corpus": len(items),
               "historical_label_collisions": collisions,
           },
           "items": items}
    content_hash = canonical_hash({k: v for k, v in doc.items() if k != "extracted_at"})
    doc["corpus_id"] = f"staging-tool-type-{content_hash[:12]}"
    payload = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True)
    fd, tmp = tempfile.mkstemp(dir="/app/logs", prefix="corpus.", suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        fh.write(payload.encode("utf-8"))
    os.replace(tmp, OUT)
    print("corpus_id:", doc["corpus_id"])
    print("counters:", json.dumps(doc["counters"], sort_keys=True))
    print("exclusions:", json.dumps(exclusions, ensure_ascii=False))
    print("corpus_hash:", canonical_hash({k: v for k, v in doc.items() if k != "extracted_at"}))
    print("sha256:", hashlib.sha256(payload.encode("utf-8")).hexdigest())
```

- [ ] **Step 2: доставка и запуск** (таймаут ≥ 280 с)

```bash
scp scratchpad/phase7a/extract_corpus.py taximeter@194.87.99.126:/tmp/
ssh taximeter@194.87.99.126 "
  docker cp /tmp/extract_corpus.py proff58_staging-web-1:/app/logs/extract_corpus.py &&
  docker exec proff58_staging-web-1 python manage.py shell < /app/logs/extract_corpus.py" \
  > scratchpad/phase7a/extract_run1.log 2>&1
```

Примечание: `manage.py shell` читает скрипт из stdin через перенаправление
внутри контейнера (файл уже в `/app/logs/`); вывод — counters,
exclusions, corpus_hash, sha256. Проверка: counters по ожиданиям
(56/54/54/2 или задокументированное F6), exclusions → F7 при > 2.

### Task 4: Stage 2 — idempotency re-run (byte-identical, review P1-4)

Проверяются ДВА свойства: (а) повторный extraction на неизменных
данных создаёт файл с тем же содержимым, что и первый, с точностью до
единственной объявленной volatile-строки `extracted_at`; (б)
`corpus_hash` обоих прогонов равен (F9). `corpus_id` (content-addressed)
воспроизводится идентично — это часть проверки.

- [ ] **Step 1: забрать копию run1 сразу после Task 3**

```bash
ssh taximeter@194.87.99.126 "docker exec proff58_staging-web-1 cat /app/logs/applied_corpus_tool_type.v1.json" > scratchpad/phase7a/corpus_run1.json
```

- [ ] **Step 2: удалить файл на staging и повторить extraction в то же
  имя** (таймаут ≥ 280 с):

```bash
ssh taximeter@194.87.99.126 "
  docker exec proff58_staging-web-1 rm /app/logs/applied_corpus_tool_type.v1.json &&
  docker exec proff58_staging-web-1 python manage.py shell < /app/logs/extract_corpus.py" \
  > scratchpad/phase7a/extract_run2.log 2>&1
ssh taximeter@194.87.99.126 "docker exec proff58_staging-web-1 cat /app/logs/applied_corpus_tool_type.v1.json" > scratchpad/phase7a/corpus_run2.json
```

- [ ] **Step 3: byte-identical сравнение.** Единственная допустимая
  разница — строка `extracted_at`:

```bash
diff scratchpad/phase7a/corpus_run1.json scratchpad/phase7a/corpus_run2.json | grep -c '^[<>]'
# ожидание: ровно 2 (строка extracted_at с обеих сторон)
diff <(grep -v '"extracted_at"' scratchpad/phase7a/corpus_run1.json) \
     <(grep -v '"extracted_at"' scratchpad/phase7a/corpus_run2.json) | wc -l
# ожидание: 0 — байт-в-байт идентичны вне volatile-строки
```

Любой другой diff, отличный `corpus_id` или отличный `corpus_hash` →
F9 (STOP). Оба прогона (sha256, corpus_hash, длительности) — в
extraction report; локальные копии run1/run2 остаются в
`scratchpad/phase7a/` как evidence, staging-файл после Task 5 — это
файл run2 (содержимое идентично run1 вне volatile-строки).

### Task 5: Stages 3–5 — transfer, валидация, Corpus Summary

- [ ] **Step 1: забрать артефакт локально**

```bash
ssh taximeter@194.87.99.126 "docker exec proff58_staging-web-1 cat /app/logs/applied_corpus_tool_type.v1.json" > scratchpad/phase7a/applied_corpus_tool_type.v1.json
```

- [ ] **Step 2: локальная валидация (F8 gate)**

```bash
./.venv/Scripts/python.exe -c "
from apps.catalog.rules_engine import load_corpus
c = load_corpus('scratchpad/phase7a/applied_corpus_tool_type.v1.json')
print('items', len(c.items), 'counters OK, facts_hash OK, unique OK')"
```

(требует `DJANGO_SETTINGS_MODULE=config.settings.dev` — как для pytest;
любая ошибка → F8.)

- [ ] **Step 3: category distribution (staging, read-only)**

```python
from apps.catalog.models import Product
ids = [<product_id из corpus>]  # подставляется скриптом из локального файла
from collections import Counter
print(Counter(Product.objects.filter(pk__in=ids).values_list("category_id", flat=True)))
```

(один вызов `manage.py shell`; результат — в Corpus Summary, поле
«Catalog categories»; «Source groups» считается локально из corpus.)

- [ ] **Step 4: собрать `corpus_summary.md`** по шаблону §6.3 со
  всеми review flags §8 (label distribution, unknown, ambiguous groups
  через группировку `brand+source_group+category → distinct slugs` с
  колонками `brand | source_group | category | label | count |
  product IDs`, per-slug shares). Extraction report дополняется всеми
  хэшами/длительностями.
- [ ] **Step 5: Performance Summary (§6.2) в extraction report:**
  длительности extraction run1/run2 и `load_corpus` из логов,
  `corpus_size_bytes` (`stat -c%s` / `wc -c` по файлу), peak RAM:

```bash
ssh taximeter@194.87.99.126 "docker stats --no-stream --format '{{.MemUsage}}' proff58_staging-web-1"
```

(снимок сразу после extraction; replay_seconds и derivation_hours
добавляются в отчёт по завершении Task 6).

### Task 6: Stage 6 — analyst-curated derivation + draft ruleset

- [ ] **Step 1:** группировка corpus по `brand+source_group` (+ серии
  по article/original_name) → кандидатные группы с одним доминирующим
  label; каждая группа оценивается на ≥ 2 измерения и близость к
  группам с другим label.
- [ ] **Step 2:** draft `tool_type.v1.json` (P0.2-ограничения §6.5;
  без `negative_keywords`, если Task 1.3 не в dev) + rule-scoped
  negative fixtures (источник fixture: реальный товар ambiguous-группы
  или соседнего label).
- [ ] **Step 3: локальные проверки**

```bash
./.venv/Scripts/python.exe -c "
from apps.catalog.rules_engine import (load_ruleset, check_negative_fixtures,
    validate_against_taxonomy, load_corpus)
rs = load_ruleset('scratchpad/phase7a/tool_type.v1.json')
print('ruleset_hash', rs.ruleset_hash)
assert check_negative_fixtures(rs) == []
c = load_corpus('scratchpad/phase7a/applied_corpus_tool_type.v1.json')
ids = {i.product_id for i in c.items}
bad = [r.rule_ref for r in rs.rules if not set(r.derived_from) <= ids]
assert not bad, f'derived_from вне corpus (leakage): {bad}'
print('fixtures OK, derived_from subset OK')"
```

Плюс `validate_against_taxonomy` против export'а allowed options со
staging (export делается тем же SELECT, что `catalog_rules_shadow`
читает через `_allowed_tool_type_options`; один read-only вызов).

- [ ] **Step 4: replay (informational)** — временный локальный прогон
  matcher'а по corpus (та же логика, что `Command._replay`, через
  `load_corpus`); результат — `measured_recall` с разбором mismatches
  в derivation doc. Далее строго по §6.4: analyst ПРЕДЛАГАЕТ
  `expected_recall` (≤ measured, с обоснованием запаса); автоматическая
  запись в fixture ЗАПРЕЩЕНА (review P0-2); measured < 0.90 после
  итераций → F11.
- [ ] **Step 5:** derivation doc по §6.4 (каждое правило с
  обоснованием, риски, narrow-флаги, отклонения от baseline, хэши) +
  Human Decision Log: все принятые на тот момент решения (acceptance
  corpus, отклонения F6 и т.п.) со строками
  `Decision | Reason | Timestamp (UTC)`.

### Task 7: Stage 7 — STOP → ревью пользователя → repo fixtures

- [ ] **Step 1:** отчёт пользователю: Corpus Summary (§6.3), extraction
  report, derivation doc, draft ruleset + `ruleset_hash`, replay
  recall, статус инвариантов §4, healthz. STOP.
- [ ] **Step 2 (только после явного approval каждого правила):**
  fixtures в `data/catalog_processing_rules/`, derivation doc в
  `docs/catalog/`, `test_rules_corpus_replay.py` (recall ≥
  `expected_recall`, taxonomy, fixture coverage), PR → CI → ревью →
  merge по слову пользователя.
- [ ] **Step 3:** ledger; Phase 7B (shadow runs + gate sample ≥ 100 +
  metrics) — отдельным планом/авторизацией.

---

## Self-Review

- Spec coverage: 7 разделов пользователя → §1–§7; Corpus Summary →
  §6.3 + Task 5; data-quality пункты → §8; инварианты «100%
  наблюдательный» → Global Constraints + §4; процесс 7A→ревью→7B →
  Stage 7 + Task 7 Step 3; deferred minors → Task 1.
- Placeholder scan: extraction script — полный код (Task 3); ruleset —
  analyst-curated выход Stage 6 (задокументированный процесс, не
  placeholder); `measured_recall` измеряется в Task 6 Step 4,
  `expected_recall` — только через human approval (§6.4).
- Type consistency: поля corpus ↔ `applied_tool_type_corpus_v1.json`;
  `target_kind="tool_type"` и `after_value.option_slug` сверены с
  `catalog_queue_import.py:418` и `tool_type_snapshot`
  (`processing.py:72`); `product_ref`/`applied_at` сверены с моделью
  `CatalogChange` (`models.py:1094+`); `load_corpus`/`load_ruleset`/
  `canonical_hash` — существующие API `rules_engine`/`processing`;
  новых полей в схемы не добавляется (`additionalProperties: false`,
  §6.1).
- Известные компромиссы: `extracted_at` — единственная volatile-строка,
  byte-check (P1-4) опирается на фиксированный формат выгрузки
  (`indent=2, sort_keys`); content-addressed `corpus_id` не несёт дату
  прогона — provenance полностью в extraction report (§6.1); права 0600
  на staging-артефакт не ставятся (читается через `docker exec cat`,
  перенос по ssh); F6 допускает продолжение при отклонении counters —
  осознанное решение: это data finding, а не инфра-сбой.
