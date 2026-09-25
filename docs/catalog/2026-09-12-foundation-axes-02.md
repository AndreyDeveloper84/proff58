# FOUNDATION-AXES-02 — Facet Exposure Audit (read-only) → **RESEARCH_COMPLETE**

Дата: 2026-09-12. Продолжение [2026-09-12-foundation-axes-01.md](2026-09-12-foundation-axes-01.md)
(PASS; рекомендация — visibility audit низкопокрытых фасетов). Read-only decision
track по owner GO: **какие из 21 новых `CategoryAttribute` FA-01 стоит показывать
пользователю уже сейчас**. DB / код / config / кэш writes = 0. Решения применены в
[2026-09-12-foundation-axes-03.md](2026-09-12-foundation-axes-03.md).

## Вердикт: RESEARCH_COMPLETE

**16 KEEP_VISIBLE · 5 HIDE_FOR_NOW · NEEDS_ENRICHMENT_RESEARCH 0 ·
NEEDS_CATEGORY_SPLIT_RESEARCH 0.** Глобальный threshold не вводится. Baseline на момент
аудита = финал FA-01 (Attribute 110 / Option 675 / CategoryAttribute 303 / PAV 84 839 /
ProductImage 787 / migrations 128) — foreign activity 0.

## 1. Пайплайн фасета (end-to-end, код)

`CategoryAttribute(is_filter=True) ∧ Attribute.is_filterable` →
`queries._category_filter_attributes` (наследуется **вниз** по дереву, closest-wins по
подписи/группе) → `facets.build_facets`: GROUP BY `attrs_cache` по **видимым** товарам
(`is_active ∧ status=PUBLISHED`, `filters.visible_products`); пустой counter → фасет
не эмитится; `MAX_FACET_VALUES = 100` → API `/categories/<slug>/facets/` →
`frontend/lib/adapters.ts` (attr_* вне base → kind `tech`) → **`frontend/lib/listing.ts`**.

- **Скрытый порог существует — `TECH_FACET_MIN_SHARE = 0.25`** (`sidebarFacets`): на
  «широкой» категории (nav-панель содержит >1 tool_type с товарами) и **без выбранного
  tool_type** технический фасет показывается только при `covered/total ≥ 25 %`; в листе
  с одним типом или после выбора типа — всегда, даже с одним товаром. Бэкенд
  coverage-гейта не имеет.
- `bind` в правилах = существование `CategoryAttribute`, ничего больше.
- Decimal-оси (все три FA-01) рендерятся **dual-слайдером** (`RangeFacet`): одно
  distinct-значение → блок «Диапазон недоступен»; шаг слайдера 1 (`RANGE_STEP` задан
  только для price) — сублитровые объёмы выбираются только полями ввода.

## 2. Decision table (live = active+published; «show» = виден без выбора типа)

