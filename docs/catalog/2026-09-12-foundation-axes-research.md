# ХАР — Foundation Axes: research gate (закрыт 2026-09-12)

> **Статус:** research gate **PASS / CLOSED** решением владельца 2026-09-12.
> Ничего из proposals **не применено**. Следующий шаг — implementation track
> **FOUNDATION-AXES-01**, открывается отдельным OWNER GO.

## Зачем трек

Волна правил 2026-09-11 (52 блока, ~3300 значений; см.
[HANDOFF-2026-09-06-catalog-main.md](../HANDOFF-2026-09-06-catalog-main.md) и память
проекта) упёрлась в три инфраструктурные характеристики, которые повторяются во
многих категориях и которые выгоднее один раз определить правильно, чем продолжать
добавлять локальные правила: **объём**, **количество в упаковке**, **длина в метрах**.
Все пять субагентов волны независимо вышли на отсутствие оси объёма как на главную
дыру словаря.

Параллельно вскрылся дефект pipeline: `enrich_attributes` молча пропускает
SELECT-значения, чьей опции ещё нет в БД (42 значения 2026-09-11, exit 0).

## Что исследовано (read-only, STOP conditions соблюдены)

| трек | документ | proposal |
|---|---|---|
| A. `volume` | [2026-09-12-fa-volume.md](2026-09-12-fa-volume.md) | `appendix/2026-09-12-foundation-axes/volume.proposal.json` |
| B. `package_quantity` | [2026-09-12-fa-package-quantity.md](2026-09-12-fa-package-quantity.md) | `…/package_quantity.proposal.json` |
| C. `linear_length` | [2026-09-12-fa-linear-length.md](2026-09-12-fa-linear-length.md) | `…/linear_length.proposal.json` |
| T. SELECT preflight | [2026-09-12-select-preflight-audit.md](2026-09-12-select-preflight-audit.md) | — (дизайн T2 в отчёте) |
| H. tree hygiene | [2026-09-12-tree-hygiene-audit.md](2026-09-12-tree-hygiene-audit.md) | `…/tree-hygiene.manifest.json` |

Сырые замеры стенда, скрипты и `cases.json` (по 90–130 кейсов на ось, все проходят
движком в памяти) остались в scratchpad сессии как доказательный слой; при
implementation кейсы переносятся в тесты.

## Итоговые числа

| ось | статус | CREATE (пул) | в наличии | фасетов ≥ порога | коллизии Attribute / PAV | новых options |
|---|---|---|---|---|---|---|
| `volume` | новая | **905** (22 типа) | 106 | 8 | 0 / 0 | 0 |
| `package_quantity` | расширение (id 85) | **977** (Tier 1: 97; Tier 2: 880) | 266 | keep 108 + до 11 | 0 / 0 (с `piece_count` — 0) | 0 |
| `linear_length` | новая | **545** (16 типов) | 61 | 1 (леска 92 %) | 0 / 0 | 0 |

CONFIRM и PROTECTED у всех трёх — 0. Runtime/code conversion не требуется:
единственный механизм — существующий `scale` в правилах.

## Решения владельца (2026-09-12)

