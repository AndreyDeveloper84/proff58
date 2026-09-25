# FOUNDATION-AXES-03 — Facet Visibility Apply → **PASS**

Дата: 2026-09-12. Продолжение [2026-09-12-foundation-axes-02.md](2026-09-12-foundation-axes-02.md)
(RESEARCH_COMPLETE; owner GO на exact 5 HIDE_FOR_NOW). Два гейта: Phase A
(config `bind:false` + regression tests → PR → CI → merge → deploy) → Phase B
(post-deploy plan → immutable deletion manifest → baseline → backup → drift gate →
controlled deletion → post-audit). **HIDE_FOR_NOW = visibility decision, не отказ от
оси: PAV, Attribute, AttributeOption, regex и извлечение сохранены.**

## Вердикт: PASS

- Ровно пять `bind:false` в правилах · ровно пять `CategoryAttribute` удалены
  (id 422, 425, 427, 428, 432) · **CategoryAttribute 303 → 298** · PAV Δ **0**
  (по пяти парам deleted/changed/added 0) · Attribute / Option / ProductImage /
  taxonomy / tool_type Δ 0 · attrs_cache образцов не изменился · 6 positive controls
  целы · API: исчезли только целевые фасеты · rerun `load_attributes` не восстанавливает
  привязки · extraction при `bind:false` работает · G-4 чистый · unrelated changes 0.

## 1. Exact target set (решение FA-02)

| CA id | категория | ось | attr id | PAV в поддереве | live / filled | причина |
|---|---|---|---|---|---|---|
| 422 | 91 Биты | package_quantity | 85 | 47 | 262 / 6 | 2 %, у 147 из 148 незаполненных «шт» в названии нет |
| 428 | 82 Круги | package_quantity | 85 | 131 | 492 / 43 | 9 %, фасовка только у подмножества; листья 83/85 — одно значение |
| 425 | 361 Дюбели | package_quantity | 85 | 31 | 41 / 10 | 24 %, в наличии 2/22 |
| 432 | 106 Мешки-пылесборники | package_quantity | 85 | 30 | 71 / 22 | значения только 5 и 2 |
| 427 | 448 Кремы | volume | 124 | 3 | 4 / 3 | одно distinct-значение → «Диапазон недоступен» |

Ревалидация до изменений (стенд `4ba0b0d`): пять привязок существуют по одной,
похожих в предках/потомках нет, FK на `CategoryAttribute` в моделях нет; baseline =
финал FA-01. Positive controls: 429 (105 linear_length), 436 (356), 434 (86),
437 (408), 439 (217 «Объём кузова»), 424 (193).

## 2. Phase A — config + tests (PR #764, merge `65a71d2`)

- `data/attribute_rules.json`: **ровно пять `bind: true → bind: false`** (+ `_note`);
  regex / skip_if / units / display_name / derive / quarantine / taxonomy — без изменений.
- `apps/catalog/test_fa03_facet_visibility.py` (боевой словарь): negative — plan и apply
  `load_attributes` не создают пять привязок; positive — 6 контролей создаются, 217 с
  `display_name «Объём кузова»`; extraction — 5 реальных названий извлекаются при
  `bind:false`, накопленный PAV после `load_attributes` цел; ровно пять `bind:false`
  помечены FA-03.
- Python / frontend / `TECH_FACET_MIN_SHARE` / `RangeFacet` — **0 изменений**.
- CI 4/4 green; deploy run 34684680628 success; стенд HEAD `65a71d2`, блоб правил
  `22119530…` = origin/dev, контейнеры healthy.

## 3. Phase B — post-deploy plan

`load_attributes --dry-run --strict-bindings`: атрибуты 0/0/96 · варианты 0/0/302 ·
**привязки create 0 / update 0 / keep 228** (было 233: пять целей больше не требуются
контрактом), dead 0; `Объём кузова` в target 217 сохранён.

`build_facets` до удаления: все пять целевых фасетов PRESENT (covered 6 / 43 / 10 / 22 /
3) — негативная проверка после удаления содержательна.

## 4. Manifest, baseline, backup, drift, deletion

- Immutable deletion manifest (5 строк `CategoryAttribute_id | category | attribute |
  display_name | current_bind=False | DELETE_BINDING_ONLY`): **sha256 `d27ee384…`**;
  persistent `/home/taximeter/backups/staging/fa03-manifest-20260912.json`.
