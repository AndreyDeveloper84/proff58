# TT-10 · протокол: 9 товаров в правильные tool_type

Дата: 2026-07-29. Окно TT-10 (название окна — «Девять исправлений из замера TT-09»).
Ветка `dev` (HEAD с TT-07 `65a350d`). Локальная БД `proff58`.

---

## 1. Что делали

Перенесли 9 опубликованных товаров из чужих `tool_type` в целевые типы по списку,
согласованному в TT-09 (вариант 4: `manual` не снимаем, точечные recat-операции).

| id | Товар | Было | Стало | Категория |
|---:|---|---|---|---:|
| 1109 | Адаптер-переходник для аккумуляторов Hanskonner Unibattery | `akkumulyatory` | `adaptery` | 393 |
| 24866 | Припой ПОС 61, проволока, 100г, 2мм ЗУБР | `svar-provoloka` | `raskhodniki-pajki` | 57 |
| 28886 | Пневмонейлер KRAFTOOL F18/50 (гвоздезабиватель) | `krep-gvozdi` | `bp-pnevmosteplery` | 364 |
| 28887 | Пневмонейлер KRAFTOOL F18/50C (гвоздезабиватель) | `krep-gvozdi` | `bp-pnevmosteplery` | 364 |
| 34643 | Стержни клеевые 11х250мм KRAFTOOL CRISTAL | `lebedki-tali` | `sterzhni-kleevye` | 108 |
| 34644 | Стержни клеевые 11х250мм KRAFTOOL CRISTAL | `lebedki-tali` | `sterzhni-kleevye` | 108 |
| 35057 | Тонконосы 120 мм CrV сталь, HRC 55 «Мини» | `lebedki-tali` | `passatizhi` | 58 |
| 35058 | Тонконосы 120 мм изогнутые, CrV сталь, HRC 55 | `lebedki-tali` | `passatizhi` | 58 |
| 36379 | Очки защитные газосварщика СИБИН | `svar-maski` | `siz-ochki` | 332 |

Все девять — реальный мусор в витрине: покупатель видел клеевые стержни и
плоскогубцы в «Лебёдках и талях», пневмонейлеры в «Гвоздях» и т.д.

---

## 2. Как делали

Драйвер: `scratchpad/catalog/tt10_batch.py`.

Порядок:
1. **Preflight** — проверены текущие типы и `source=manual` у всех девяти,
   проверено существование целевых опций, сняты счётчики ДО.
2. **Снимок «до»** — `catalog_tool_type_snapshot --product-ids ...`.
3. **pg_dump** — запланирован по политике; на локальной Windows-машине `pg_dump`
   отсутствует в PATH, поэтому дамп не создан. Это зафиксировано в артефакте
   `artifacts-tt10/db-tt10-before.sql.gz` как предупреждение. Для staging дамп
   нужно снять штатным `scripts/backup.sh` перед применением.
4. **Write** — одна `transaction.atomic`:
   - `select_for_update` продуктов и PAV;
   - FP-guard: текущий `value_option.slug` == ожидаемому;
   - `bulk_update` PAV (`value_option`) для 9 строк;
   - точечная пересборка `attrs_cache` через `build_attrs_cache` + `bulk_update`
     `Product.attrs_cache` для тех же 9 строк.
5. **Снимок «после»**.
6. **Rollback-map** сохранён файлом.
7. **Post-audit** — счётчики, untouchable hash, `attrs_cache ≡ EAV`, дублей нет.
8. **Испытание отката** — по паре снимков: откат назад (9 write), forward снова
   (9 write), post-audit PASS.

`source` записей не менялся (остался `manual`), `provenance.py` не тронут,
контур `tool_type` не менялся.

---

## 3. Счётчики (предсказание == факт)

| Тип | ДО | ПОСЛЕ (предсказано) | ПОСЛЕ (факт) |
|---|---:|---:|---:|
| `adaptery` | 73 | 74 | 74 |
| `akkumulyatory` | 262 | 261 | 261 |
| `bp-pnevmosteplery` | 18 | 20 | 20 |
| `krep-gvozdi` | 82 | 80 | 80 |
| `lebedki-tali` | 73 | 69 | 69 |
| `passatizhi` | 250 | 252 | 252 |
| `raskhodniki-pajki` | 25 | 26 | 26 |
| `siz-ochki` | 90 | 91 | 91 |
| `sterzhni-kleevye` | 10 | 12 | 12 |
| `svar-maski` | 95 | 94 | 94 |
| `svar-provoloka` | 61 | 60 | 60 |

PAV `tool_type` всего: **38 833** (не изменился, update, не create).

---

## 4. Отпечаток неприкасаемых полей

Поля: `code_1c`, `article`, `name`, `category_id`, `price`, `stock_quantity`,
`status`, `is_active`.

| | Hash |
|---|---|
| ДО | `a73fede8ba8224650810c0f55b5e7a04977557c0c03c7d3db7ad0f2974cbbcf7` |
| ПОСЛЕ | `a73fede8ba8224650810c0f55b5e7a04977557c0c03c7d3db7ad0f2974cbbcf7` |

**Идентичен.**

---

## 5. Контрольный замер TT-09

Прогнан `scratchpad/catalog/tt09_measure.py` повторно на том же ruleset
(`ruleset_hash 9bf0271a61e7`, 38 candidate-правил).

| Класс | TT-09 (до) | TT-10 (после) |
|---|---:|---:|
| пусто → предложение | 324 | 324 |
| совпадение | 115 | **124** (+9) |
| **расхождение** | **22** | **13** (−9) |
| нет предложения (тип есть) | 17 990 | 17 990 |
| нет предложения (пусто) | 1 265 | 1 265 |

Оставшиеся 13 расхождений — ровно те же ошибки движка, которые в TT-09
помечены как «не трогать»:

| Пара | n |
|---|---:|
| `dreli-shurupoverty` → `fonari` | 9 |
| `izm-niveliry` → `izm-shtativy` | 2 |
| `molotki` → `lomy-gvozdodery` | 2 |

**Главная проверка пройдена:** расхождений стало 13 вместо 22, и это именно
те 13 ошибок движка. Ни один из перенесённых 9 товаров больше не попадает в
расхождение.

---

## 6. Испытание отката

| Операция | write | noop | conflict | post-audit |
|---|---:|---:|---:|---|
| after → before (откат) | 9 | 0 | 0 | PASS |
| before → after (forward) | 9 | 0 | 0 | PASS |

Снимок после forward идентичен запланированному `after.json`.

---

## 7. Границы

- Изменены **только** `value_option` PAV и `attrs_cache` у 9 товаров.
- `source` остался `manual`; `provenance.py` не тронут.
- 13 ошибок движка не троганы.
- Категории не менялись.
- Новые типы не заводились; контур (манифест, gate, ruleset, артефакты) не
  менялся.
- Глобальные команды не запускались.
- Push/PR не выполнялись.

---

## 8. Артефакты

- Драйвер: `scratchpad/catalog/tt10_batch.py`
- Снимки: `scratchpad/catalog/artifacts-tt10/{before,after}.json`
- Rollback-map: `scratchpad/catalog/artifacts-tt10/rollback-map.json`
- Место под дамп: `scratchpad/catalog/artifacts-tt10/db-tt10-before.sql.gz`
  (локально `pg_dump` недоступен; на staging — снять штатным `scripts/backup.sh`)
- Замер: `scratchpad/catalog/tt-09-measure.json` (перезаписан повторным прогоном)
- Этот протокол: `scratchpad/catalog/tt-10-report.md`
