# TT-02 · Протокол исполнения approved legacy_aliases (collision-winners)

Дата: 2026-07-28. Исполнитель: окно «Окно» (Kimi Code). Среда: локальная БД
(`proff58-db-1`, postgres:16). Staging не трогали — GO владельца не было.

## Что сделано

Переименованы slug трёх legacy-опций `tool_type` в canonical, одной транзакцией,
только поле `slug`. `id`, `value`, `sort_order`, все PAV — не тронуты.

| id | slug ДО | slug ПОСЛЕ | value | PAV |
|---|---|---|---|---|
| 160 | `hoz-lupy` | `izm-lupy` | Лупы | 24 |
| 167 | `hoz-provoloka` | `krep-provoloka` | Проволока | 20 |
| 143 | `hoz-zamki` | `krep-zamki` | Замки и скобянка | 250 |

Итого PAV: 24 + 20 + 250 = **294** — пересчитано после записи, совпало.

## Гейт-цикл

1. **Read-only.** Факты: где slug (см. ниже), отпечаток ДО.
2. **Preflight.** Canonical-slug'и `izm-lupy`/`krep-provoloka`/`krep-zamki` в БД
   отсутствовали (проверено выборкой) — конфликта другого рода нет.
   `content_locked=True` среди 294 затронутых товаров: **0**. Все 294 PAV имеют
   `source='manual'`, но операция меняет только `AttributeOption.slug`; PAV
   ссылаются на опцию по `id` (FK) и физически не затрагиваются — manual-значения
   не пострадали.
3. **Dry-run.** Rehearsal в транзакции с rollback: ровно 3 строки UPDATE,
   PAV 24/20/250 на месте, откат чистый. Ожидания сформулированы до прогона
   (см. «Ожидание vs факт»).
4. **pg_dump** — `scratchpad/catalog/backups/tt02-pre-legacy-aliases.dump`
   (custom format, 20.8 MB, вся БД). Снимок отката:
   `scratchpad/catalog/tt02-before-snapshot.json` (id, старые slug, списки
   product_id по каждой опции, отпечаток ДО).
5. **Write.** Одна транзакция, `UPDATE` по PK, assert на 3 строки и на PAV после.
6. **Post-audit.** См. ниже.

## Ожидание vs факт

| Метрика | Ожидание (до прогона) | Факт |
|---|---|---|
| UPDATE строк | 3 | 3 ✓ |
| PAV после | 24/20/250, Σ=294 | 24/20/250, Σ=294 ✓ |
| `taxonomy_identity_hash` | `fc13be78…14d8`, без изменений | не изменился ✓ |
| Отпечаток неприкасаемых полей | `161e02f2…d352`, без изменений | идентичен ✓ |
| `used_outside_manifest` | 0 | 0 ✓ |
| `missing_in_live` | только `steplery-i-zaklepochniki` | так ✓ |
| `unexpected_in_live` | только `drel` | так ✓ |
| `display_metadata_mismatch` | 46 → 49 (+3 переименованных) | 49 ✓ |
| `attrs_cache` расхождения | 0 (хранит value, не slug) | 0 записей ✓ |

Отпечаток неприкасаемых полей (`code_1c`, `article`, `name`, `category_id`,
`price`, `stock_quantity`, `status`, `is_active`) по 294 товарам:
ДО = ПОСЛЕ = `161e02f2589d4d2541dba09d3c0f7bd434ad7a4ab57ce8cc2ac0c955ae83d352`.

`taxonomy_identity_hash` (этоталон цепочки TT-02): ДО = ПОСЛЕ =
`fc13be7804b06713dccde5cd2888a437a1a7521772d5911acc7d9d93636714d8`.
Манифест в TT-02 не менялся — хэш не мог сдвинуться; проверено явно.

## Где используется slug (факты, не предположения)

- **API**: `GET /api/catalog/products/?tool_type=<slug>` и
  `GET /api/catalog/categories/<slug>/facets/?tool_type=<slug>` — фильтр
  relational по `attribute_values__value_option__slug`
  (`apps/catalog/filters.py:84`, `apps/catalog/facets.py:199`).
- **Фронтенд**: slug живёт только в query-параметре `?tool_type=`
  (`frontend/lib/url-state.ts:42,97`); в путях страниц его нет, PLP —
  `/catalog/<category>?tool_type=...`.
- **Sitemap**: в репозитории нет sitemap для каталога (ни Django, ни Next) —
  индексация slug-ссылок отсутствует.
- **`attrs_cache`**: хранит `value` опции («Лупы»), а не slug
  (`apps/catalog/read_models.py:53`) — фасеты по JSONB и кэш не затронуты;
  точечная пересборка по 294 товарам дала **0 расхождений**.
