# Дефект fail-open: unknown SELECT option молча пропускается

> **Статус:** audit closed  
> **Решение владельца (2026-09-12):** T2 + light T3: preflight `required_options ⊆ DB` до `ImportRun.create`; dry-run тоже FAIL; exit code 2 (или существующая non-zero convention); **NO bypass flag** для write; допустим read-only `--report-missing-options`; runtime unknown option на write path → raise/abort.  
> Обзор трека и все решения — [2026-09-12-foundation-axes-research.md](2026-09-12-foundation-axes-research.md). Exact proposal — `appendix/2026-09-12-foundation-axes/`. Сырые замеры и кейсы остались в scratchpad сессии как доказательный слой.

---

Дата: 2026-09-12. Режим: read-only аудит кода, репозиторий не менялся, стенд не трогался.
Рабочая копия: `C:\Users\user\PycharmProjects\proff58\.worktrees\pilnye` (HEAD `d22394d`).
Все ссылки `файл:строка` — по этой копии.

Эмпирическое подтверждение: пробный тест **вне репозитория**
(`scratchpad/research/T_select_order/test_select_order_probe.py`, вывод в `probe_output.txt`)
прогнан на локальной тестовой БД из брифа — 3 passed. Он воспроизводит дефект один в один:
write-mode завершается `status=done`, значение SELECT не записано, ни одного счётчика.

---

## 0. Резюме дефекта (одним абзацем)

Движок (`attribute_extract.py`) отдаёт SELECT-значение как `option_slug` из правила; команда
резолвит его в `AttributeOption` через in-memory индекс `option_index`, загруженный из БД один
раз (`enrich_attributes.py:229-233`). Если опции нет — ветка `enrich_attributes.py:541-558`:
строка отчёта `skip` (которая в боевом режиме — **no-op**, `enrich_attributes.py:374-375`) и
`continue` **до** инкремента `stats["by_attribute"]` (`enrich_attributes.py:656`). Ни один
счётчик `stats`, ни одна строка stderr/stdout, ни статус `ImportRun` не меняются. Команда
возвращает `str(run.pk)` → exit 0. Порядок «`load_attributes` → `enrich_attributes`»
документирован в двух местах (`.claude/skills/characterize-subgroup/SKILL.md:120-123`,
`docs/catalog/discover-missing-rules.md:524-526`), но кодом не защищён.

Вчерашние 4 опции подтверждены дифом правил `33f1b80^ → HEAD` (скрипт `new_opts.py`):
`material`: `alyuminiy`, `omednennaya-stal`, `poroshkovaya`; `tool_kind`: `tsanga`. Плюс
новая SELECT-ось `chain_pitch` (4 опции) — атрибут существовал в БД от трека скрапера
(`data/catalog_processing_rules/scraped_attr_map.benzopily-trimmery.json`), иначе команда
вышла бы раньше по ветке §1.4.

---

## 1. Почему `enrich_attributes` завершился штатно, пропустив 42 SELECT-значения

### 1.1 Точное место

`apps/catalog/management/commands/enrich_attributes.py:539-558`:

```python
attribute = attr_by_slug[av.slug]
option = None
if av.kind == SELECT:
    option = option_index.get(av.slug, {}).get(av.option_slug)
    if option is None:
        # вариант не загружен — пропускаем
        pav0 = existing.get((product.id, av.slug))
        add_report_row(product, tt_slug, "skip", av.slug, …, av.option_value, av.matched,
                       av.source, f"вариант {av.option_slug!r} не загружен — выполните load_attributes")
        continue
```

- `option_index` строится **один раз** до цикла: `enrich_attributes.py:229-233` —
  `AttributeOption.objects.filter(attribute__slug__in=managed_slugs)`, ключ — `opt.slug`.
- Движок гарантированно отдаёт `option_slug` только из `rule.options`
  (`apps/catalog/attribute_extract.py:290-311`, для derive — `attribute_extract.py:234-243`),
  поэтому «опции нет в индексе» = «опция из правил не загружена в БД» — единственная причина.
- `continue` на строке 558 обходит **всё**: создание PAV (564-586), обновление (587-654) и
  счётчик `stats["by_attribute"]` (656).

