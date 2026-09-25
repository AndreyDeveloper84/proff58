# FOUNDATION-AXES-01 — volume + package_quantity + linear_length + SELECT preflight → **PASS**

Дата: 2026-09-12. Implementation track по закрытому research gate
[2026-09-12-foundation-axes-research.md](2026-09-12-foundation-axes-research.md)
(owner GO после docs closeout research, PR #761). Source of truth — три exact
proposal в `appendix/2026-09-12-foundation-axes/` и
[2026-09-12-select-preflight-audit.md](2026-09-12-select-preflight-audit.md).
Продолжение — [2026-09-12-foundation-axes-02.md](2026-09-12-foundation-axes-02.md)
(visibility audit) и [2026-09-12-foundation-axes-03.md](2026-09-12-foundation-axes-03.md)
(apply). **Этот отчёт — история FA-01 как она была на момент закрытия; последующие
решения по видимости фасетов здесь не переписываются.**

## Вердикт: PASS

- Attribute **+2** (`volume` id 124 «Объём» л, `linear_length` id 123 «Длина» м;
  `package_quantity` id 85 — reuse) · AttributeOption **+0** · CategoryAttribute **+21**
  (все живые, 217 «Тележки и тачки» с `display_name «Объём кузова»`).
- Immutable manifest = **2384 CREATE**, apply = **ровно 2384 PAV** (ImportRun #147,
  id 85473–87856 подряд, все `regex/40`) · G-4: `global +2384 = exact ours +2384 + foreign 0`
  · rerun `create 0 / update 0 / prune 0` · attrs_cache по управляемым ключам mismatch 0.
- `length` (4356 PAV, в т.ч. 78 метровых) / `tape_length` 304 / `cable_length` 130 /
  `piece_count` 496 — без изменений; schema/image/taxonomy/tool_type side effects 0.
- SELECT preflight fail-closed стоит до `ImportRun.create`; silent skip удалён из кода.

## 1. Контракт

Один bounded PR с четырьмя частями: **A** `volume` (л, мл → л через `scale 0.001`,
без нового conversion-кода); **B** `package_quantity` — расширение существующей оси на
exact Tier 1 + Tier 2; **C** `linear_length` (м) по классу товара; **D** T2 preflight +
light T3 runtime-guard. Tree hygiene, `tank_volume`, дюймы шины, `cable_section` —
не входят. Forecast research: 905 / 977 / 545 = 2427 CREATE — прогноз, не контракт
записи.

## 2. Код / config (PR #762, merge `5f92cab`)

| файл | что |
|---|---|
| `data/attribute_rules.json` 149 → 179 блоков | A: 3 append + 19 new; B: 15 append + 1 new (`meshki-pylesos`); C: 5 append + 11 new. Единственное отклонение от proposal — решение владельца: тачки `bind: true` + `display_name «Объём кузова»` |
| `data/attribute_quarantine.json` | +15 `data_defect` «0,52 мл / 0.5 мл» (ЛКМ KUDO/ТРОЛЬ-АВТО, спрей), ось `volume` — не нормализуются |
| `apps/catalog/attribute_preflight.py` (новый, чистый) | `required_select_options` / `check_select_options` / `format_missing`; lint `derive.set_option ∈ options` |
| `enrich_attributes.py` | preflight `required options ⊆ AttributeOption` **только по блокам текущей выборки**, до `ImportRun.create`, `CommandError(returncode=2)` и в dry-run, и в write, **обходного флага нет**; отсутствующий `Attribute` — тоже exit 2 (было stderr + exit 0); runtime-guard: исчезнувшая опция → raise в транзакции (rollback, `ImportRun → failed`), серверный курсор закрывается до отката |
| `load_attributes.py` | `display_name` объявления оси → `CategoryAttribute.display_name` только при создании привязки |
| тесты | `test_foundation_axes_01.py` (A–E владельца + фикстуры трёх осей), обновлены инварианты `test_har20_package_quantity` (owners → явный реестр), `test_kelmy_topory_lezviya`, `test_drf1450_mm_axis` (леска = diameter + linear_length), `test_attribute_quarantine` |
| `docs/catalog/operations/README.md` | preflight реализован, exit code 2 |

Exit-code contract: **2** = preflight/contract failure (совпадает с `EXIT_INVALID`
gate-контура).

## 3. Phase B — `load_attributes` (после deploy `5f92cab`)

| | before | after | Δ |
|---|---|---|---|
| Attribute | 108 | 110 | +2 |
| AttributeOption | 675 | 675 | 0 |
| CategoryAttribute | 282 | 303 | +21 (dead/not_found/ambiguous 0; 6 flag_diff — чужие, suppressed) |

Rerun-план no-op. Prebind до PR: 0 пустых привязок из 21. Preflight после
материализации: OK — 302 варианта по 179 типам, missing 0.

## 4. Стоп-проверка манифеста и narrowing (PR #763, merge `4ba0b0d`)

Первый dry-run дал ровно forecast (volume 905 / package_quantity 981 / linear_length
545 = 2431). Семантический аудит плана по первым словам названий нашёл **внутри
разрешённых типов** то, что граница владельца («бак устройства / ёмкость встроенного
узла / совместимая тара — NO») запрещает:

| класс | tool_type | строк (в наличии) | решение |
|---|---|---|---|
| «Пистолет для герметиков 310/600 мл» | `str-germetiki` (пистолеты типизированы как герметики) | 20 (11) | совместимая туба; research п. 12 сам ставил NO — `skip_if «пистолет»` |
| «Маслонагнетатель … с баком 16л», «Нагнетатель С-321М 25л 220В», «Установка … с баком 20л», «на ведро 20л» | `obor-smazka` | 17 (3) | бак устройства / совместимая тара — `skip_if «нагнетател»/«маслонагнетател»/«солидолонагнетател»/«установка»/«на ведро»` |
| «Пеногенератор 0,75 л / 25 л / 50 л» | `obor-pena` | 8 (2) | бачок насадки = класс бачка краскопульта — `skip_if «пеногенератор»/«пенокомплект»` |

По §20 контракта это hard-stop → запись не выполнялась; сужение fail-closed отдельным
PR; повторный dry-run: **ровно −47, +0, 0 изменённых значений**. Побочно замолчали
2 «Маслёнка-нагнетатель 0,25/0,5 л» (принято: молчание лучше догадки). Три research-кейса
`cases.json` теперь намеренно отрицательные. Future `tank_volume` — отдельный research.

## 5. Phase C — dry-run, forecast vs actual, hard-stop аудит

| ось | forecast | dry-run №1 | итог | в наличии | CONFIRM | PROTECTED | QUARANTINE |
|---|---|---|---|---|---|---|---|
| volume | 905 | 905 | **858** | 94 | 0 | 0 | 15 (в audit, в CREATE 0) |
| package_quantity | 977 | 981 | **981** | 270 | 0 | 0 | — |
| linear_length | 545 | 545 | **545** | 61 | 0 | 0 | — |
| итого | 2427 | 2431 | **2384** | 425 | 41 962 keep (весь каталог) | 45 skip priority (scraper на цепях/шинах, до волны) | 18 записей |

Provenance: package_quantity +4 — research просканировал 11 из 20 стержней клеевых
(все 15 реальные «40шт / 12 шт»); volume −47 — narrowing §4.
Hard-stop: CREATE вне трёх осей 0; вне proposal-типов 0; мешки пылесосов / баки в
volume 0; 15 дефектов в CREATE 0; update 0; prune 0; conflict 0; missing option 0;
new option 0.

## 6. Manifest, baseline, backup, drift, apply

- Immutable manifest 2384 строк: sha256 `e35c128b…`; persistent
  `/home/taximeter/backups/staging/fa01-manifest-20260912.json`.
- Fresh baseline перед записью: PAV 82 455 (max id 85 472), Attribute 110, Option 675,
  CategoryAttribute 303, ProductImage 787, migrations 128; полные снимки
  `length` / `tape_length` / `cable_length` / `piece_count`.
- Backup `pre-fa01-20260912-1008.sql.gz` (pg_dump exit 0, 22.5 MB, gzip ok, sha256
  `f5889b76…`). Recovery: полный restore или targeted — удалить PAV id 85473–87856 и
  пересобрать кэш этих товаров (ids в `fa01-attribution-20260912.json`).
- Drift gate: блоб правил `2e8b8047…` = origin/dev, повторный dry-run — тот же sha256.
- Apply: ImportRun **#147**, status done, exit 0.

## 7. Post-audit

- Rerun dry-run: create 0 / update 0 / prune 0; прежние CREATE → keep (volume 858,
  package_quantity 1043 = 62 + 981, linear_length 545); unknown options 0; silent SELECT
  skip 0 (ветка удалена).
- G-4: PAV Δ 2384 = ours 2384 + foreign 0; Attribute / Option / Binding / Image /
  migrations Δ 0.
- attrs_cache по 2446 тронутым товарам: наши ключи mismatch 0; 5 расхождений в ключе
  `tool_type` (43228, 43232, 43237 — PAV `hoz-shlangi`; 15452, 15711 — `krep-svp`) —
  до волны, не наши, broad repair не делался.
- volume на исключённых типах 0; на 15 дефектах 0; товаров с обеими осями упаковки 0;
  с volume и linear_length 0.

## 8. Покрытие фасетов (на момент FA-01; UI-порога в `facets.py` нет)

≥ 50 % live: volume 220 Тара 95 %, 436 Масла 91 %, 184 Опрыскиватели 74 %, 193 Герметики
51 %, 334 / 442 / 448 (4–6 товаров); package_quantity 427 Стяжки 98 %, 363 Заклёпки 97 %,
199 СВП 95 %, 108 Скобы 92 %, 364 Гвозди 59 %; linear_length 105 Леска 96 %.
Ниже: volume 408 Смазочное 47 %, 217 Тачки 29 %; package_quantity 102 Абразивы 49 %,
356 Саморезы 47 %, 106 Мешки 31 %, 361 Дюбели 24 %, 86 Пильная 14 %, 82 Круги 9 %,
91 Биты 2 %. **Рекомендация FA-01 — отдельный visibility audit**, выполнен как FA-02.

## 9. Инциденты

1. Research-gap по семантике volume — закрыт до записи (§4).
2. В тесте E raise внутри `iterator()` ронял тестовое соединение при откате — курсор
   закрывается до raise.

## 10. Не входило / оставлено

`tank_volume` (47 сужённых + компрессоры/генераторы/пылесосы), 20 пистолетов в
`str-germetiki`, 5 stale `tool_type`-подписей кэша, tree hygiene — отдельные треки.
