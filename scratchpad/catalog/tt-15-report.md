# TT-15 · Перенос в новые типы: триммерные головки, воронки, нагрузочные вилки

Дата: 2026-07-31. Окно TT-15 — recat класса 2 по гейт-циклу.
Ветка `feature/tt-15-recat` (worktree `.worktrees/tt-15`, от `origin/dev` 5efab7c),
staging `dev.proff58.ru`, рабочая копия `/home/taximeter/proff58-staging`
(стенд на 5efab7c — TT-14 задеплоен, оба новых типа в словаре).

---

## 1. Периметр (пересчитан по стенду, read-only)

Драйвер разведки: `tt15_recon.py`. Полные списки — артефакты, здесь агрегаты.

### Кластер 1 — триммерные головки → `bp-golovki-trimmernye` (108)

Критерий «`триммерн` + `головк` в названии»: **108 товаров** — сошлось с
промптом (72 активных / 36 в наличии; `prochaya-osnastka` ×93, `krep-gaiki` ×6,
`krep-bolty` ×4, без типа ×5). Решения по пограничным исполнены буквально:

| id | Проверка на стенде | Исполнение |
|---:|---|---|
| 28157, 28158, 28159 | в критерии, деактивированы, `prochaya-osnastka` | **перенесены** |
| 38680 | «Замена головки триммерной», услуга, без PAV | **не тронут** (вне периметра, watch-контроль) |
| 26232 | «Головка для триммера ПАУК с леской SKRAB», вне критерия | **добавлен и перенесён** |
| 1899 | «Триммер бензиновый STIHL FS 250 …», `bp-trimmery` | **не тронут** (вне критерия, watch-контроль) |

Итого: 108 − 1 (38680) + 1 (26232) = **108** — сходится с промптом.
Состав по исходным типам: `prochaya-osnastka` ×94, `krep-gaiki` ×6,
`krep-bolty` ×4, без PAV-строки ×4.

### Кластер 2 — воронки → `hoz-voronki` (15)

Regex `\bворонк` — **21 товар**, разобран глазами поимённо (названия и
состояние — вывод recon в §А):

- **перенесены 15**: 39279–39292 (14 шт: «Воронка 80/100/160мм»,
  «автомобильная», «бытовая», «техническая», металлические с гибким
  наконечником, разборная 39290 из `obor-smazka` и т.п.) **+ 35608
  «Воронка GROZ пластиковая 1,7л»** — настоящая воронка (активна, остаток 1),
  в таблице промпта не учтена; решение окна — переносить (findings §3);
- **не переносились 6** (решения промпта исполнены): 11 (ареометр), 40109,
  40354 (комплектующие к ВР-100), 38368 (конус Абрамса), 11056 (мундштук к
  алкотестеру), 6170 (фильтр-воронка малярная). 11056 и 6170 — в findings.

### Кластер 3 — нагрузочные вилки → `izm-multimetry` (7)

8 товаров по «нагрузочн+вилк»: 7 в `avtomaty-predohraniteli` (23743–23749),
#18 уже в `izm-multimetry` (подтверждённый зонтик). Контраргументов в данных
нет (все 7 — нагрузочные/нагрузочно-диагностические вилки, не автоматы
защиты) — перенесены 7, #18 не тронут (watch-контроль).

---

## 2. Гейт-цикл

На каждый кластер: dry-run → `scripts/backup.sh` на хосте → write в одной
`transaction.atomic` → post-audit → испытание отката → обновление глобального
отпечатка. Драйвер: `tt15_batch.py` (вариант `tt12_batch.py` под 3 кластера,
fail-closed; создаёт PAV только там, где строки не было — `source=manual`
по умолчанию модели).

**Контроль параллельной записи:** глобальный отпечаток (PAV total, счётчики
затронутых типов, «яя», суффиксы, группы-дубли, findings, taxonomy identity,
хэш неприкасаемых полей всех scope+watch) сверялся перед каждым кластером —
совпал с сохранённым все три раза, чужой записи в окне не было.

**Чужие изменения до окна:** не проверялись отдельно — baseline снят
непосредственно перед dry-run кластера 1 (2026-07-31 06:27 UTC).

### Счётчики: предсказание == факт (PAV по типам)