### 1.2 Это отдельная ветка, а не общий путь «нет option → пропустить»

Это **отдельная ветка** с собственной причиной в тексте, но она **разделяет `action: "skip"`**
с двумя другими, семантически чужими исходами:
- карантин по атрибуту — `enrich_attributes.py:524-538` (`skip`, «атрибут в карантине»);
- приоритет источника — `enrich_attributes.py:590-605` (`skip`, «перезапись запрещена»).

Различие только в свободном тексте `reason`; **кода причины нет**. У приоритетного skip есть
свой счётчик `stats["skipped_priority"]` (591), у карантина — `quarantined_partial` (449);
у незагруженной опции — **ничего**.

### 1.3 Что при этом логируется/считается

| Канал | Write-mode | Dry-run |
|---|---|---|
| `stats` / `ImportRun.stats` | ничего (проверено: `by_attribute` = только number-оси) | `ImportRun` не создаётся |
| stderr | ничего | ничего (сводка `summary`, 704-718, счётчика skip не имеет) |
| stdout-сводка | `По атрибутам — …` без пропущенной оси | та же строка → stderr |
| JSON-отчёт | нет | `rows[].action="skip"` + текст reason; `totals.by_action.skip` **смешан** с приоритетом и карантином |
| exit code | 0 (`return str(run.pk)`, 745) | 0 |
| `ImportRun.status` | `done` (689) | — |

Итог: в боевом режиме дефект **ненаблюдаем в принципе**; в dry-run — наблюдаем только чтением
`rows` JSON по тексту reason.

### 1.4 Смежный soft-exit того же класса

`enrich_attributes.py:220-226` — отсутствие **атрибута** (не опции) обрабатывается
`self.stderr.write(...); return ""` → тоже **exit 0**, без `ImportRun`, без `CommandError`.
Оркестратор, проверяющий код возврата, не отличит это от успешного прогона. Соседняя команда
`catalog_import_scraped.py:99-101` в той же ситуации бросает `CommandError` (fail-closed).

---

## 2. Есть ли observable counter/status для unknown option

**Нет.** Обследованы:
- `stats` (`enrich_attributes.py:330-346`): ключи `processed`, `no_attributes`, `by_attribute`,
  `skipped_priority`, `pruned`, `quarantined*`, `quarantine` — незагруженной опции нет;
- сводка (`704-718`) — печатает только эти ключи;
- JSON dry-run (`766-798`): агрегаты `by_action`/`by_tool_type`/`by_attribute` считают по
  `action`, а `action="skip"` — общий для трёх причин; поля `reason_code` нет.

**Почему не было видно вчера.** В боевом режиме `add_report_row` — no-op (374-375), а другой
канал не предусмотрен. Если dry-run делался, оператор видел сводку без skip-счётчика и JSON, где
42 строки `skip` были неотличимы от приоритетных skip без чтения `reason`.

**Где естественно добавить (минимум, без изменения решений):**
1. `stats["skipped_missing_option"]: {attr_slug: n}` — инкремент в ветке 543-558 перед
   `continue`; попадает в `ImportRun.stats` автоматически (700-702).
2. Строка сводки (711-718): `…, пропущено без опции {N} ({attr: n, …})`.
3. `reason_code` в строке отчёта (`add_report_row`, 363-388): `missing_option` /
   `quarantine` / `priority` / … — и агрегат `totals.by_reason_code` в `_emit_dry_run_report`.
4. Список пропущенных пар `(attr, option_slug, value)` в `stats` и в JSON `preflight` (см. §4).

---

## 3. Можно ли сделать выполнение fail-closed

Да, и дёшево. Три возможные точки в pipeline:

| Точка | Где | Когда ловит | Стоимость |
|---|---|---|---|
| **A. Статический preflight** (T2) | после `option_index` (233) и `selected_tt` (256), до `existing` (323) и `ImportRun.objects.create` (329) | до чтения товаров; ничего не создано | 0 SQL (индекс уже загружен), O(302 пар) в памяти |
| **B. Runtime-assert** (T3) | ветка 543-558: вместо `continue` — `raise` | при первом реальном срабатывании | внутри `transaction.atomic()` (429) → полный rollback; `ImportRun` уходит в `FAILED` с `stats.error` (690-697) |
| **C. Post-check** | после цикла, до flush (677-686) | после обработки всех товаров | впустую обработан весь пул |

