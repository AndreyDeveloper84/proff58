# TT-06 · протокол: apply 11 одобренных findings — первое реальное изменение каталога контуром

Дата: 2026-07-28. Ветка `dev`, HEAD `e8c86ef`. Окно: одно.
БД: локальная dev `proff58` (docker `proff58-db-1`, postgres:16) → staging
(`ssh taximeter@dev.proff58.ru`, `~/proff58-staging`, docker-compose.prod).
Вход: run `00638eaa-0d7e-4532-b13f-ab40b3b8be0d` (ступень 3), 11 approved findings.
Окружение локальных команд — как в ступени 3 (`FEATURE_CATALOG_PROCESSING=True` через env).

---

## 0. Ожидание, сформулированное ДО записи (сверяется в §3, §6)

1. Apply ровно 11 changes → status `applied`, items → `completed`; создано ровно
   11 новых строк PAV `tool_type` (до — 0 у этих товаров): **4→izm-areometry,
   22→spetsialnye-klyuchi, 123→domkraty, 164→zaryadnye, 179→bp-kompressory,
   377→sharoshki, 422→bp-vozdukhoduvki, 4944→yashchiki-sumki, 4945→krep-bolty,
   11232→payalniki, 23606→hoz-himiya**.
2. `PAV tool_type` всего: 38822 → **38833** (+11), дублей нет.
3. Хэш неприкасаемых полей (без `tool_type`) до == после: `be36cf755b…`.
4. `attrs_cache.tool_type` пересобран ровно у 11 и равен value опции (точечно,
   глобальный `rebuild_attrs_cache` не запускался).
5. `rejected` (6798) и 9 `needs_review` не затронуты (PAV у них — 0).
6. Откат по паре снимков возвращает состояние в точности (0 PAV у 11,
   38822, кэш пуст).
7. Витрина: каждый из 11 виден в фильтре своей категории по своему slug,
   счётчики фильтра == прямому PAV-подсчёту.
8. Run закрывается `finalize` → `completed_with_review`.
9. На staging — те же числа (локальная БД = свежая копия staging).

## 1. ЛОКАЛЬНО — гейт-цикл

### 1.1 Read-only + preflight (все ожидания сошлись)

`scratchpad/phase8/tt06_readonly.py` → `artifacts-tt06/readonly-before.json`:

```
UNTOUCHABLE_HASH: be36cf755b4933529ff91164fd5170467e93605309097b7be8c3fe569eac50aa
PRODUCTS: 47225
PAV_11_COUNT: 0      (tool_type у 11 пуст — apply не выполнялся)
CONTENT_LOCKED: []   MANUAL_TOOL_TYPE: []   OPTIONS_MISSING: []   OPTIONS_TOTAL: 329
```

Отпечаток TT-06 — только неприкасаемые поля (`code_1c, article, name,
category_id, price, stock_quantity, status, is_active`), `tool_type` в него
**не входит** (меняется по замыслу — проверено явно в post-audit, §1.5).

### 1.2 Снимок «до» (H5)

```bash
uv run python manage.py catalog_tool_type_snapshot \
  --product-ids 4,22,123,164,179,377,422,4944,4945,11232,23606 \
  --out scratchpad/phase8/artifacts-tt06/tt06-local-before.json
# selector=explicit_ids rows=11 taxonomy_identity=524d4e317a80…
# canonical_hash=b4bdca2caccec38b1fe95d765523e2651ed847adf945bda3a874f2021a2a8332
```

### 1.3 pg_dump (после dry-run плана §0, до записи)

```bash
docker exec proff58-db-1 pg_dump -U proff proff58 | gzip \
  > scratchpad/phase8/artifacts-tt06/db-2026-07-28-tt06-local-before-apply.sql.gz
# 21 484 785 байт (pg_dump на хосте отсутствует — снят внутри контейнера БД)
```

### 1.4 Apply — одной транзакцией, run перепроверен (G1)

`scratchpad/phase8/tt06_apply.py` (shell): run_id задан явно, перед записью
проверено — approved changes ровно 11, все принадлежат run `00638eaa`
(`change.item.run_id == RUN_ID` по каждому), план slug'ов == одобренному;
все 11 `apply_catalog_change` — в одной внешней `transaction.atomic`, любой
не-`applied` → откат всего. Результат:

```
product=4→izm-areometry, 22→spetsialnye-klyuchi, 123→domkraty, 164→zaryadnye,
179→bp-kompressory, 377→sharoshki, 422→bp-vozdukhoduvki, 4944→yashchiki-sumki,
4945→krep-bolty, 11232→payalniki, 23606→hoz-himiya — APPLIED_TOTAL: 11
```

