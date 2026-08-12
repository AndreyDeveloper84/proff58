# Phase 8 · ступень 3 — протокол: real batch 20, findings + ручная модерация

Дата: 2026-07-28. Ветка `dev`, HEAD `e8c86ef3773f9a7d951462ad7e35494353f0acf5`
(== `origin/dev` на старте окна). Окно: одно. БД: локальная dev `proff58`
(`postgres://proff:proff@localhost:5432/proff58`). Regression: отдельная БД
`proff58_ph8reg3` (`--create-db`). Staging не трогался. Apply к каталогу не
выполнялся (доказательство — §7).

Окружение всех команд:

```bash
export DJANGO_SETTINGS_MODULE=config.settings.dev PYTHONIOENCODING=utf-8 \
       FEATURE_CATALOG_PROCESSING=True \
       DATABASE_URL="postgres://proff:proff@localhost:5432/proff58"
```

---

## 0. Стартовое состояние (гейты)

- **Словарь вылечен и подтверждён фактом:** `AttributeOption(tool_type)` —
  **329 строк / 329 уникальных slug**; `izm-areometry` («Ареометры
  (денсиметры)») присутствует (TT-01). `catalog_taxonomy_reconcile`:
  `identity_equal=True` (manifest v1, identity `524d4e317a80…`), все
  `blocking/* = 0`; advisory: `manifest_unused_option = 5` (`hoz-schetchiki`,
  `izm-areometry`, `metchiki`, `osnastka-rezbonarez`, `plashki`) —
  информационно, не блокер. Legacy-хэш живого словаря очереди:
  `a583a9aefeec…b2f1` (новый, закономерен после лечения словаря).
- **Tracked-дерево на старте чистое** (`git status --short --untracked-files=no`
  пусто), HEAD == `origin/dev`.
- **Отпечаток каталога ДО** (`catalog_fingerprint.py`, методика ст. 1):
  `8783f63e34e793c94d7f7c0dfcb77be293ccb3870f61385f747b17fb99003ac1`
  (PRODUCTS=47225, PAV_TOOL_TYPE=38822) —
  `artifacts-step3/fingerprint-before.json`.

## 1. Критерий отбора (стратифицированный, дословно)

> **Round-robin стратификация по корневым разделам.** Вселенная — товары без
> заполненного `tool_type` (предикат `catalog_queue_create._products_without_tool_type()`:
> отсутствие `ProductAttributeValue` по атрибуту `slug='tool_type'` с непустым
> `value_option`; 8403 товара на момент отбора). Страта — корневой раздел
> категории товара (категория `depth=1` дерева MP_Node, определяется по первым
> `steplen` символам `path` через маппинг `path→pk`; товар без категории —
> страта 0, идёт последней). Порядок страт: по убыванию числа untyped-товаров
> в страте, при равенстве — по возрастанию id корневой категории. Внутри страты
> товары упорядочены по возрастанию `id`. Выборка: циклический обход страт в
> установленном порядке, из каждой непустой страты за проход берётся один
> следующий товар, пока не набрано 20. Воспроизведение:
> `manage.py shell -c "exec(open('scratchpad/phase8/select_step3.py', encoding='utf-8').read())"`
> → `artifacts-step3/selection.json`; затем
> `catalog_queue_create --explicit-ids <ids>`. Cherry-pick не выполнялся:
> все 20 отобранных позиций взяты как есть, включая служебные/мусорные.

Итог: **20 товаров из 20 разных корневых разделов** (первый круг round-robin
покрыл все 20 непустых страт, кроме страт с 2 и 1 товаром и страты 0).
Страты и untyped-объёмы: «Не на сайте» 2197, «Хозтовары, сад, огород» 1448,
«Запчасти» 893, «Электроинструмент» 508, «Электрика и освещение» 416+377
(два корня-дубля по имени), «Ручной инструмент» 382, «Строительный и
отделочный» 350, «Силовая техника» 280, «Спецодежда и СИЗ» 273, «Оснастка»
195, «Автоинструмент» 195, «Садовая техника» 184, «Сварочное оборудование»
179+57, «Измерительный инструмент» 144+91, «Хранение» 103, «Запчасти,
аккумуляторы» 62, «Крепёж и метизы» 42+24. Полные данные —
`artifacts-step3/selection.json`.

