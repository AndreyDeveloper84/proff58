# TT-04 · Протокол: словарь `tool_type` на staging в соответствие с манифестом

Дата: 2026-07-28. Исполнитель: окно «TT-04» (Kimi Code). Среда: **staging**
`dev.proff58.ru`, стек `/home/taximeter/proff58-staging`, БД `proff58_staging`,
деплой `7714625` (merge TT-01). Промпт: `scratchpad/catalog/tt-04-staging-dictionary-prompt.md`.

## Главное: аудит изменил скоуп

Аудит (выполнен первым, до любой записи) показал картину, принципиально отличную
от ожидаемой, — по правилу промпта работа была остановлена и доложена
оркестратору. Решение оркестратора: **продолжить урезанным скоупом** —
фактическим write остался только seed `izm-areometry`.

| Пункт промпта | Ожидание | Факт аудита |
|---|---|---|
| remap `hoz-*` → canonical | предстоит | **уже выполнен на стенде ранее** (id=160/167/143 носят canonical-slug) |
| миграция `catalog.0027` | скорее всего применена | **применена** 2026-07-22 13:44 UTC деплоем; дублей нет |
| выравнивание `sort_order` | предстоит | **расхождений нет** (`display_metadata_mismatch: 0`) |
| seed `izm-areometry` | предстоит | отсутствовала — **единственный оставшийся шаг, выполнен** |
| `drel` — blocking-остаток | зафиксировать | **на стенде `drel` не существует** (id=398 = `inch` другого атрибута) |

## Происхождение remap (git-археология, read-only)

Remap на стенде — **не запись вне циклов**, а след штатной работы старой версии
`load_tool_types` (до Wave 7.1 H1.2): она делала
`update_or_create(attribute, value=…, defaults={slug, sort_order})` — ключ по
**value**, slug перезаписывался. После PR #470 (`8910079`, 10.07.2026,
«safe reconcile tool type rules») в `data/tool_type_rules.json` появились
canonical-slug `krep-zamki` / `krep-provoloka` / `izm-lupy`, и очередной прогон
старой команды на стенде переименовал опции на месте — `id` и PAV сохранились,
что и наблюдается. Следы прогонов — в `~/.bash_history` сервера
(многократные `$DC exec -T web python manage.py load_tool_types`);
`django_admin_log` по этим опциям пуст (не админка). Текущая
`load_tool_types` (H1.2) так себя не ведёт: ключ по slug, fail-closed,
no-delete. Вывод: постороннего писателя в staging нет.

## ЗАДАЧА 1 — аудит стенда (факты)

- Опций `tool_type`: **328**, уникальных slug 328, дублей нет.
- `hoz-lupy` / `hoz-provoloka` / `hoz-zamki` — отсутствуют.
- id=160 `izm-lupy` (PAV 24), id=167 `krep-provoloka` (20), id=143 `krep-zamki`
  (**247**, локально 250), sort_order 17/16/15 — манифестные.
- id=73 `steplery` (PAV 42), id=16 `steplery-i-zaklepochniki` (PAV **10**,
  локально 0).
- `izm-areometry` — отсутствовала; опций со value `%реометр%` — нет.
- `reconcile` до записи: единственный blocking `missing_in_live=[izm-areometry]`,
  `unexpected_in_live=0`, `display_metadata_mismatch=0`; advisory
  `manifest_unused_option=4`.
- Неприменённых миграций нет; `reviews.0002` применена деплоем 23.07 (не нами).
- Расхождение PAV с локальными числами (247/42/10 против 250/43/0) объяснено:
  стенд живёт через обмен с 1С, локальный снимок ему не эталон.

**Зафиксировано для владельца:** id=16 (`steplery-i-zaklepochniki`) на стенде
имеет 10 PAV — удалять опцию, на которой висят товары, нельзя; вопрос её судьбы
на стенде звучит иначе, чем локально. Вопрос `drel` — чисто локальный, на
стенде решать нечего.

## ЗАДАЧА 2 — гейт-цикл (урезанный скоуп: только seed)

1. **Preflight.** `izm-areometry` и её value «Ареометры (денсиметры)» в БД
   отсутствуют (конфликта другого рода нет); затронутых товаров 0 (опция
   новая, PAV нет) — `content_locked` и manual-значения не пострадают
   по построению.
2. **Dry-run.** Rehearsal в транзакции с rollback. Ожидание, сформулированное
   ДО прогона: `created=1, present=328, display_updated=0, display_mismatch=0`,
   опций станет 329, CategoryAttribute не изменится (19). **Факт rehearsal:
   точно так** (`izm-areometry`, value «Ареометры (денсиметры)», sort_order=18),
   откат чистый.
3. **pg_dump** — после dry-run, до записи:
   `/home/taximeter/backups/tt04-pre-staging-areometry.dump` (custom, 21.7 MB);
   копия `scratchpad/catalog/backups/tt04-pre-staging-areometry.dump`.
   Снимок отката: `scratchpad/catalog/tt04-staging-before-snapshot.json`.
