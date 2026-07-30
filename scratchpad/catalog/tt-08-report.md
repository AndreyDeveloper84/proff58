# TT-08 · протокол: переклассификация 305 товаров (recat-операция, класс 2)

Дата: 2026-07-28/29. Ветка `dev`, HEAD с коммитом TT-07 `65a350d`. Окно: одно.
Маршрут: плейбук `docs/catalog/operations/recategorize.md` (НЕ контур Phase 8 —
доказано, что контур для manual-typed товаров заблокирован provenance по
построению; защита не правилась и не обходилась). Локальная БД `proff58`.
Staging — по отдельной авторизации владельца (§7).

---

## 1. Предпосылки и защита provenance

- TT-07 закрыт: типы `gaikoverty`, `gaikoverty-ruchnye`, `bp-leska` в БД обеих
  сред (334 опции, reconcile blocking=0), коммит `65a350d`.
- Проверка маршрута (повторена read-only): все 108+193 целевых PAV несут
  `source=manual` (приоритет 100); находки очереди — `web`/`llm` (25/20) →
  `can_overwrite` = `priority_blocked` (`provenance.py:49-56,162-163`).
  Контур Phase 8 для этой задачи непригоден **по построению** — не обходили,
  не правили, код provenance не тронут ни строкой.

## 2. Критерий отбора (дословно, воспроизводим)

Зафиксирован исполняемо: `scratchpad/phase8/tt08_build_lists.py` →
`scratchpad/phase8/tt-08-lists.json` (305 товаров, 11 батчей ≤30).

- **`gaikoverty` (107):** `name ILIKE '%гайковерт%'` AND текущий
  `tool_type='dreli-shurupoverty'` AND name NOT MATCHES
  `ручн|механическ|32х33|РГ ?5|мультиплик`.
- **`gaikoverty-ruchnye` (6):** явные id 21, 23 (были `golovki`), 26213, 26214
  (были `prochaya-osnastka`), 43790 (внутри dreli-выборки — ручной, не
  электрический), 22 (был `spetsialnye-klyuchi` — кейс, ради которого тип
  заводился в TT-07).
- **`bp-leska` (192):** текущий `tool_type='prochaya-osnastka'` AND
  `name ILIKE '%леска%'` AND товар — сама леска (исключены 3 головки
  триммерные 26239, 26256, 26257) → 190; плюс явные 26724, 26749 из
  `izm-ugolniki` (леска CHAMPION «треугольник», попала в «Угольники» по форме
  сечения).
- **Исключены:** 38762–38768 (7 услуг «Ремонт гайковерта …» — не товар) и
  8832 (крюк-аксессуар) — целевого типа нет, правило stop плейбука;
  19 бензокос в `bp-trimmery` — машины, на своём месте, не тронуты;
  3 головки триммерные — остаются в `prochaya-osnastka` (типа «головки
  триммерные» нет — вынесено в §7).

## 3. Предсказание, сформулированное ДО записи (сверено в §5)

| Тип | ДО | ПОСЛЕ (предсказание) |
|---|---:|---:|
| `gaikoverty` | 0 | 107 |
| `gaikoverty-ruchnye` | 0 | 6 |
| `bp-leska` | 0 | 192 |
| `dreli-shurupoverty` | 673 | 565 |
| `prochaya-osnastka` | 2041 | 1849 |
| `golovki` | 928 | 926 |
| `spetsialnye-klyuchi` | 23 | 22 |
| `izm-ugolniki` | 156 | 154 |
| `bp-trimmery` | 107 | 107 (не трогаем) |
| PAV tool_type всего | 38833 | 38833 (update, не create) |
| UNTOUCHABLE_HASH | `be36cf755b…` | идентичен |

Rollback-map (`product_id → old_option_id → new_option_id`, 305 строк):
`scratchpad/phase8/artifacts-tt08/rollback-map.json`.

## 4. Исполнение — 11 батчей ≤30, каждый по гейт-циклу

На каждый батч: `catalog_tool_type_snapshot --product-ids …` (снимок «до») →
pg_dump → write одной `transaction.atomic` (FP-guard: текущий option ==
ожидаемому из rollback-map; затем только `value_option` + точечная
`rebuild_attrs_cache`; **source не менялся — решение владельца: `manual`**) →
postcheck (тип == новый, `attrs_cache ≡ EAV`, дублей PAV нет) → снимок «после».

