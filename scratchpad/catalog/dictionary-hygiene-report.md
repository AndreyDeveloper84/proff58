# TT-03 · Протокол: гигиена словаря `tool_type` (дубль `steplery` + `sort_order`)

Дата: 2026-07-28. Исполнитель: окно «Окно» (Kimi Code). Среда: локальная БД
(`proff58-db-1`, postgres:16). Staging не трогался, push/PR не выполнялись.
Эталон хэша для этой задачи — **новый**, из отчёта TT-01: `524d4e31…`
(не `fc13be78…`).

## Главный факт read-only фазы

**Решение по `id=16` уже принято владельцем ранее** — бриф TT-03 исходил из
того, что решения нет, но оно есть: ADR-0012 (принято 2026-07-22) и миграция
`catalog.0027_reslug_steplery_unique_option_slug` (PR #584, DEVIATION-2) —
re-slug `id=16` → `steplery-i-zaklepochniki` с guard-проверками + unique
`(attribute, slug)` для непустых slug. Локальная БД просто **не имела
применённой миграции 0027** (снимок до 2026-07-22): `django_migrations`
не содержала 0027, констрейнт отсутствовал. Поэтому дубль жил только локально.

Вариант «удалить id=16» в ADR-0012 рассмотрен и **отклонён владельцем**
(вариант b — слияние/удаление: «разные таксономические сущности»). Инвариант
no-delete не нарушен: исполнен штатный re-slug одобренной миграцией, а не
новое самостоятельное решение окна.

## Что ссылается на `id=16` (preflight, факты)

- PAV: **0** (id=73: 43 — на месте после записи).
- `CatalogChange.evidence`: 0 упоминаний `steplery`.
- `data/tool_type_rules.json` уже содержит обе записи с правильными slug
  (`steplery` и `steplery-i-zaklepochniki`) — extraction-контур не ломается.
- Фронтенд/фикстуры/gate-артефакты на id=16 не ссылаются (привязка по хэшам
  таксономии, не по id).

## `sort_order` — куда влияет

`sort_order` опции используется витриной: порядок значений nav-панели
`tool_type` и EAV-фасетов (`apps/catalog/facets.py:111,261-263` —
`order_by(value_option__sort_order, …)`). В `attrs_cache` не попадает
(там только значения). Выравнивание по манифесту — восстановление
задокументированного инварианта `live == manifest`, влияние ограничено
порядком отображения значений фильтров.

## Гейт-цикл

1. **Read-only**: факты выше; отпечаток ДО
   `ad641d5c333c82572f7acb89cc20d50c5c05361688f5bc7a9a31a259520bcfec`
   (все 47226 товаров, неприкасаемые поля).
2. **Preflight**: ссылки на id=16 отсутствуют; manual-значения PAV не
   затрагиваются (меняются только `slug` пустой опции и `sort_order` опций —
   display-метаданные, не PAV).
3. **Dry-run** (rehearsal с rollback): re-slug id=16 по логике миграции —
   guard'ы проходят; `load_tool_types --update-display` внутри внешней
   транзакции — `created=1, present=328, display_updated=49,
   display_mismatch=0`. Ожидания сформулированы до прогона и совпали.
4. **pg_dump**: `scratchpad/catalog/backups/tt03-pre-dictionary-hygiene.dump`
   (custom, 20.8 MB). Отпечаток ДО:
   `scratchpad/catalog/tt03-before-fingerprint.txt`.
5. **Write**:
   - `migrate catalog 0027` — re-slug id=16 + констрейнт
     `uniq_attributeoption_attr_slug_nonempty`; остальные отстающие миграции
     (delivery.0005, orders.0010–0012, promotions.0001, reviews.0002)
     **намеренно не применялись** — вне зоны задачи, reviews.0002
     деструктивна (delete+create Review); вопрос отставания локальной БД
     вынесен владельцу ниже.
   - `load_tool_types --update-display` — создана `izm-areometry`
     (sort_order=18; сидирование стало легальным после remap TT-02, как
     предписывал TT-01: «попадание типа в БД — после remap»), выровнены
     49 `sort_order` (46 исходных + 3 переименованных в TT-02).
6. **Post-audit**: ниже.

## Ожидание vs факт

| Метрика | Ожидание | Факт |
|---|---|---|
| re-slug id=16 | `steplery-i-zaklepochniki`, guard'ы миграции | так ✓ |
| `load_tool_types --update-display` | created=1, present=328, display_updated=49, mismatch=0 | точно так ✓ |
| `taxonomy_identity_hash` | `524d4e31…` без изменений (манифест не тронут) | не изменился ✓ |
| PAV id=73 | 43 | 43 ✓ |
| Отпечаток неприкасаемых полей | `ad641d5c…` идентичен | идентичен ✓ |
| `attrs_cache` расхождения | 0 (337 проверенных товаров: steplery + 3 опции TT-02) | 0 ✓ |
| reconcile missing_in_live | 0 | 0 ✓ |
| reconcile display_metadata_mismatch | 0 | 0 ✓ |

`taxonomy_identity_hash` ДО = ПОСЛЕ =
`524d4e317a804160548ebd5f4d0c590cb08a9b69910b23355df7558902616439` — проверено
явно (манифест в TT-03 не менялся; `value` не трогались).

## Живые запросы после записи

- `GET /api/catalog/products/?tool_type=steplery` → 24 (active+published,
  резолв теперь детерминирован — slug уникален, плюс DB-констрейнт).
- `?tool_type=steplery-i-zaklepochniki` → 0 (у id=16 нет товаров — консистентно).
- Nav-панель фасетов (`ruchnoy-klyuchi`) отдаёт значения в порядке
  `sort_order` манифеста; `krep-zamki` (sort=15 после выравнивания) на месте.

## `reconcile` после цепочки TT-02 → TT-01 → TT-03

```
missing_in_live: 0      unexpected_in_live: [drel]   slug_value_mismatch: 0
used_outside_manifest: 0   ruleset_unknown_slug: 0   semantic_duplicate: 0
display_metadata_mismatch: 0   manifest_unused_option: 32 (advisory)
```

Единственный blocking-остаток во всём контуре — `drel` (id=398, 0 PAV):
**решение владельца** (варианты — в `legacy-aliases-report.md`, §«Судьба
drel»). До него `blocking = 0` недостижим по построению.

`load_tool_types` теперь проходит без поблажек (выше — фактический прогон,
EXIT=0).

## Границы соблюдены

- `taxonomy_identity_hash` не изменился — проверено явно против эталона TT-01.
- Типы не создавались вручную и не сливались: единственная новая опция —
  `izm-areometry`, создана штатным seed из манифеста (решение TT-01).
- Манифест, matcher, ruleset v2, corpus, release manifest — не трогались
  (коммитов в TT-03 нет, дерево не менялось).
- Глобальные команды не запускались; `attrs_cache` — точечная проверка
  (337 товаров), записей 0.
- Staging, push, PR — нет. Чужие изменения в общей рабочей копии не
  затрагивались (правок файлов в TT-03 вообще не было).

## Вынесено владельцу

1. **`drel`** — единственный blocking-остаток reconcile (см. отчёт TT-02).
2. **`manifest_version` 1 → 2** — рекомендация в отчёте TT-01.
3. **Локальная БД отстаёт от кодовой базы** на 6 миграций (delivery.0005,
   orders.0010–0012, promotions.0001, reviews.0002). Применялась только
   catalog.0027. Если локалка должна соответствовать dev — нужен отдельный
   `migrate` с осознанием reviews.0002 (пересоздание таблицы Review).
4. **Stale-ссылки на `hoz-lupy/hoz-provoloka/hoz-zamki`** в
   `data/tool_type_rules.json` и one-off `catalog_distribute_legacy.py` —
   на витрину не влияют; обновление контура распознавания — отдельным
   решением (см. отчёт TT-02).

## Артефакты

- `scratchpad/catalog/backups/tt03-pre-dictionary-hygiene.dump` — pg_dump ДО.
- `scratchpad/catalog/tt03-before-fingerprint.txt` — отпечаток ДО.