Рекомендация: **A как основной гейт + B как assertion**, C не нужен.

### 3.1 Чем это отличается от карантина (`attribute_quarantine`)

| | Карантин | Preflight опций (предлагаемый) |
|---|---|---|
| Что валидирует | **файл реестра** (структура, `product_id`, слуги ⊆ managed) | **дрейф правил ↔ схема БД** (`AttributeOption`) |
| Положение | `enrich_attributes.py:194-218`, до `Attribute`-проверки | сразу после `option_index` (233) |
| Отказ | `CommandError` (198-199, 210-213), exit 1, `ImportRun` не создаётся | то же |
| Обход | нет флага — чинится файл | предлагается `--allow-missing-options` (см. §7) |
| Что защищает | «не писать там, где владелец запретил» | «не терять то, что правила обещают записать» |

Общее: обе проверки стоят **до** любого чтения товаров и до `ImportRun`, обе — «весь прогон
или ничего». Разное: карантин — про правомерность записи; preflight — про полноту схемы.

### 3.2 Чем это отличается от `--strict-bindings` у `load_attributes`

`load_attributes.py:625-679`: `--strict-bindings` делает фатальным `not_found` **категории**
для `CategoryAttribute` — другая сущность (привязка, не опция), другая команда, и это
**opt-in ужесточение** (по умолчанию WARNING, `load_attributes.py:40-43`). Предлагаемый
preflight — **default-fatal** в стиле карантина и `--allow-ambiguous`: обход — явное разрешение
на самостоятельное действие, а не ужесточение проверки (конвенция зафиксирована в
`load_attributes.py:69-71`).

Важно: `load_attributes` планирует опции **по всем** SELECT-осям **независимо от `bind`**
(`load_attributes.py:296-297`; `bind:false` влияет только на привязку, 312-314), ключ
существующих — `(attribute.slug, value)` (274-278), а `slug` расходящейся опции обновляется
(`_finalize_option`, 479-496, поле `slug` в `OPTION_FIELDS`). Значит, после штатного
`load_attributes` на актуальных правилах инвариант «required ⊆ DB» выполняется всегда, и
preflight в `enrich_attributes` ложных срабатываний по этой причине не даёт.

---

## 4. Preflight «required options ⊆ DB options»

### 4.1 Как вычислить required по execution manifest

Execution manifest команды = `selected_tt` (`enrich_attributes.py:245-256`: все `tool_types`
из правил, суженные `--tool-type`). Required:

```python
def required_select_options(raw: dict, tool_types: Iterable[str]) -> dict[str, dict[str, dict]]:
    """{attr_slug: {option_slug: {"value": str, "tool_types": [..]}}} по SELECT-осям выбранных блоков."""
    wanted = set(tool_types); out = {}
    for tt in raw.get("tool_types", []):
        if tt["tool_type"] not in wanted: continue
        for a in tt["attributes"]:
            if a.get("kind") != "select": continue
            for o in a.get("options", []):
                entry = out.setdefault(a["slug"], {}).setdefault(o["slug"], {"value": o["value"], "tool_types": []})
                entry["tool_types"].append(tt["tool_type"])
    return out
```

Чистая функция без Django — место ей рядом с `AttributeRules` в `attribute_extract.py`
(модуль уже «без обращения к БД», `attribute_extract.py:3-5`) или в новом
`apps/catalog/attribute_preflight.py`; тестируется без БД.

Derive-правила покрыты автоматически: `set_option` обязан быть в `rule.options`
(`attribute_extract.py:234`), иначе движок молча вернёт `None` — это **ещё один тихий путь**,
который стоит включить в тот же preflight как lint правил (`derive.set_option ∉ options` → отказ).

Масштаб по текущему словарю (скрипт `stats_rules.py`): 149 блоков, 350 правил, из них 101
SELECT по 44 атрибутам, **302 required пар** `(attr, option_slug)`; пустых слугов нет; коллизий
«один slug — разные value» / «одно value — разные slug» нет; `tool_kind` — 17 опций,
`material` — 25 (обе оси разделяются многими блоками, поэтому required считается **на атрибут,
объединением по блокам**, а не «на блок»).