| Батч | moved | Батч | moved |
|---|---:|---|---:|
| G1 | 30 | L1–L6 | 30 × 6 |
| G2 | 30 | L7 | 12 |
| G3 | 30 | | |
| G4 | 23 (17 эл. + 6 ручных) | | |

Итого: **305 moved, 0 ошибок FP-guard, 0 postcheck-ошибок.**
Артефакты: `artifacts-tt08/{G1..G4,L1..L7}-{before,after}.json`,
`db-tt08-{batch}.sql.gz` (11 дампов).

### Испытание отката (батч G1, сценарий «смена существующего типа»)

```
rollback --from G1-after --to G1-before         dry-run: write=30 conflict=0
rollback --from G1-after --to G1-before --apply written=30, post-audit=PASS
  → состояние возвращено (включая 3 товара с недreli-исходными типами —
    21/23 в golovki, 22 в spetsialnye-klyuchi; первичная проверка «30 в dreli»
    показала 27 именно потому, что rollback честно вернул каждому своё)
forward  --from G1-before --to G1-after --apply written=30, post-audit=PASS
  → все 30 == плану (mismatch [])
```

Откат для нового сценария работает, включая честное восстановление
разнородных исходных типов и `attrs_cache`.

## 5. Post-audit — предсказание == факт

Фактические счётчики (PAV): `gaikoverty` 107, `gaikoverty-ruchnye` 6,
`bp-leska` 192, `dreli-shurupoverty` 565, `prochaya-osnastka` 1849,
`golovki` 926, `spetsialnye-klyuchi` 22, `izm-ugolniki` 154,
`bp-trimmery` 107 — **все совпали с §3**. `UNTOUCHABLE_HASH` =
`be36cf755b…` (идентичен ДО: цена, остаток, категория, название, артикул,
публикация целы). PAV total 38833 (не изменился). Дублей PAV нет.

## 6. Витрина (живой запрос `products_in(category, tool_type=slug)`)

- `gaikoverty`: товары видны в фильтре, счётчик фильтра == прямому PAV
  (пример: product 433, count=107 direct=107 — весь тип в одном поддереве
  «Электроинструмент»);
- `gaikoverty-ruchnye`: product 21, count=3 direct=3 OK;
- `bp-leska`: product 26669, count=41 direct=41 OK.
- `STOREFRONT_ALL_OK: True`. Соседние разделы: `dreli-shurupoverty`
  похудел ровно на перенесённые (673→565), `prochaya-osnastka` (2041→1849) —
  счётчики выше, ничего не сломано.

## 7. Вынесенное владельцу и долги

1. **Staging:** 11 батчей готовы к воспроизведению (списки, rollback-map,
   драйвер). Промпт требует **отдельную авторизацию владельца на каждый батч**
   + согласование с CAT-05/CAT-06/PARS-05 (PARS-05 последним). Жду GO
   (можно пакетно: «все 11»).
2. **Услуги ремонта (38762–38768) и крюк (8832)** — не перенесены (нет
   целевого типа). Если нужен тип «Услуги» или решение по аксессуару —
   отдельное продуктовое решение.
3. **3 головки триммерные** (26239, 26256, 26257) — остались в
   `prochaya-osnastka`; кандидат на тип «Головки триммерные» в будущий пакет
   (по аналогии с TT-07, отдельным решением).
4. Наблюдение (не часть задачи): 22 получил `gaikoverty-ruchnye` вместо
   зонтика `spetsialnye-klyuchi` — кейс закрыт как задумано в TT-07.

## 8. Границы

- Менялся только `tool_type` (PAV `value_option` + точечный `attrs_cache`);
  отпечаток неприкасаемых полей идентичен (§5). Категория не трогалась,
  `category_is_manual` сохранён.
- Provenance не правился и не обходился; source записей — `manual` по
  решению владельца (вопрос вынесен до записи, не решён молча).
- Новые типы не заводились; контур (манифест, gate, ruleset, артефакты) не
  тронут после коммита TT-07; глобальные команды не запускались.
- Tracked-файлов это окно в TT-08 не меняло (только untracked-артефакты в
  `scratchpad/`); push/PR не выполнялись; pg_dump перед каждым батчем.

## 9. Артефакты

- Критерий/списки: `scratchpad/phase8/tt08_build_lists.py`,
  `tt-08-lists.json`, `tt-08-audit.txt`