## 2. Цикл: create → export

```bash
uv run python manage.py catalog_queue_create \
  --explicit-ids "28270,39029,6503,422,23606,22,123,5312,179,1860,377,4,1453,11232,2126,4944,10559,164,6798,4945" \
  --mode tool_type --kind research --idempotency-key "phase8-step3-strat20"
# → Создан run 00638eaa-0d7e-4532-b13f-ab40b3b8be0d с 20 items

uv run python manage.py catalog_queue_export \
  --run 00638eaa-0d7e-4532-b13f-ab40b3b8be0d --pretty
# → items: 20, checksum: 5290841dd519ceb5bae99c882c96bfe4309bf438e003023b71d663fac55db0bc
# → var/catalog-processing/outbox/00638eaa-….json
```

Параметры export: `target_kind=tool_type`, `taxonomy_hash=a583a9ae…b2f1`
(legacy-хэш живого словаря, §0), `allowed_options=329`. Снимок items:
`artifacts-step3/export-items.txt`.

## 3. Research (скилл catalog-research, шаги 3–5) + ручная сверка evidence

Web research — реальные поисковые запросы (WebSearch); identity gate и
приоритет источников — по `references/source-policy.md`. **Ручная сверка
выполнена по каждому из 20 товаров** (обязательство ступени): все URL из
evidence открыты (FetchURL) и проверены на три вопроса: страница реальна,
относится к этому товару, подтверждает предложенный тип. Для 8 items без
changes evidence по контракту не прилагается — сверка заключалась в
документировании identity-вывода и причины отказа (§3.2).

### 3.1 Сверка items с changes (12): товар → тип → evidence → подтверждено