### 4.2 Сверка с БД и стоимость

`option_index` (229-233) уже содержит все `AttributeOption` для `managed_slugs` — это
**единственный запрос**, дополнительных не нужно. Для полезной диагностики из того же
queryset строится второй индекс `{attr: {value: option}}` (0 SQL), чтобы различать:
- `absent` — опции нет вовсе → нужен `load_attributes` (create);
- `slug_mismatch` — есть опция с тем же `value`, но `slug` пустой/другой (легаси,
  `backfill_option_slugs`) → тоже `load_attributes` (update slug).

Стоимость: O(302) словарных операций; на стенде — микросекунды.

### 4.3 Точка в `enrich_attributes`

Между строками 256 (`selected_tt` готов) и 258 (`resolve_category_ids`): после карантина
(194-218) и проверки атрибутов (220-226), после `option_index` (229-233), **до** выборки
товаров (278-291), `existing` (323-327) и `ImportRun.objects.create` (329). Отказ здесь —
«ничего не произошло»: нет `ImportRun`, нет транзакции, как у карантина.

### 4.4 Поведение в dry-run

Один путь для dry-run и apply — требование владельца, зафиксированное в докстринге
(`enrich_attributes.py:16-21`: «решения принимает тот же код, расходится только финальный
шаг»). Preflight обязан вести себя **одинаково**: dry-run без опций **тоже отказ** — иначе
план покажет 42 `skip` вместо 42 `create` и введёт оператора в заблуждение (ровно вчерашний
сценарий: повторный dry-run после `load_attributes` показал `create 42`). С флагом обхода
dry-run продолжает, а JSON получает блок `preflight` (§7) и `reason_code="missing_option"` в
строках.

---

## 5. Как не сломать legitimate dropped/unknown values

Проверены все кандидаты на «отсутствие опции — норма»:

| Случай | Влияет на preflight? | Почему / как отличить |
|---|---|---|
| `derive` (14 правил, все `set_option` ∈ options) | нет | движок берёт опцию из `rule.options` (`attribute_extract.py:234`); required уже включает её. Если `set_option` вне options — это дефект правила, preflight обязан его **поднять** (сейчас тихий `None`) |
| Опция `unknown` («Не определён», `metchiki-plashki`/`tool_kind`, `attribute_rules.json:2312`) и `universal*` | нет | это **обычные объявленные опции**, `load_attributes` их создаёт; исключать нельзя |
| Карантин (whole / partial) | нет | ось товара, не схемы: карантин ставится **до** извлечения (441-450) и не меняет множество опций правил. Preflight статический — карантин ему не виден и не нужен |
| `bind: false` (38 осей) | нет | влияет только на `CategoryAttribute` (`load_attributes.py:312-314`); опции всё равно планируются (296-297). Исключать из required **нельзя** — иначе preflight пропустит ровно тот класс, который и потерялся |
| Значения скрапера с другими словарями | нет | другой путь записи (`catalog_import_scraped` → `scraped_import.apply_plan_items`, `scraped_import.py:1042-1046`) с собственным `option_index`. Опции, существующие только в БД (создал скрапер-трек/руками) — **надмножество**, а preflight проверяет `required ⊆ DB`, надмножество допустимо. PAV `source=scraper` prune не трогает (`PRUNABLE_SOURCES`, 72; 485-500) |
| Опции с пустым `slug` в БД (легаси до `backfill_option_slugs`) | да — как `slug_mismatch` | сейчас это **тоже тихая потеря** (индекс по slug); preflight должен показать её отдельным hint, лечится `load_attributes` (обновляет slug) |
| `kind: number/boolean/text` | нет | опций нет по определению; `TEXT` не создаёт options (`test_enrich_attributes_text.py:6-7`) |
| `--tool-type` вне блоков правил | нет | уже WARNING (247-256); required считается по `selected_tt`, лишних требований нет |
| Расхождение `attribute_type` (в правилах `select`, в БД `text`) | вне scope | `load_attributes` показывает `conflicts` (399-407) без отказа; отдельная тема, здесь только отметить |