- Rollback-map: `scratchpad/phase8/artifacts-tt08/rollback-map.json`
- Снимки H5: `artifacts-tt08/{batch}-{before,after}.json` (22 файла)
- Дампы: `artifacts-tt08/db-tt08-{batch}.sql.gz` (11 файлов)
- Драйверы: `tt08_state.py`, `tt08_batch.py`, `tt08_storefront.py`
- Этот протокол: `scratchpad/catalog/tt-08-report.md`

---

# STAGING (2026-07-29, GO владельца)

## С1. Preflight

Счётчики и хэш на стенде == локальному ДО: `UNTOUCHABLE_HASH be36cf755b…`,
dreli 673, prochaya 2041, golovki 928, izm-ugolniki 156, spetsialnye 23,
bp-trimmery 107, PAV 38833, `gaikoverty`/`bp-leska` = 0. Типы посеяны в
TT-07 (334 опции). Полный бэкап:
`/home/taximeter/backups/staging/db-2026-07-29-1227.sql.gz` (+ media).

## С2. Исполнение

Списки, rollback-map и драйвер доставлены в контейнер (`/tmp/`; код стенда —
image, не bind-mount). 11 батчей тем же циклом: snapshot → pg_dump (db-only,
`db-tt08-{G1..L7}.sql.gz`, ~21,5 МБ каждый, настоящие) → write одной
`transaction.atomic` (FP-guard + postcheck) → snapshot. Итог:
**305 moved, 0 ошибок** (G1–G4: 30/30/30/23; L1–L7: 30×6+12). Лог:
`artifacts-tt08/staging-run.log`. Два операционных сбоя до прогона (CRLF в
сгенерированном драйвере; stdin скрипта съеден `docker compose exec` при
запуске через `bash -s`) — до записи, влияния нет, лечение зафиксировано:
LF-окончания, запуск из файла на хосте.

## С3. Post-audit — числа == локальным

Счётчики PAV на стенде: `gaikoverty` 107, `gaikovery-ruchnye` 6,
`bp-leska` 192, dreli 565, prochaya 1849, golovki 926, spetsialnye 22,
izm-ugolniki 154, bp-trimmery 107, PAV total 38833 — **все 10 чисел
совпали с предсказанием и с локальными**. Витрина `products_in` по трём
новым типам — OK, счётчики == БД (те же значения, что локально).

## С4. Внешнее изменение на стенде — НЕ наше (важно)

Untouchable-хэш стенда после цикла: `560f7ee7…` ≠ утреннему `be36cf755b…`.
Расследование по полной проекции (47 225 строк, сравнение с локальной):

- все расхождения — **только поле `is_active`** (True→False), 2 547 товаров,
  остальные поля идентичны; 2 546 из 2 547 — со `stock=0`;
- 2 493 из 2 547 — **вне скоупа TT-08**; 54 — внутри, у всех тип выставлен
  корректно (проверено);
- `updated_at` перевёрнутых — июнь (bulk `.update()` его не двигает) —
  деактивация произошла сегодня между preflight (~09:20 UTC) и post-audit;
  в `django_admin_log` за сегодня записей нет, путь 1С пишет `is_active_1c`,
  а не `is_active`;
- моя запись физически не могла это сделать: батч-драйвер пишет только
  `PAV.value_option` (`update_fields=["value_option"]`) и
  `rebuild_attrs_cache` (`update_fields=["attrs_cache"]`).

Вывод: параллельный процесс (availability-деактивация нулевых остатков или
одно из окон CAT-05/CAT-06/PARS-05) снял с публикации 2 547 товаров во время
нашего цикла — **нарушение договорённости «write не одновременно»**, либо
штатный процесс, о котором окно не знало. Вынесено владельцу: если это
нештатное — проверить; наша операция ни причём, её write-set доказанно
не пересекается (§С3, код драйвера).

## С5. Артефакты staging

- Снимки H5: `/tmp/tt08-{G1..L7}-{before,after}.json` (в контейнере web)
- Дампы: `/home/taximeter/backups/staging/db-tt08-*.sql.gz` (11 шт) +
  `db-2026-07-29-1227.sql.gz` (полный, до цикла)
- Лог: `scratchpad/phase8/artifacts-tt08/staging-run.log`; проекции:
  `proj-local.json`, `proj-staging.json`; драйвер: `tt08_staging_driver.sh`