- **Фасетная панель** (nav) эмитит slug опции: после записи выдаёт
  `krep-zamki` (живой запрос `/api/catalog/categories/ruchnoy-klyuchi/facets/`
  → `{'slug': 'krep-zamki', 'count': 7}`), старого `hoz-zamki` в выдаче нет.
- **Ruleset v2** (`data/catalog_processing_rules/tool_type.v2.json`) на
  `hoz-*` не ссылается — `ruleset_unknown_slug` остался 0.
- **ВНЕ контура витрины** (не тронуты, зафиксировано как хвост):
  `data/tool_type_rules.json` (legacy extraction rules, используется запрещённой
  глобальной `enrich_tool_type` и аудитом) и one-off команда
  `apps/catalog/management/commands/catalog_distribute_legacy.py` содержат
  stale-ссылки на `hoz-lupy`/`hoz-provoloka`/`hoz-zamki`. На витрину не влияют;
  обновление — отдельным решением (контур распознавания в TT-02 не трогается).

## Живые запросы после записи

- `GET /api/catalog/products/?tool_type=izm-lupy` → 1 (active+published)
- `?tool_type=krep-provoloka` → 6; `?tool_type=krep-zamki` → 51; Σ=58 — совпало
  с числом активных опубликованных до записи.
- `?tool_type=hoz-lupy` (stale) → 200, count=0: неизвестный slug фильтрует в
  пустую выдачу без ошибки.
- Фасеты `ruchnoy-klyuchi` с `?tool_type=krep-zamki` → total=7,
  `applied_filters.tool_type='krep-zamki'`.

## Вывод по редиректам

**Не нужны.** Slug присутствует только в query-параметрах, а не в канонических
URL страниц; sitemap отсутствует, индексировать нечего; редирект query-параметра
на уровне nginx/Next не предусмотрен архитектурой. Побочный эффект: старые
сохранённые ссылки вида `?tool_type=hoz-zamki` деградируют в пустую выдачу
(200, count=0), а не в 404/410. Это факт для владельца: если такие ссылки
где-то опубликованы (рассылки, соцсети), вариант — alias-обработка на уровне
API (принимать старый slug как синоним) — отдельное продуктовое решение,
в TT-02 не входит.

## `load_tool_types` и `reconcile` после TT-02

- `load_tool_types`: блокер по legacy-alias ушёл. Команда всё ещё падает
  fail-closed, но уже только на дубле `steplery`:
  `option slug conflicts with DB: steplery: db='Степлеры и заклёпочники' vs
  manifest='Степлеры (скобозабивные)'` — это зона TT-03.
- `catalog_taxonomy_reconcile`: blocking-остаток ровно два пункта:
  `missing_in_live=[steplery-i-zaklepochniki]` (TT-03) и
  `unexpected_in_live=[drel]` (решение владельца). До нуля доводится только
  после TT-03 и решения по `drel` — в рамках TT-02 `blocking=0` недостижим
  по построению. `used_outside_manifest` — 0, `slug_value_mismatch` — 0,
  `ruleset_unknown_slug` — 0.

## Судьба `drel` — вынесено владельцу (не решал)

Факты: `id=398`, slug `drel`, value «Дрель», `sort_order=0`, PAV=0, конфликта
по value нет. В манифесте slug `drel` отсутствует (есть `dreli-shurupoverty`,
«Дрели-шуруповёрты»). Откуда взялась — не установлено (вероятно, ранний seed
из `tool_type_rules.json`; в текущем `tool_type_rules.json` slug `drel` есть
в справочниках окружения). Варианты:

1. Оставить как есть — `unexpected_in_live=1` в reconcile останется блокирующим
   (reconcile никогда не даст blocking=0).
2. Удалить — нарушение инварианта no-delete, только явным решением владельца.
3. Переименовать slug в неконфликтующий `legacy-drel` — уберёт из
   `unexpected_in_live`? Нет: любой slug вне манифеста остаётся unexpected.
   Значит осмысленных варианта два: удалить (с GO владельца) или признать
   blocking-остаток постоянным до решения. Рекомендация: удалить (0 PAV,
   ни на что не ссылается), но решение за владельцем.

## Границы соблюдены

- `value` не менялось; опции не создавались/не удалялись; PAV не трогались.
- Контур распознавания (matcher, ruleset v2, corpus, артефакты гейта) не тронут.
- Глобальные команды не запускались (`attrs_cache` — только точечная проверка
  с записью расхождений, которых оказалось 0).
- Staging, push, PR — не выполнялись.
- GitHub/GitLab операций не было.

## Артефакты

- `scratchpad/catalog/backups/tt02-pre-legacy-aliases.dump` — pg_dump ДО записи.
- `scratchpad/catalog/tt02-before-snapshot.json` — снимок отката (id, slug ДО,
  product_id по опциям, отпечаток ДО).