| вопрос | решение |
|---|---|
| `linear_length`: критерий | **по классу товара**, не по единице. `length` (мм) — геометрический размер жёсткого изделия (линейка, лом, сверло, нож), нормализация «1,5 м → 1500 мм» допустима; `linear_length` (м) — товар, коммерческая сущность которого длинномер/гибкое изделие (трос, рукав, шланг, леска, канат) |
| существующие 78 PAV метров в `length` | **не откатывать** |
| `tape_length`, `cable_length` | сохранить как специализированные оси компонента, **не мигрировать** |
| global rule «м → linear_length», «Длина → linear_length» | **запрещено**; только tool_type/context-bounded mapping |
| `package_quantity` Tier 1 (лезвия, тросы, СВП) | **GO** |
| `package_quantity` Tier 2 (крепёж, пилки/полотна, абразивные расходники) | **GO по exact research list** из proposal; не расширять по похожему имени категории |
| semantic gate `package_quantity` | только «количество одинаковых товарных единиц в продаваемой упаковке»; label просто «Количество» без доказанной фасовки — **fail closed**; `piece_count` (элементы набора как продукта) не смешивать |
| `volume` | **GO**: canonical `volume`, «Объём», unit л, scale мл → л; `volume_l`/`volume_ml` не заводить |
| тачки | **GO с фасетом**; contextual label «Объём кузова», если presentation-слой позволяет; Attribute один |
| пылесосы (бак/контейнер) | **NO** в `volume`; future `tank_volume` — зафиксировать, **не создавать** в FA-01; то же для компрессоров, генераторов, краскопультов и любых встроенных баков/ресиверов |
| мешки пылесосов | **NO-GO**, fail closed: «36 л» — класс совместимых пылесосов / индекс серии, не объём мешка |
| 15 × «0,52 мл» у ЛКМ | **QUARANTINE / data_defect**; не нормализовать автоматически |
| SELECT preflight | **T2 + light T3**: preflight `required_options ⊆ DB AttributeOption` для фактического manifest **до** `ImportRun.create`; при нарушении execution не начинается |
| dry-run при missing option | **FAIL**, не warning |
| exit code | **2** для preflight/contract failure (если в CLI уже принят другой специализированный код — сохранить существующую convention, но non-zero) |
| bypass flag для write | **NO** (`--ignore-missing-options`, `--force` и аналоги не создавать); допустим read-only `--report-missing-options` (ничего не пишет, `ImportRun` не создаёт) |
| runtime guard | на write path unknown option → **raise / abort transaction**, не `continue` (защита от drift между preflight и write) |
| regression tests | A — все опции есть → PASS; B — одна missing → FAIL, `ImportRun` не создан, PAV 0, exit ≠ 0; C — несколько missing → все в отчёте; D — missing option **вне** текущего manifest не блокирует; E — runtime drift → abort |
| лезвия (72) → 107 / напрямую → 353 | **NO / NO**; **отдельный leaf «Лезвия» под 353**; tool_type не менять; перед write exact manifest |
| leaf «Правила и отвесы» | **GO**, внутри ветки измерительного/разметочного инструмента; tool_type `str-pravila` верный, не менять; перед созданием проверить дубли, canonical parent, slug, bindings родителя, состав |
| остальные tree-находки | только correction manifest; tree writes — отдельный OWNER GO |

## Обязательный порядок apply

Для блоков, которые могут добавить schema / bindings / options:

`load_attributes` → проверить Attribute/bindings/options → SELECT preflight →
dry-run enrichment → immutable manifest → backup → drift gate →
`enrich_attributes` → post-audit → rerun no-op.

Закреплён в [operations/README.md](operations/README.md).

## Scope FOUNDATION-AXES-01 (после отдельного GO)

- **A. volume** — Attribute `volume` (л, scale мл→л), approved bindings, тачки с фасетом,
  vacuum bags excluded, tank semantics excluded, 15 data_defect в карантин.
- **B. package_quantity** — расширение существующего Attribute; Tier 1 + exact Tier 2;
  никаких новых Attribute; никаких смешений с `piece_count`.
- **C. linear_length** — Attribute `linear_length` (м), class-based mapping,
  78 PAV не откатывать, `tape_length`/`cable_length` не мигрировать.
- **D. SELECT preflight** — required-options preflight, hard fail, non-zero exit,
  no write bypass, runtime fail-safe, тесты A–E.

**Не входит:** `tank_volume`, inch bar length, `cable_section` +35 options, FIRMAN,
заклёпочники, vi-longtail, dead tool_type cleanup, tree moves, новые leaf writes,
collector, Wave 2B/2C.