Вывод: **легитимного случая «опция из правил отсутствует в БД» не существует** — движок никогда
не порождает `option_slug` вне правил, а `load_attributes` создаёт все опции правил. Поэтому
preflight «required ⊆ DB» не имеет ложных срабатываний по конструкции; единственный источник
«ложного» отказа — умышленно не применённый `load_attributes`, что и есть нарушение инварианта.

---

## 6. Минимальный regression-тест

Образец — `apps/catalog/test_enrich_attributes_text.py` (инлайн-словарь через `--path`,
`tmp_path`). Прототип уже прогнан: `test_select_order_probe.py` (3 passed, локальная тестовая БД).

**Фикстура.** `RULES_DOC`: один блок `tsangi-i-tsangovye-patrony` с осью `tool_kind`
(`select`, `keyword`, опции `patron`/«Патрон» и `tsanga`/«Цанга») и осью `diameter`
(`number`, regex `(\d+)\s*мм`). В БД **руками** (без `load_attributes`): `Attribute`
`tool_type`+опция типа, `Attribute tool_kind` с **одной** опцией `patron`, `Attribute diameter`.
Товар «Цанга 8 мм для фрезера» с PAV `tool_type`. То есть схема «до применения новых правил».

**Вызов.** `call_command("enrich_attributes", "--path", rules_path[, "--dry-run"])`.

**Ожидаемое поведение — T2 (preflight):**
- и dry-run, и write: `pytest.raises(CommandError, match=r"tool_kind.*tsanga")`;
- `ImportRun.objects.count() == 0`; PAV `diameter` **не** создан (весь прогон отвергнут);
  `attrs_cache` не изменился;
- с `--allow-missing-options` (write): статус `done`, PAV `diameter` есть, PAV `tool_kind` нет,
  `run.stats["skipped_missing_option"] == {"tool_kind": 1}`, строка сводки содержит
  «пропущено без опции 1»; (dry-run): `rows` содержит строку `tool_kind` с
  `action="skip"`, `reason_code="missing_option"`, JSON `preflight.missing_options` =
  `[{"attribute":"tool_kind","option":"tsanga","value":"Цанга","status":"absent","tool_types":[…]}]`;
- после `call_command("load_attributes", "--path", rules_path)` — dry-run без флага проходит,
  строка `tool_kind` → `create` (равенство dry-run/apply, как в
  `test_dry_run_decisions_match_apply`).

**Ожидаемое поведение — T3 (runtime):**
- write: `CommandError` (или доменное исключение) из цикла; транзакция откатилась —
  PAV `diameter` **нет**, `attrs_cache` пуст; `ImportRun` один, `status == "failed"`,
  `stats["error"]` содержит `tool_kind`/`tsanga` (ветка 690-697);
- dry-run: тот же отказ (единый путь), `ImportRun` нет.

**Негативный контроль:** та же фикстура, но опция `tsanga` создана → оба режима проходят,
`create` для `tool_kind`. Плюс unit-тест чистой функции `required_select_options` без БД
(derive `set_option` вне options → ошибка).

---

## 7. Рекомендация: T1 / T2 / T3

| Вариант | Что ловит | Цена | Слабость |
|---|---|---|---|
| **T1 — только документ** | ничего (полагается на человека) | 0 | порядок уже написан в 2 местах (`SKILL.md:120-123`, `discover-missing-rules.md:524-526`) и всё равно нарушен — доказано вчера |
| **T2 — preflight gate** | весь класс «правила обещают опцию, в БД её нет» **до** любой записи, с точным списком и подсказкой | ~40 строк + тесты; 0 SQL | статический: не видит гонку «опцию удалили между preflight и записью» (на практике не встречается) |
| **T3 — hard runtime failure** | то же + гонки/обход | ~10 строк | падает **поздно** (после обработки пула), в `FAILED ImportRun`; сам по себе — плохая эргономика; без счётчика всё ещё ненаблюдаем |

**Рекомендация: T2 как основной гейт + T3 в облегчённой форме (счётчик всегда + assert)
+ T1 как сопровождение (обновить README gate-cycle и докстринг команды).**

### Дизайн T2