| # | Category | Axis | Live | Filled | Cov | In-stock filled | Distinct | broad / show | Decision |
|---|---|---|---:|---:|---:|---|---:|---|---|
| 1 | 105 Леска для триммера | linear_length | 79 | 76 | 96 % | 21/24 | 29 | 2 типа / да | KEEP_VISIBLE |
| 2 | 199 Плиточный инструмент | package_quantity | 21 | 20 | 95 % | 1/1 | 4 | нет / да | KEEP_VISIBLE |
| 3 | 427 Хомуты-стяжки | package_quantity | 61 | 60 | 98 % | 33/33 | 5 | нет / да | KEEP_VISIBLE |
| 4 | 363 Заклёпки | package_quantity | 72 | 70 | 97 % | 29/29 | 8 | нет / да | KEEP_VISIBLE |
| 5 | 364 Гвозди | package_quantity | 68 | 40 | 59 % | 21/34 | 8 | 2 типа / да | KEEP_VISIBLE |
| 6 | 356 Саморезы | package_quantity | 91 | 43 | 47 % | 39/67 | 20 | нет / да | KEEP_VISIBLE |
| 7 | 102 Абразивы | package_quantity | 235 | 114 | 49 % | 35/67 | 4 | 6 типов / да | KEEP_VISIBLE (72 % = «5 шт») |
| 8 | 86 Пильная оснастка | package_quantity | 401 | 56 | 14 % | 37/207 | 4 | 3 типа / **нет** | KEEP_VISIBLE — наследование: лист 90 Пилки 38/41 = 93 %, лист 89 Полотна 18/56, лист 87 Диски — фасет не эмитится; split не нужен |
| 9 | 82 Круги | package_quantity | 492 | 43 | 9 % | 7/200 | 4 | 4 типа / нет | **HIDE_FOR_NOW** — subset (круги на липучке), 422 без «шт»; листья 83 (3/97) и 85 (11/115) — одно значение |
| 10 | 91 Биты | package_quantity | 262 | 6 | 2 % | 4/190 | 2 | 6 типов / нет | **HIDE_FOR_NOW** — у 147 из 148 незаполненных числа со «шт» нет |
| 11 | 361 Дюбели | package_quantity | 41 | 10 | 24 % | 2/22 | 7 | нет / да | **HIDE_FOR_NOW** — 6 из 10 одна линейка ЗУБР ТФ6; роста из названий нет |
| 12 | 106 Мешки-пылесборники | package_quantity | 71 | 22 | 31 % | 17/46 | 2 | нет / да | **HIDE_FOR_NOW** — значения только 5 и 2; 49 одиночных мешков без числа |
| 13 | 184 Опрыскиватели | volume | 23 | 17 | 74 % | 4/5 | 8 | нет / да | KEEP_VISIBLE |
| 14 | 193 Герметики и пены | volume | 179 | 91 | 51 % | 28/48 | 21 | 10 типов / да | KEEP_VISIBLE |
| 15 | 220 Тара и ёмкости | volume | 60 | 57 | 95 % | 10/10 | 14 | 2 типа / да | KEEP_VISIBLE |
| 16 | 436 Масла и смазки | volume | 47 | 43 | 92 % | 9/10 | 9 | 2 типа / да | KEEP_VISIBLE (74 % = 1 л) |
| 17 | 408 Смазочное оборудование | volume | 73 | 34 | 47 % | 6/24 | 13 | 3 типа / да | KEEP_VISIBLE — все 34 значения семантически чистые после #763 (шприцы, маслёнки, ёмкость, воронка) |
| 18 | 217 Тележки и тачки | volume «Объём кузова» | 56 | 16 | 29 % | 1/3 | 7 | 8 типов / да (0,29 ≥ 0,25) | KEEP_VISIBLE — 16/30 своего типа = 53 %, 65–140 л; семантика не пересматривается |
| 19 | 334 Антипригарные средства | volume | 4 | 4 | 100 % | 2/2 | 3 | нет / да | KEEP_VISIBLE (малая категория) |
| 20 | 442 Мешки и пакеты | volume | 6 | 4 | 67 % | 0/2 | 3 | нет / да | KEEP_VISIBLE (малая; при фильтре «в наличии» исчезает сам) |
| 21 | 448 Кремы | volume | 4 | 3 | 75 % | 3/3 | **1** | нет / да | **HIDE_FOR_NOW** — одно значение 0,1 л → «Диапазон недоступен» |

Малые категории (334, 442, 448) не резались по проценту; 448 скрывается только из-за
одного distinct-значения. Процент не был единственным критерием: смотрели абсолюты
`filled/live`, распределение значений, in-stock, per-tool_type и per-leaf, паттерн
отсутствия (есть ли токен «шт»/«л» в названии).

## 3. Missing-data patterns (главные)

- Биты 91: 148 незаполненных своего типа, у 147 токена «шт» нет — данных в названиях нет.
- Круги 82: 422 одиночных круга без токена; фасовка релевантна подмножеству.
- Пильная оснастка 86: 270 пильных дисков (0), 10 полотен «(1шт)» — по дизайну оси (≥2).
- Гвозди 364: 4 «10 000шт» (пробел в тысячах) молчат, 9 «ящик 25 кг».
- Смазочное 408: 4 нагнетателя молчат намеренно (#763), 28 без литров.
- Тачки 217: 14 тачек без объёма в названии; 25 чужих (тележки, колёса, носилки).

## 4. Карантин и tank semantics

15 «0,52 мл»: все `is_active=False`, volume PAV 0 — на покрытие не влияют.
47 tank-исключений не возвращаются; `tank_volume` не проектировался.

## 5. Observations — только наблюдение, НЕ решения (остаются unresolved)

- **Пистолеты для герметиков под `tool_type=str-germetiki`: не 20, а 37 (+ 1 сопло)**,
  все в листе 193, 17 активных, 9 в наличии — IDs 37515–37545, 38189–38194, 37811;
  при этом тип `str-pistolety` существует (2 товара в 193).
- 5 stale `tool_type`-подписей в attrs_cache: 43228, 43232, 43237 (PAV `hoz-shlangi`,
  кэш «Удлинители…»), 15452, 15711 (PAV `krep-svp`, кэш «Тросы…»).
- `svar-ballony` (1 товар) в листе 217 «Тележки и тачки».
- UI GAP: порог 25 % живёт только на фронте и не задокументирован в `docs/catalog`;
  decimal-фасет с одним значением рендерит «Диапазон недоступен»; шаг слайдера 1 для
  сублитровых `volume` (193, 408); regex не читает «10 000шт» с пробелом.

## 6. Zero-write

DB writes 0 · code 0 · config 0 · taxonomy/tool_type 0 · cache 0 · collector 0 · images 0.

## 7. Рекомендация (принята владельцем)

1. Facet visibility apply — 5 HIDE_FOR_NOW: `bind:false` + удаление 5 привязок, PAV не
   трогаются → FA-03.
2. Correction manifest research — 37 пистолетов, 5 stale cache, `svar-ballony` в 217.
3. Docs closeout FA-01 → FA-02 → FA-03.