4. **Write.** Одна команда — `load_tool_types --update-display` (внутри —
   одна `transaction.atomic`): `created=1, present=328, display_updated=0,
   display_mismatch=0`. Совпало с предсказанием. Новая опция id=438.
5. **Post-audit.** Ниже.

## Ожидание vs факт

| Метрика | Ожидание (до прогона) | Факт |
|---|---|---|
| `load_tool_types` | created=1, present=328, display_updated=0, mismatch=0 | точно так ✓ |
| Опций после | 329 / 329 уникальных | 329 / 329 ✓ |
| `taxonomy_identity_hash` | `524d4e31…` без изменений | `524d4e317a804160548ebd5f4d0c590cb08a9b69910b23355df7558902616439`, не изменился ✓ |
| Отпечаток неприкасаемых полей (47225 товаров) | идентичен | ДО = ПОСЛЕ = `0b44ad4e6ecb926e666b9e2f275fbb7b6f90306fd28f1e112ad62072768bb21d` ✓ |
| `CategoryAttribute` (tool_type) | 19, без изменений | 19 ✓ |
| `attrs_cache` | затронутых товаров 0 → пересборка не требуется | 0 товаров, пересборка не выполнялась ✓ |
| `reconcile` blocking | 0 | **0 по всем блокирующим осям** ✓ |

`reconcile` после записи: `identity_equal=True`, все blocking-оси 0
(`missing/unexpected/slug_value/used_outside/ruleset_unknown`). Advisory:
`manifest_unused_option=5` (в т.ч. `izm-areometry` — ожидаемо, 0 PAV).
`drel`-остатка на стенде нет и не было.

## ЗАДАЧА 3 — витрина (живые запросы, HTTPS `dev.proff58.ru`)

| Запрос | HTTP | count | Сверка с БД (visible_products) |
|---|---|---|---|
| `?tool_type=izm-lupy` | 200 | 1 | 1 ✓ |
| `?tool_type=krep-provoloka` | 200 | 6 | 6 ✓ |
| `?tool_type=krep-zamki` | 200 | 51 | 51 ✓ |
| `?tool_type=izm-areometry` | 200 | 0 | 0 ✓ (опция без товаров — консистентно) |
| `?tool_type=hoz-zamki` (stale) | 200 | 0 | деградация в пустую выдачу, как предсказано ✓ |
| `?tool_type=steplery` | 200 | 23 | 23 ✓ |
| `?tool_type=steplery-i-zaklepochniki` | 200 | 4 | 4 visible из 10 PAV ✓ |

Артефакты ответов: `scratchpad/catalog/tt04-live/`.

Примечание к приёмочным «24 / 20 / 250»: это числа PAV из локального снимка;
на стенде remap предшествовал TT-04, PAV живут своей жизнью (24/20/247), а API
отдаёт active+published. Критерий исполнен в действующей форме: количества по
новым slug **совпали с БД стенда** на момент проверки.

## Перепроверка витрины CAT-02 (по просьбе оркестратора)

После seed `izm-areometry` панели фасетов измерительного на месте:

- `GET /api/catalog/categories/izmeritelnyy-urovni/facets/` → 200, фасет
  `length` (16 значений), `tool_type` (`izm-urovni`: 159), total 159;
- фильтр `?category=izmeritelnyy-urovni&attr_length_min=1000` → 200, count=**31**
  — сошлось с эталоном CAT-02 (db_ge=31);
- `…/izmeritelnyy-ruletki/facets/` → фасеты `tape_length` (11 значений) и
  `tape_width` (7) на месте, total 109.

Добавление типа без товаров логику панелей не сдвинуло.

## Координация с CAT-02

Проверено дважды — до write и в момент write: управляющих процессов
(`manage.py`, shell) в контейнере web нет, последний staging-артефакт CAT-02
датирован 04:00 (завершение её записи на стенд), мой write — 04:26.
Одновременных write не было. Обе задачи трогали `attrs_cache` только точечно;
у TT-04 затронутых товаров 0.

## Границы соблюдены

- `taxonomy_identity_hash` не изменился — сверка с **новым** эталоном
  `524d4e31…` (не `fc13be78…`), проверено явно до и после.
- Значения характеристик не трогались; хвосты CREATE=4 / PRUNE=17 — вне скоупа.
- Типы не создавались вручную: единственная новая опция — штатный seed
  `izm-areometry` из манифеста. Ничего не удалялось и не сливалось.
- Деструктивные миграции не применялись; миграций TT-04 вообще не гонял
  (0027 уже была применена деплоем).
- Глобальные команды не запускались; push/PR/GitHub-операций не было.
- Чужие изменения в общей рабочей копии не затрагивались (правок кода нет;
  только артефакты в `scratchpad/catalog/`).

## Артефакты

- `scratchpad/catalog/backups/tt04-pre-staging-areometry.dump` — pg_dump ДО
  (копия; оригинал на сервере `/home/taximeter/backups/`).
- `scratchpad/catalog/tt04-staging-before-snapshot.json` — снимок отката
  (состояние ДО, план отката, факты аудита).
- `scratchpad/catalog/tt04-live/` — ответы витрины (products по 7 slug,
  фасеты urovni/ruletki, фильтр length≥1000).