| Тип | ДО | ПОСЛЕ | Δ |
|---|---:|---:|---:|
| `bp-golovki-trimmernye` | 0 | 108 | +108 |
| `prochaya-osnastka` | 1581 | 1487 | **−94** (см. findings §4) |
| `krep-gaiki` | 144 | 138 | −6 |
| `krep-bolty` | 433 | 429 | −4 |
| `hoz-voronki` | 0 | 15 | +15 |
| `obor-smazka` | 151 | 150 | −1 |
| `izm-multimetry` | 176 | 183 | +7 |
| `avtomaty-predohraniteli` | 41 | 34 | −7 |

**PAV `tool_type` всего: 38 877 → 38 895 (+18)** — созданы строки для
товаров, у которых PAV не было вообще (4 + 14); все существовавшие строки
только обновлены, удалений и пересозданий нет. Объяснение расхождения с
буквальным инвариантом «38 877» — findings §5.

### Дампы (scripts/backup.sh на хосте, до write каждого кластера)

| Кластер | Файл | Размер |
|---|---|---:|
| 1 | `/home/taximeter/backups/staging/db-2026-07-31-0628.sql.gz` | 21 538 381 |
| 2 | `/home/taximeter/backups/staging/db-2026-07-31-0633.sql.gz` | 21 539 161 |
| 3 | `/home/taximeter/backups/staging/db-2026-07-31-0636.sql.gz` | 21 539 524 |

Маркер: `artifacts-tt15/db-tt15-backups.txt`.

---

## 3. Post-audit (по каждому кластеру)

- счётчики факт == предсказание (таблица §2) — PASS ×3;
- отпечаток неприкасаемых полей (`code_1c`, `article`, `name`, `category_id`,
  `price`, `stock_quantity`, `status`, `is_active`) по scope+watch идентичен
  до/после — PASS ×3 (cluster1 `295315d2…`, cluster2 `db85bbae…`,
  cluster3 `9639d6ae…`);
- `attrs_cache ≡ EAV` по всем 130 товарам — PASS ×3;
- дублей PAV нет — PASS ×3;
- watch-товары (38680, 1899, 11, 40109, 40354, 38368, 11056, 6170, 18)
  не изменились — PASS ×3.

## 4. Испытание отката на стенде (обе стороны, по паре снимков)

| Кластер | after→before | before→after | контрольный снимок |
|---|---|---|---|
| 1 | write=108, noop=0, conflict=0 | write=108, noop=0, conflict=0 | == after — PASS |
| 2 | write=15, noop=0, conflict=0 | write=15, noop=0, conflict=0 | == after — PASS |
| 3 | write=7, noop=0, conflict=0 | write=7, noop=0, conflict=0 | == after — PASS |

Карты отката: `artifacts-tt15/cluster{1,2,3}-rollback-map.json`
(включая `old_slug: null` для 18 созданных строк — откат их удаляет,
механика `tool_type_rollback` это покрывает).

## 5. Глобальные инварианты (invariants-before → invariants-after)