### 1.5 Post-audit (`tt06_postaudit.py`)

```
UNTOUCHABLE_HASH: be36cf755b… == ДО            (неприкасаемые поля целы)
PAV_11_COUNT: 11   PAV_MATCH_EXPECTED: True    (ровно 11, slug == одобренный)
rows=1 по каждому                              (дублей PAV нет)
PAV_TOOL_TYPE_TOTAL: 38833                     (38822 + 11)
attrs_cache × 11: OK                           (точечно, == value опции)
PAV_OTHERS_COUNT: 0                            (rejected/needs_review не тронуты)
```

Снимок «после»: `artifacts-tt06/tt06-local-after.json`,
`canonical_hash=9e483e7333a490cae1908c8eb065018ce213c808b8e872d192b1034170e444af`.

### 1.6 Испытание отката (H5/H6) — первое реальное, намеренное

```bash
# 1. rollback dry-run:  rows=11 noop=0 write=11 conflict=0 → план исполним
uv run python manage.py catalog_tool_type_rollback \
  --from …/tt06-local-after.json --to …/tt06-local-before.json
# 2. rollback --apply:  mode=apply written=11 noop=0; post-audit=PASS rows_checked=11
uv run python manage.py catalog_tool_type_rollback \
  --from …/tt06-local-after.json --to …/tt06-local-before.json --apply
```

Состояние после отката (независимый ORM-запрос):
`PAV_11=0`, `PAV_TOOL_TYPE_TOTAL=38822`, `attrs_cache.tool_type` пуст у всех 11
— **состояние возвращено в точности** (включая кэш, как обещает rollback.md).

Повторное применение — forward той же парой снимков:

```bash
# 3. forward dry-run:   rows=11 noop=0 write=11 conflict=0
# 4. forward --apply:   mode=apply written=11 noop=0; post-audit=PASS rows_checked=11
uv run python manage.py catalog_tool_type_rollback \
  --from …/tt06-local-before.json --to …/tt06-local-after.json --apply
```

Финальная сверка (`tt06_storefront.py`):
`UNTOUCHABLE_HASH == be36cf755b…`, `PAV_FINAL_MATCH: True`, total 38833.

### 1.7 Витрина (живой запрос `products_in(category, tool_type=slug)`)

11/11 товаров видны в фильтре своей категории по своему slug; счётчики
фильтра == прямому PAV-подсчёту в поддереве: 4→1, 22→1, 123→1, 164→77,
179→128, 377→122, 422→1, 4944→65, 4945→322, 11232→1, 23606→1.
`STOREFRONT_ALL_OK: True`.

### 1.8 Finalize

```bash
uv run python manage.py catalog_queue_finalize --run 00638eaa-…
# status=completed, outcome=completed_with_review
# items: 11 completed / 9 needs_review; changes: 11 applied / 1 rejected
```

`items_not_final` ступени 3 снят применением — state machine сошлась штатно.

## 2. STAGING — тот же гейт-цикл

Run ступени 3 существовал только локально; на staging контур воспроизведён
теми же решениями: новый run `3b11e43d-53c4-4fc7-bb4c-b4e66591aef3` (те же 20
explicit ids). `FEATURE_CATALOG_PROCESSING` на staging выключен — флаг
подавался точечно в команду (`docker compose exec -e FEATURE_CATALOG_PROCESSING=True`),
конфиг стенда не менялся.

### 2.1 Read-only + preflight

`UNTOUCHABLE_HASH: be36cf755b…` — **идентичен локальному** (локальная БД =
копия staging, доказано хэшем, не утверждением). `PAV_11=0`, locks/manual —
нет, options 329, `PAV_TOOL_TYPE_TOTAL=38822` == локальному ДО.

### 2.2 Снимок «до» + pg_dump

```
snapshot «до» → /tmp/tt06-staging-before.json (в контейнере web)
canonical_hash=b4bdca2c… == локальному снимку «до» (побайтово то же состояние)
backup.sh → /home/taximeter/backups/staging/db-2026-07-28-1331.sql.gz (+ media tgz)
```

### 2.3 Queue на staging