| id | Товар | Предложенный тип | Evidence (источник) | Подтверждено |
|---|---|---|---|---|
| 4 | Ареометр АНТ-1 (710-770) ГОСТ 18481-81 | `izm-areometry` (90, researched) | [5drops.ru](https://5drops.ru/product/areometr_dlya_nefti_i_nefteproduktov_ant_1_710_770_kg_m3/) (specialized) — «Вид: АНТ-1; 710-770 кг/м3; ГОСТ 18481-81» | **да** — страница товара, тип/диапазон/ГОСТ совпали |
| 22 | Гайковерт ручной РГ56М | `spetsialnye-klyuchi` (55, review) | [mitra-s.ru](https://mitra-s.ru/products/ruchnoj-gajkovert-rg56m-s-golovkami-rg0561) (specialized) — «РГ56 Ручной гайковёрт… 3800 Nm» | **да** (identity); тип — ближайший зонтик, решение оставлено модератору |
| 123 | Домкрат кабельный ДК-5, две стойки, два винта | `domkraty` (90, researched) | [kvt-pro.ru](https://kvt-pro.ru/domkraty-kvt/domkraty-kabelnye/domkrat-kabelnyj-vintovoj-dk-5v) (**manufacturer**) — «ДК-5В… пара стоек; 2 винта» | **да** — карточка производителя КВТ, комплектация совпала дословно |
| 164 | Зарядное устройство PW 325 12В 18А | `zaryadnye` (90, researched) | [orionspb.ru](https://orionspb.ru/charger/7248/) (**manufacturer**) — «Модель: Орион PW-325; 12В; ток до 20А» | **да** — карточка НПП «Орион» (прибор снят с производства, страница жива) |
| 179 | Компрессор Бежецк АСО К-11 | `bp-kompressory` (90, researched) | [asobezh.ru](https://asobezh.ru/catalog/porshnevye_kompressory/s_privodom_2_2_4_0_kvt/gruppa_2/1030/) (**manufacturer**) — «Поршневой компрессор К11/10… Бежецкого завода АСО» | **да** — официальный сайт завода |
| 377 | Шарошки победит 6зубцов ВАЗ (арт. 72570) | `sharoshki` (95, researched) | [service-kluch.com](https://service-kluch.com/sharoshki-pobeditovye-vaz-2101-21011-2103-2106-21213-21083-2110-2111-zmz-406-6-zubov/) (**manufacturer**) — «Артикул: 72570; Тип: шарошки, зенкер» | **да** — точный артикул на сайте производителя |
| 422 | Воздуходувка DENZEL RB180-36 (арт. 59610) | `bp-vozdukhoduvki` (90, researched) | [denzel-shop.ru](https://denzel-shop.ru/product/vozduhoduvka-akkumuljatornaja-rb180-36-li-ion-36-v-4-ach-180-kmch-820-m3ch-denzel-59610/) (**distributor**) — «RB180-36… DENZEL 59610, арт. DZ-59610» | **да** — официальный дилер DENZEL; vseinstrumenti отдал 403 (bot-защита) → источник заменён на дилера до записи в result |
| 4944 | Бокс для инструмента ALVE (арт. ALV-3003) | `yashchiki-sumki` (85, researched) | [kutil.cz](https://www.kutil.cz/zahrada-stavba-dilna/zebriky-schudky-plosiny/doplnky-k-zebrikum/multi-box-alve-3003/) (specialized) — «Multi box Alve 3003… typ 3003, nosnost 3 kg» | **да** |
| 4945 | Винт ГОСТ Р ИСО 4017-М8х30-5,6-А2F | `krep-bolty` (90, researched) | [rcsm-ural.ru](https://rcsm-ural.ru/store/bolty/gost-r-iso-4017-2013/vint-s-shestigrannoy-golovkoy-gost-r-iso-4017-m8h30-5.6/) (specialized) — «Винт… ГОСТ Р ИСО 4017-М8х30-5.6» | **да** — ГОСТ+размер+класс совпали |
| 6798 | Катод плазмотрона А141 | `svar-sopla` (55, review) | [teslaweld.com](https://teslaweld.com/elektrod-dlya-plazmotrona-a141-d20-14mm) (specialized) — «Электрод для плазмотрона А141 (катод)… расходный материал» | **да** (identity); тип **не подтверждён** — катод ≠ сопло, модератору |
| 11232 | Паяльник REXANT 12-0621 65Вт | `payalniki` (90, researched) | [rexant-shop.ru](https://rexant-shop.ru/product/rexant-12-0621/126490) (specialized) — «12-0621… 65 Вт… 5 жал» | **да** — одиночный паяльник, не станция |
| 23606 | Автомат SP pius п/э пакет 3кг | `hoz-himiya` (65, review) | [u2b.ru](https://u2b.ru/catalog/bytovaya_khimiya/sredstva_dlya_stirki/poroshok_stiralnyy_avtomat_sp_plus_ekonom_universal_3kg/) (specialized) — «Порошок стиральный автомат "SP plus Эконом" универсал 3кг» | **да** — identity косвенная (опечатка pius/plus), тип верен по сути |

Выдуманных URL нет; все 12 источников — из реальных выдач и открывались.
`retrieved_at` в result — `2026-07-28T09:05:00Z` (дата сбора).

### 3.2 Items без changes (8): identity и причина отказа

| id | Товар | identity | status | Причина (проверена поиском) |
|---|---|---|---|---|
| 1453 | Бак со станиной для швонарезчика Patriot RCS-450 | partial | unknown | Швонарезчик RCS-450 подтверждён множеством источников; сама запчасть (бак для **воды**) отдельной карточкой не находится. `zap-baki` = «Топливные баки» — по value не подходит |
| 1860 | Сумка для противогаза | partial | unknown | Generic-наименование без модели (класс существует — сумки ГП-5/ГП-7); matched недостижим. Типа нет: `sumki-poyasnye` — сумки для инструмента, не СИЗ-аксессуар |
| 2126 | Электрогенератор CHAMPION DS1000E (10/11кВт…) | partial | unknown | Модели «DS1000E» у Champion **не существует**; характеристики из наименования совпадают с DG10000E — опечатка 1С. Changes без matched запрещены |
| 5312 | Адгилин М НПЭ | matched | unknown | Товар — отражающая теплоизоляция (izolon.ru + независимые), НЕ герметик (категория каталога ошибочна); типа «теплоизоляция» в словаре нет |
| 6503 | Боек 374432 | matched | unknown | Точный артикул — «второй боек» Hitachi/HiKOKI (zip4tools и др.); типа «бойки/ударники перфораторов» в словаре нет; категория «Запчасти / ЗУБР» с брендом не совпадает |
| 10559 | Беспроводной сканер штрих-кода | partial | unknown | Generic без модели; сканер — торговое оборудование, типа в словаре нет |
| 28270 | Долг за инструмент | unknown | **identity_failed** | Не товар — служебная запись долга («Не на сайте / Офис»); корректный отказ контура |
| 39029 | Агар Чапека-Докса, гранулир. (арт. CM075-500G) | partial | unknown | По совокупности — HiMedia GM075-500G (артикул в БД расходится C≠G); питательная среда — вне домена словаря |

Result-файл: `var/catalog-processing/inbox/00638eaa-….result.json`
(собран `scratchpad/phase8/make_result_step3.py`; `input_hash`/`taxonomy_hash`/
`export_checksum` подставлены из export-файла). Локальная валидация по JSON
Schema `catalog_research_result_v1.json`: **0 ошибок** (20 items, 12 changes;
пойман и исправлен один `identity.reason` > 255 — лимит схемы).

## 4. Import — G1 закрыт процедурно (`--run` в каждом вызове)

Все вызовы импорта ступени, команды целиком (других не было):

```bash
# импорт №1 — контрольный dry-run (dry-run — режим по умолчанию, флага --dry-run нет)
uv run python manage.py catalog_queue_import \
  --file var/catalog-processing/inbox/00638eaa-0d7e-4532-b13f-ab40b3b8be0d.result.json \
  --run 00638eaa-0d7e-4532-b13f-ab40b3b8be0d
# EXIT=0: {"total": 20, "created": 0, "would_create": 12, "existing": 0,
#  "skipped": 8, "errors": 0, "dry_run": true,
#  "result_checksum": "efdea23717cd841c6ebc014bf21f56e5b7173a59e9cabe798003fea163e3aa56",
#  "export_checksum": "5290841dd519ceb5bae99c882c96bfe4309bf438e003023b71d663fac55db0bc"}

# импорт №2 — commit: findings в модерацию (CatalogChange proposed), НЕ в каталог
uv run python manage.py catalog_queue_import \
  --file var/catalog-processing/inbox/00638eaa-0d7e-4532-b13f-ab40b3b8be0d.result.json \
  --run 00638eaa-0d7e-4532-b13f-ab40b3b8be0d --commit
# EXIT=0: {"total": 20, "created": 12, "would_create": 0, "existing": 0,
#  "skipped": 8, "errors": 0, "dry_run": false, checksums — те же}
```

Итог: **12 `CatalogChange(proposed)`** (findings в очереди модерации),
8 items → `needs_review` (7 × `unknown` + 1 × `identity_failed`). Ошибок
валидации: 0. `PAV tool_type` не изменился (§7).

## 5. Модерация (ручная, по итогам сверки evidence)

Выполнена `review_catalog_change` (reviewer_id=1) со скриптом
`scratchpad/phase8/moderate_step3.py`, комментарии модератора записаны в
каждый change:

| Решение | refs | Обоснование |
|---|---|---|
| **approved × 11** | 4, 22, 123, 164, 179, 377, 422, 4944, 4945, 11232, 23606 | Evidence сверены вручную, тип верен (для 22 — лучший доступный зонтик при отсутствии типа «ручные гайковёрты»; для 23606 — верно по сути при косвенной identity) |
| **rejected × 1** | 6798 | Катод плазмотрона ≠ сопло: value `svar-sopla` («Сопла, мундштуки, наконечники») катоды не покрывает; нужен отдельный тип расходки плазмы |

Item 6798 после reject ушёл в `needs_review` с `error_code=rejected`
(штатый переход, `processing.py:_close_item_after_reject`).

`catalog_queue_status` после модерации: items 11 `processing` (approved,
«одобрено и готово к применению») + 9 `needs_review`; changes 11 approved /
1 rejected, `pending_review=0`.

## 6. Finalize — попытка и штатный отказ

```bash
uv run python manage.py catalog_queue_finalize --run 00638eaa-0d7e-4532-b13f-ab40b3b8be0d
# EXIT=1: CommandError: Финализация невозможна: items_not_final
```

**Это ожидаемое поведение state machine, а не сбой:** финальны только items
`completed`/`failed` (`processing.py:65,708,745-746`); items с approved
changes остаются `processing` до apply, а apply в этой ступени запрещён
границами («само применение к каталогу — не в этой ступени»). Следствие:
**finalize и «без apply» несовместимы** — run остаётся в `running` с 11
одобренными findings до решения владельца о применении. Отказ finalize
документирован как доказательство, что контур не даёт закрыть batch с
неприменёнными одобренными находками.

## 7. Каталог не изменён — доказательство

```
ДО    8783f63e34e793c94d7f7c0dfcb77be293ccb3870f61385f747b17fb99003ac1
ПОСЛЕ 8783f63e34e793c94d7f7c0dfcb77be293ccb3870f61385f747b17fb99003ac1
rows equal: True (47225 строк проекции), PAV_TOOL_TYPE: 38822 == 38822
```

Снимки: `artifacts-step3/fingerprint-before.json`, `fingerprint-after.json`.
Отпечаток покрывает `code_1c, article, name, category_id, price,
stock_quantity, status, is_active` + slug опции `tool_type` — записи
`CatalogChange` в проекцию не входят по построению и каталогом не являются.

## 8. Оценка качества (главный результат ступени)

### 8.1 Счётчики

- Предложений выдано: **12 из 20** (9 `researched` + 3 `review`).
- **Верные: 10 из 12** — 9 researched (4, 123, 164, 179, 377, 422, 4944,
  4945, 11232) + 23606 (порошок → `hoz-himiya`, верно по сути).
- **Условно верные: 1** — 22 (ручной гайковёрт → `spetsialnye-klyuchi`:
  ближайший зонтик при отсутствии точного типа).
- **Ошибочные: 1** — 6798 (катод → `svar-sopla`: семейство верное, тип
  неверный; **поймано модерацией**, rejected).
- В `needs_review`: **9 из 20** — 7 × `unknown` (осознанный отказ: нет типа
  в словаре или identity не matched), 1 × `identity_failed` (не товар),
  1 × `rejected` (6798 после модерации).

### 8.2 Какие ошибки контур сделал бы, если бы применял — разбор

1. **6798: неверный тип расходки плазмы (поймана).** Катод плазмотрона А141
   получил бы «Сопла, мундштуки, наконечники». Причина: в словаре нет типа
   «электроды/катоды плазмотронов», скилл выбрал ближайший из семейства.
   Защита сработала: `review` + conf 55 → модератор отклонил. Вывод: без
   модерации контур бы ошибся; с модерацией — нет. Модерации **хватает**,
   если модератор читает value опции, а не только название товара.
2. **2126: потерянный очевидный случай из-за наименования 1С.** «CHAMPION
   DS1000E» не существует (есть DG10000E с теми же характеристиками).
   Identity gate честно не дал `matched` → `unknown`, предложение не
   сформировано. Это не ошибка, а **отказ по строению**: цена строгости
   gate — товар ждёт ручной обработки. Модератору такие кейсы видны в
   `needs_review` с причиной.
3. **Категорийная слепота подтверждена массово.** 6 из 20 товаров лежат в
   чужих разделах: 23606 (порошок в «Электрике»), 5312 (теплоизоляция в
   «Герметиках»), 2126 (генератор в «Измерительном»), 6503 (Hitachi в
   «Запчасти / ЗУБР»), 10559 (сканер в «Измерительном»), 28270 (долг — не
   товар). Контур tool_type категорию не правит (и не должен в v1), но
   `category_path` в export позволяет модератору видеть расхождение.
4. **Дыры словаря на здоровой таксономии — поимённые, не catch-all.**
   В отличие от ступени 2 (9/10 в `izm-analizatory`), здесь ни одного
   предложения в catch-all: все 9 researched — точные типы. Оставшиеся дыры
   конкретны: «ручные гайковёрты/мультипликаторы» (22), «катоды/электроды
   плазмотронов» (6798), «бойки/ударники перфораторов» (6503), «теплоизоляция»
   (5312), «баки водяные — запчасти» (1453). Вне домена словаря (не дыры, а
   чужой товарный контур): сканер штрих-кода (10559), лабораторные среды
   (39029).
5. **Тип `izm-areometry` работает.** Товар id=4 (та же позиция, что на
   ступени 2 уходила в catch-all `izm-analizatory` с conf 60 review) получил
   точный тип с conf 90 `researched` — дыра TT-01 закрыта фактом применения.

### 8.3 Достаточность модерации

Из 12 предложений модерации потребовали 3 (`review`): 2 одобрены (22, 23606),
1 отклонена (6798). Единственная реальная ошибка контура поймана. Узкое
место — не модерация, а **качество наименований 1С** (2126, 39029) и
**generic-наименования без модели** (1860, 10559): их доля — 4 из 20 (20%),
на batch 50 даст ~10 items ручной работы.

## 9. Regression

Два прогона на отдельной БД `proff58_ph8reg3` (`--create-db` в первом),
`-p no:pylama`, вывод в файлы `artifacts-step3/pytest-step3*.log`:

```bash
# прогон №1 (464s): 3 failed, 2047 passed, 1 skipped
#   FAILED test_processing_service.py::test_finalize_feature_disabled  ← артефакт окружения окна
#   FAILED test_regression_mvp.py::test_healthcheck_returns_ok          (нет Redis — known)
#   FAILED test_deploy_release.py::test_release_script_is_executable    (Windows exec bit — known)
# прогон №2, чистый (500s): 2 failed, 2051 passed, 1 skipped
```

Разбор третьего падения прогона №1: `test_finalize_feature_disabled` упал из-за
**собственного** `export FEATURE_CATALOG_PROCESSING=True` в той же команде
(тест ждёт флаг выключенным). Доказано: одиночный запуск теста без флага —
`1 passed`; чистый прогон №2 без флага — третьего падения нет. Код контура
окном не менялся, так что это артефакт запуска, а не регрессия; зафиксировано
для runbook (regression запускать без `FEATURE_CATALOG_PROCESSING`).

| | собрано | failed | passed | skipped |
|---|---|---|---|---|
| Baseline (ст. 2, HEAD `8ff3f32`) | 1937 | 2 | 1934 | 1 |
| Факт (ст. 3, HEAD `e8c86ef`) | 2054 | 2 | 2051 | 1 |
| Δ | +117 | **0** | +117 | 0 |

Арифметика: `pytest --collect-only` на том же HEAD с теми же ignore —
**2054 tests collected** = 2 known failed + 2051 passed + 1 skipped. Сходится.
Δ +117 — разница деревьев (HEAD окна == свежий `origin/dev`; набор тестов
вырос чужой историей), не результатов. Третьего падения нет.

Особенность сбора на общей рабочей копии: чужие worktree-копии проекта
(`.claude/worktrees/*`, `.codex-ai-bot-platform-pr1092/`, `.review-origin-dev/`)
попадают в collection, т.к. `norecursedirs` в `pyproject.toml` переопределён
без `.*` — первый запуск умер на import-mismatch. Лечение без правки tracked
конфига и без удаления чужого: `--ignore` этих каталогов в команде.

## 10. Границы — подтверждение

- **Apply не выполнялся:** отпечаток до == после (§7); `CatalogChange` — только
  proposed→approved/rejected, ни одного `applied`; попыток
  `apply_catalog_change` не было.
- **Контур `tool_type` не тронут окном:** matcher, ruleset v2, applied corpus,
  манифест, артефакты гейта, queue-команды не изменялись. **Оговорка:** во
  время окна параллельная сессия изменила в общей рабочей копии
  `apps/catalog/{admin,facets,models,queries,test_facets}.py` (+84/−11,
  фича `CategoryAttribute.display_name` для фасетов) — чужая работа, не
  откатывалась, контура tool_type и очереди не касается (diff прочитан и
  атрибутирован). На старте и на финише окна моих tracked-изменений — 0.
- Новые типы в манифест не добавлялись; глобальные команды не запускались;
  staging не трогался; push/PR не выполнялись; `git add` не выполнялся.
- Regression — отдельная БД, `-p no:pylama`, вывод в файлы (§9).
- Ступень 4 не начиналась.
- Новые файлы только untracked: этот протокол, `select_step3.py`,
  `make_result_step3.py`, `moderate_step3.py`, `artifacts-step3/*`,
  export/result в `var/catalog-processing/` (по контракту вне git).

## 11. Вынесенное владельцу

1. **GO на apply (отдельным решением):** 11 findings одобрены и готовы к
   применению (run `00638eaa`, approved). По гейт-циклу: pg_dump → снимок
   отката (H5/H6) → apply → post-audit. Числа: 11 товаров получат tool_type
   (4, 22, 123, 164, 179, 377, 422, 4944, 4945, 11232, 23606); каталог меняется
   только в slug PAV tool_type этих 11 товаров.
2. **Finalize заблокирован до apply** (§6) — после apply 11 items уйдут в
   `completed`, 9 останутся `needs_review` → finalize даст
   `completed_with_review`. Альтернатива без apply — отмена run (команды
   отмены нет — G3).
3. **Дыры словаря по факту batch 20** (§8.2 п. 4): кандидаты на новые типы
   через контур manifest — «ручные гайковёрты», «катоды/электроды
   плазмотронов» (или расширить value `svar-sopla`), «бойки/ударники»;
   «теплоизоляция» — продуктовое решение (большой соседний контур).
4. **Калибровка ступени 4 (batch 50):** см. отчёт оркестратору §«Калибровка».

## 12. Артефакты

- Этот протокол: `scratchpad/phase8/phase8-step3-report.md`
- Отчёт оркестратору: `scratchpad/phase8/phase8-step3-orchestrator-report.md`
- Скрипты: `select_step3.py`, `make_result_step3.py`, `moderate_step3.py`
- Снимки: `artifacts-step3/selection.json`, `export-items.txt`,
  `allowed-options.txt`, `fingerprint-{before,after}.json`,
  `pytest-step3.log`, `pytest-step3-clean.log`
- Export: `var/catalog-processing/outbox/00638eaa-….json` (checksum `5290841d…`)
- Result: `var/catalog-processing/inbox/00638eaa-….result.json`
  (`result_checksum efdea237…`)
- Run `00638eaa-0d7e-4532-b13f-ab40b3b8be0d` оставлен в `running`: 11
  approved findings (готовы к apply), 9 items `needs_review`.