| Инвариант | ДО | ПОСЛЕ | Итог |
|---|---|---|---|
| `taxonomy_identity` | `7ac7a9a2…` | `7ac7a9a2…` | OK (словарь не тронут, 336 опций) |
| «яя» по `original_name` | 4550 / active 0 | 4550 / active 0 | OK |
| Суффиксы CAT-12 (видимые с « (арт. » / « (код 1С ») | 266 | 266 | OK |
| Группы-дубли (пересчёт CAT-11/12) | 17 / 34 карточки, все same_article | то же | OK |
| Находки ступени 4 (run `0f8a6599`) | 44 | 44 | OK |
| Findings по статусам | applied 111 / rejected 2 | то же | OK |
| Хэш неприкасаемых полей (все scope+watch) | `a8d79785…` | `a8d79785…` | OK |
| PAV `tool_type` всего | 38 877 | 38 895 | CHG = +18, объяснено (findings §5) |
| Счётчики затронутых типов | §2 | §2 | CHG ровно на переносы |

## 6. Витрина (живой API dev.proff58.ru, `tt15_vitrine.py`)

- Счётчики `?tool_type=` == eligible-числам БД (is_active+published, EAV) по
  всем восьми типам: `bp-golovki-trimmernye` 72=72, `hoz-voronki` 5=5,
  `izm-multimetry` 73=73, `prochaya-osnastka` 386=386, `krep-gaiki` 39=39,
  `krep-bolty` 194=194, `obor-smazka` 61=61, `avtomaty-predohraniteli` 1=1.
- Присутствие: все 72 активные головки в `bp-golovki-trimmernye`; 5 активных
  воронок (35608, 39284, 39286, 39290, 39291) в `hoz-voronki`; #18 в
  `izm-multimetry` — OK.
- Отсутствие в исходных типах: перенесённые не отдаются из
  `prochaya-osnastka` / `krep-gaiki` / `krep-bolty` / `obor-smazka` — OK.
- Фасеты: панель `tool_type` сконфигурирована только у `krepezh-gayki`
  (5=5) и `krepezh-bolty` (3=3) — сошлись с БД. В `osnastka-prochaya` и
  категориях воронок панели нет by design (нет привязки `CategoryAttribute` —
  конфиг, окном не трогался); `hoztovary-sad-ogorod` и `avto-na-moderaciyu`
  неактивны → 404 by design. Категории каталога не менялись (граница окна).

## 7. Границы

- Изменены только `value_option` PAV и `attrs_cache` у 130 товаров
  (108 + 15 + 7); создано 18 PAV-строк (`source=manual`).
- Названия, публикация, цены, остатки, категории — не тронуты (хэш §5).
- Новые типы не заводились; контур правил (манифест, ruleset, gate,
  фикстуры) не менялся; `taxonomy_identity` не изменился.
- Глобальные команды не запускались; push/PR не выполнялись.
- Код не менялся — `pytest` не нужен (окно данных, как TT-12).

## 8. Артефакты

- Драйвер: `scratchpad/catalog/tt15_batch.py`; разведка: `tt15_recon.py`;
  витрина: `tt15_vitrine.py`.
- `scratchpad/catalog/artifacts-tt15/`: cluster{1,2,3}-{before,after}.json,
  cluster{1,2,3}-rollback-map.json, cluster1-ids.json, global-fp.json,
  invariants-{before,after}.json, db-tt15-backups.txt.
- Findings для владельца: `scratchpad/catalog/tt-15-findings.md`
  (11056, 6170, 11, 40109, 40354, 38368 + решение по 35608 + пояснения
  по −94 и PAV +18).
- Этот протокол: `scratchpad/catalog/tt-15-report.md`.

## Приложение А. Кластер 2 — все 21 совпадений regex (состояние на момент recon)

```
pid=11     active=F stock=0 type=None          | Ареометр универсальный KRAFT электролит+тосол, в тубе с воронкой KT
pid=6170   active=F stock=0 type=None          | Фильтр-воронка для краски, 190 мкр REMIX
pid=11056  active=F stock=0 type=svar-sopla    | Мундштук-воронка к алкотестеру Динго Е-200
pid=35608  active=T stock=1 type=None          | Воронка GROZ пластиковая 1,7л
pid=38368  active=F stock=0 type=None          | Конус КА (Абрамса) с воронкой
pid=39279  active=F stock=0 type=None          | Воронка  80мм
pid=39280  active=F stock=0 type=None          | Воронка 100мм
pid=39281  active=F stock=0 type=None          | Воронка 160мм г. Самара
pid=39282  active=F stock=0 type=None          | Воронка 160мм с гибким носиком Inforce
pid=39283  active=F stock=0 type=None          | Воронка d200, 3,2литра из белой жести
pid=39284  active=T stock=0 type=None          | Воронка автомобильная пластиковая 135мм с гофр шлангом
pid=39285  active=F stock=0 type=None          | Воронка автомобильная пластиковая 160мм
pid=39286  active=T stock=0 type=None          | Воронка бытовая
pid=39287  active=F stock=0 type=None          | Воронка металлическая с гибким наконечником 370мм
pid=39288  active=F stock=0 type=None          | Воронка металлическая с гибким наконечником 630мм
pid=39289  active=F stock=0 type=None          | Воронка пластиковая с сетчатым фильтром 160 мм // Stels
pid=39290  active=T stock=1 type=obor-smazka   | Воронка разборная с гибкой ножкой, с сеточкой
pid=39291  active=T stock=0 type=None          | Воронка техническая
pid=39292  active=F stock=0 type=None          | Воронка, пластик, 19*16см FIT  РОС
pid=40109  active=F stock=0 type=None          | Колпак к воронке ВР-100
pid=40354  active=F stock=0 type=None          | Крышка к колпаку воронки ВР-100
```