```bash
create --explicit-ids "<те же 20>" --idempotency-key "tt06-staging-apply11"
# → run 3b11e43d-53c4-4fc7-bb4c-b4e66591aef3, 20 items
export --run 3b11e43d-… --pretty
# → checksum b281bd671d81783970bf9f2859530795c19bfc97344d8490211f78ba291583d4
#   taxonomy_hash=a583a9ae…b2f1 — идентичен локальному (словари равны)
```

Result собран из тех же решений ступени 3 против staging export
(`artifacts-tt06/staging-queue/inbox/3b11e43d-….result.json`, JSON Schema:
0 ошибок), залит в `/app/var/catalog-processing/inbox/`. Импорты (оба с
`--run`, G1):

```bash
catalog_queue_import --file …/3b11e43d-….result.json --run 3b11e43d-…
# dry-run: would_create=12, skipped=8, errors=0
catalog_queue_import --file …/3b11e43d-….result.json --run 3b11e43d-… --commit
# created=12, skipped=8, errors=0, result_checksum=9eb598fe…
```

### 2.4 Модерация + apply

Те же решения: 11 approved / 1 rejected (6798). Apply (`tt06_apply.py` с
run `3b11e43d`): **APPLIED_TOTAL: 11**, все slug'и совпали с одобренными.

### 2.5 Post-audit, витрина, finalize

```
UNTOUCHABLE_HASH: be36cf755b… == ДО staging
PAV_11_COUNT: 11, MATCH_EXPECTED: True, дублей нет, total 38833
attrs_cache × 11: OK; PAV_OTHERS_COUNT: 0
snapshot «после»: canonical_hash=9e483e73… == локальному «после»
витрина: 11/11 OK, счётчики идентичны локальным (1,1,1,77,128,122,1,65,322,1,1)
finalize: status=completed, outcome=completed_with_review
          (items 11 completed / 9 needs_review; changes 11 applied / 1 rejected)
```

## 3. Сверка «предсказано → факт»

| Число | Ожидание (§0) | Локально | Staging |
|---|---|---|---|
| applied changes | 11 | 11 | 11 |
| PAV создано | 11 | 11 | 11 |
| PAV tool_type total | 38833 | 38833 | 38833 |
| untouchable hash | `be36cf755b…` | == | == |
| дубли PAV | 0 | 0 | 0 |
| PAV у rejected/needs_review | 0 | 0 | 0 |
| attrs_cache mismatch | [] | [] | [] |
| rollback возвращает состояние | да | **да (write=11, post-audit PASS, 38822)** | не требовался (только локально) |
| витрина OK | 11/11 | 11/11 | 11/11 |
| finalize | completed_with_review | да | да |

Расхождений нет — подгонки не было.

## 4. Границы — подтверждение

- Применены **только 11 одобренных**; rejected (6798) и 9 needs_review не
  затронуты (PAV_OTHERS=0 на обеих БД).
- Кроме `tool_type` ничего не менялось: untouchable hash до == после на обеих
  БД (цена, остаток, категория, название, артикул, статус публикации целы).
- Контур `tool_type` не тронут; новые типы в манифест не добавлялись;
  глобальные команды (`enrich_attributes` без `--path`, `rebuild_attrs_cache`)
  не запускались — кэш пересобран точечно самим apply (11 товаров).
- `--run` — в каждом вызове импорта (2 локально в ст. 3 + 2 на staging);
  apply через `apply_catalog_change` с явной перепроверкой run (G1).
- Tracked-файлы окном не изменялись; чужие изменения CAT-03/PARS-03 не
  откатывались; `git add` не выполнялся; push/PR не было; staging-config не
  менялся (флаг — только env в команде); ступень 4 не начиналась.
- Один транзиентный SSH-таймаут на staging — повтор команд, влияния нет.

## 5. Артефакты

- Локально: `artifacts-tt06/readonly-before.json`, `tt06-local-before.json`,
  `tt06-local-after.json`, `db-2026-07-28-tt06-local-before-apply.sql.gz`.
- Staging (копии локально): `artifacts-tt06/tt06-staging-before.json`,
  `tt06-staging-after.json`, `staging-export.json`,
  `staging-queue/inbox/3b11e43d-….result.json`; на стенде:
  `/home/taximeter/backups/staging/db-2026-07-28-1331.sql.gz`,
  `/tmp/tt06-staging-{before,after}.json` (в контейнере web).
- Скрипты: `tt06_readonly.py`, `tt06_apply.py`, `tt06_postaudit.py`,
  `tt06_storefront.py` (все — `scratchpad/phase8/`).
- Run `00638eaa` (локально) и `3b11e43d` (staging) — `completed`,
  `completed_with_review`.