1. **Чистая функция** `required_select_options(raw, tool_types)` (см. §4.1) +
   `check_select_options(required, option_index, option_by_value) -> list[MissingOption]`
   (`attribute`, `option`, `value`, `tool_types`, `status ∈ {absent, slug_mismatch}`) —
   без Django-запросов; в неё же lint `derive.set_option ∈ options`.
2. **Точка вызова** — `enrich_attributes.handle` между строками 256 и 258 (после
   `option_index` и `selected_tt`, до выборки товаров и `ImportRun`).
3. **Отказ** — `CommandError` (exit 1, как у карантина в той же команде, 198-213; отдельный
   код не нужен — текст различает). Текст:
   ```
   Preflight опций не пройден: 4 варианта SELECT из attribute_rules.json отсутствуют в БД
   (типов в выборке 44, проверено 302 пары атрибут·вариант):
     material  · alyuminiy       («Алюминий»)              — absent; блоки: elektrody-…, …
     material  · omednennaya-stal («Омеднённая сталь»)     — absent; блоки: …
     material  · poroshkovaya    («Порошковая (флюсовая)») — absent; блоки: …
     tool_kind · tsanga          («Цанга»)                 — absent; блоки: tsangi-i-tsangovye-patrony
   Эти значения были бы молча пропущены. Выполните `load_attributes --dry-run` → `load_attributes`
   и повторите. Обход: --allow-missing-options (пропуски считаются в stats.skipped_missing_option).
   ```
4. **Флаг обхода** `--allow-missing-options` (семейство `--allow-*` = разрешение действия,
   `load_attributes.py:69-71`). С ним: preflight печатает WARNING с тем же списком, прогон
   идёт, каждая потеря считается (`stats["skipped_missing_option"][attr] += 1`), строка
   отчёта получает `reason_code="missing_option"`, сводка — «пропущено без опции N (…)».
5. **Dry-run** — идентично (единый путь, 16-21): без флага — отказ; с флагом — JSON-блок
   `"preflight": {"options": {"required": 302, "checked_tool_types": 44, "missing": [...],
   "allowed": true}}` и `totals.by_reason_code`. При успехе в обоих режимах — одна строка в
   stderr: `Preflight опций: OK — 302 варианта по 44 типам найдены в БД` (след в журнале окна).
6. Попутно: `enrich_attributes.py:220-226` → `CommandError` вместо `return ""` (тот же класс
   soft-exit), сохранив текст.

### T3 как дополнительный слой

В ветке 541-558 вместо голого `continue`: инкремент счётчика + `reason_code`; если флага
`--allow-missing-options` нет — `raise CommandError(...)` (внутри `transaction.atomic()` →
rollback всего, `ImportRun → FAILED` с `stats.error`, 690-697). После T2 эта ветка без флага
недостижима — это assertion «preflight и runtime согласованы»; с флагом — просто учёт.

### Что не входит, но помечено

- `scraped_import.py:1042-1046` — тот же тихий `continue` в пути скрапера; отдельная задача.
- `_derive_one` (`attribute_extract.py:234`) — тихий `None` при `set_option ∉ options`;
  закрывается той же preflight-проверкой правил.

### Точки, требующие подтверждения — РЕШЕНИЕ ВЛАДЕЛЬЦА

1. Dry-run без опций: **отказ** (рекомендуется, единый путь) или «предупреждение + план с
   `reason_code`»? Отчёт исходит из отказа.
2. Exit code отказа: **1** (как карантин) или отдельный (стиль gate `EXIT_INVALID=2`,
   `rules_gate.py:58-61`)? Отчёт исходит из 1.
3. Нужен ли `--allow-missing-options` вообще, или обход запрещён (как у карантина)? Отчёт
   предлагает флаг ради сценария «оценить yield новых правил до записи схемы»; альтернатива —
   считать, что для этого есть `attribute_coverage`/`discover_missing_rules`, и флага не давать.

---

## Приложение: артефакты в этой папке

- `test_select_order_probe.py` — прототип regression-теста (вне репозитория), `probe_output.txt` — вывод (3 passed).
- `stats_rules.py` — подсчёт required-пар и особых случаев по `data/attribute_rules.json`.
- `new_opts.py` — диф SELECT-опций `33f1b80^ → HEAD` (подтверждение 4 опций).