- Fresh baseline: Attribute 110 / Option 675 / CategoryAttribute 303 / PAV 84 839
  (max id 87 856) / ProductImage 787 / migrations 128 + полные PAV-снимки пяти пар,
  23 образца `attrs_cache`, 6 контрольных строк.
- Backup **`pre-fa03-20260912-1219.sql.gz`**: pg_dump exit 0, 22.6 MB, gzip ok, sha256
  `c32298c0…`; COPY `catalog_categoryattribute` содержит ровно 5 целевых строк.
  Recovery: восстановить эти 5 строк из дампа (или полный restore).
- Drift gate: PASS (ids, display, sha манифеста, контроли, глобальные counts).
- Deletion: ORM `select_for_update` + сверка manifest ≠ live → `.delete()` →
  `{'catalog.CategoryAttribute': 5}`; сигнал `post_delete` сбросил кэш фасетов.

## 5. Post-audit

| | до | после | Δ |
|---|---|---|---|
| CategoryAttribute | 303 | **298** | −5 = exact ours {422, 425, 427, 428, 432}, foreign 0, added 0 |
| PAV | 84 839 | 84 839 | 0 (volume 858 / package_quantity 1043 / linear_length 545 без изменений) |
| Attribute / AttributeOption | 110 / 675 | 110 / 675 | 0 |
| ProductImage / migrations / Category / tool_type PAV | 787 / 128 / 362 / 39 628 | те же | 0 |

- Контроли после: 429 / 436 / 434 / 437 / 439 («Объём кузова») / 424 — без изменений.
- `build_facets`: цели — фасет absent у 91, 82, 361, 106, 448; остальные фасеты листов
  не задеты; контроли — PRESENT с прежним covered (76 / 43 / 56 / 34 / 16 / 91).
- Публичный API `/api/catalog/categories/<slug>/facets/`: `osnastka-bity` → только
  `bit_type`; `krugi` → без package_quantity; `krepezh-dyubeli` → diameter/length;
  `meshki-pylesborniki`, `siz-kremy-zashchity-kozhi` → `[]`; контроли на месте.
- Rerun `load_attributes --dry-run --strict-bindings`: create 0 / update 0 / keep 228.
- Extraction (движок на стенде, read-only): bity → 10, krugi-shlif → 5, krep-dyubeli →
  100, meshki-pylesos → 5, siz-kremy → 0,1 л.

## 6. Инцидент (observation, не чинился)

Хост-nginx отдаёт `dev.proff58.ru → 301 → proff58.ru` (один IP); ответ по `proff58.ru`
отражает ровно staging-набор данных (числа совпадают с БД стенда). На FA-03 не
повлияло; routing стенда/прода — отдельный infra-check.

## 7. Не тронуто

37 пистолетов + сопло под `str-germetiki`, 5 stale `tool_type` в кэше, `svar-ballony` в
217, 47 tank-исключений, 15 карантинных «0,52 мл», UI GAP-ы (порог 25 %, «Диапазон
недоступен», шаг слайдера, «10 000шт»).

## 8. Canonical baseline после FA-01 → FA-03 (staging, 2026-09-12)

**Schema/data:** Attribute 110 · AttributeOption 675 · CategoryAttribute 298 ·
PAV 84 839 · ProductImage 787 · migrations 128.

**Оси активны:** `volume` (id 124), `package_quantity` (id 85), `linear_length` (id 123).

**Скрытые привязки (ровно пять, `bind:false`, CategoryAttribute отсутствует):**
91 / package_quantity · 82 / package_quantity · 361 / package_quantity ·
106 / package_quantity · 448 / volume.

**Видимые привязки FA-01 (16):** linear_length 105; package_quantity 199, 427, 363,
364, 356, 102, 86; volume 184, 193, 220, 436, 408, 217 («Объём кузова»), 334, 442.

## 9. Следующие треки (не начаты)

1. Docs closeout FA-01 → FA-03 (этот цикл).
2. Correction manifest research — 37 пистолетов (`str-germetiki → str-pistolety`),
   5 stale cache, `svar-ballony` в 217 — по отдельному OWNER GO.
3. Infra-check редиректа dev-домена; UI GAP-ы фасетов — отдельными решениями.
