# Reverse migration `tool_type`: откат применённого и понижение версии словаря

> Wave 7.1 / стадия **H5**. Статус: реализовано и покрыто тестами.
> Смежные документы: [operations/rollback.md](operations/rollback.md) (политика отката),
> [operations/README.md](operations/README.md) (гейт-цикл),
> [tool-type-taxonomy-manifest.md](tool-type-taxonomy-manifest.md) (форвардный путь словаря),
> [rules-release-manifest.md](rules-release-manifest.md) (версия контура).

## 1. Зачем

До H5 у контура распознавания `tool_type` был только форвардный путь:

- словарь эволюционирует «вперёд» — манифест плюс fail-closed seed `load_tool_types`,
  который создаёт недостающие опции и **никогда ничего не удаляет**;
- предложения применяются к товарам, и обратной операции не существовало.

Отсюда два необратимых состояния. Первое: опция исчезла из манифеста, а товары
остались висеть на записи, которой в словаре больше нет. Второе: применённые
`tool_type` нечем откатить иначе как восстановлением всей БД из pg_dump —
инструмента грубого и непригодного, когда с момента записи произошли другие
изменения.

H5 закрывает обе дыры **проверяемой** процедурой: не «можно откатить руками», а
«откат исполняется командой, идемпотентен, отказывается работать поверх
изменившегося baseline и подтверждается post-audit».

## 2. Два контура

| Контур | Модуль | Команды | Что делает |
|---|---|---|---|
| Откат применённого `tool_type` | `apps/catalog/tool_type_rollback.py` | `catalog_tool_type_snapshot`, `catalog_tool_type_rollback` | возвращает товарам прежние опции и `attrs_cache` |
| Понижение версии словаря `N → N-1` | `apps/catalog/taxonomy_reverse.py` | `catalog_taxonomy_downgrade` | решает судьбу исчезающих опций и товаров на них |

Второй контур исполняет перенос товаров **через первый** — поэтому у понижения
версии ровно та же семантика идемпотентности и конфликта, что у обычного отката.
Отдельной, менее строгой ветки записи не существует.

## 3. Артефакт снимка

Снимок — канонический JSON той же рецептуры, что release manifest H3
(`rules_release.canonical_bytes`): два прогона на неизменной БД дают побайтово
идентичный файл.

```json
{
  "canonical": {
    "schema_version": 1,
    "attribute_slug": "tool_type",
    "selector": {"kind": "explicit_ids", "value": [101, 102]},
    "live_taxonomy_identity_hash": "fc13be78…",
    "rows_count": 2,
    "rows": [
      {"product_id": 101, "option_slug": "bury", "option_value": "Буры",
       "attrs_cache_tool_type": "Буры"},
      {"product_id": 102, "option_slug": null, "option_value": null,
       "attrs_cache_tool_type": null}
    ]
  },
  "canonical_hash": "<sha256 canonical>"
}
```

Свойства, на которые опирается процедура:

- **строки явные** — `product_id` перечислены поимённо, как требует
  [rollback.md](operations/rollback.md) («все id в карте — явные, не „по правилу“»);
- **`attrs_cache_tool_type` входит в снимок** — read-model восстанавливается вместе
  с EAV, а не «пересоберётся когда-нибудь»;
- **`live_taxonomy_identity_hash`** — тот же recipe, что `taxonomy_identity_hash` из
  H1; если словарь дрейфовал с момента снимка, откат отказывается работать;
- **`canonical_hash`** — подделка любой строки ловится при загрузке.

Селектор ровно один: `--product-ids` (предпочтительно), `--option-slug` или
`--all-with-tool-type`.

## 4. Семантика отката: почему нужна пара снимков

Откат исполняется по **паре** снимков, а не по одному:

- `--from` — состояние, которое ожидается в БД сейчас (что записал forward-прогон,
  снимок «после»);
- `--to` — состояние, к которому возвращаемся (снимок «до»).

| live | решение | почему |
|---|---|---|
| `== to` | **noop** | уже откачено; отсюда идемпотентность повторного запуска |
| `== from` | **write** | штатный откат |
| ни то, ни другое | **conflict** | baseline изменился после записи — молчаливой перезаписи не будет |

Одного снимка «до» здесь принципиально недостаточно: по нему нельзя отличить
«изменение, которое мы откатываем» от «изменения, которое внёс кто-то другой». Это
та же логика, что у `CatalogProcessingItem.baseline_hashes` в
[operations/README.md](operations/README.md): изменение baseline после снимка → `conflict`.

Отсутствие `--from` не имеет обходного флага: без него conflict-детекция
невозможна, поэтому оба аргумента обязательны.

Сравнение идёт по `option_slug` — по значению EAV, единственному источнику правды.
`attrs_cache` производен и восстанавливается по снимку, расхождение в нём конфликта
не создаёт.

## 5. Процедура отката применённого `tool_type`

Вписана в универсальный гейт-цикл
`read-only → preflight → dry-run → pg_dump → write → post-audit`.

```bash
# 0. ДО записи (обязательно, иначе откат невозможен)
manage.py catalog_tool_type_snapshot --product-ids 101,102,103 --out before.json

# ... forward-прогон (enrich / apply) ...

# 1. ПОСЛЕ записи — второй снимок
manage.py catalog_tool_type_snapshot --product-ids 101,102,103 --out after.json

# 2. dry-run отката: план без записи
manage.py catalog_tool_type_rollback --from after.json --to before.json

# 3. pg_dump по docs/catalog/operations/pgdump-policy.md

# 4. write
manage.py catalog_tool_type_rollback --from after.json --to before.json --apply

# 5. post-audit выполняется автоматически: "post-audit=PASS rows_checked=N"
```

Свойства шага 4:

- вся запись — одна `transaction.atomic()`; сбой на середине не оставляет
  полуприменённого состояния;
- план с **хотя бы одним** конфликтом не применяется целиком (не «остальные
  запишем, конфликтные пропустим»);
- повторный запуск после успешного отката → `write=0`, `noop=N`;
- post-audit пересобирает снимок по тем же товарам и сверяет с целевым, включая
  `attrs_cache`.

Exit codes: `0` — план исполним / откат применён и post-audit пройден;
`1` — conflict, не записано ничего; `2` — невалидные артефакты; `3` — internal или
не сошедшийся post-audit.

## 6. Процедура понижения версии словаря `N → N-1`

Порядок жёсткий; шаги 2–4 выполняются только на `feasible=True`.

```bash
# 1. План (read-only). Без --apply в БД не пишется ничего.
manage.py catalog_taxonomy_downgrade \
    --from-manifest data/catalog_processing_rules/tool_type_taxonomy.v1.json \
    --to-manifest  path/to/tool_type_taxonomy.v0.json \
    --remap remap.json --out downgrade-plan.json

# 2. Перенос товаров с исчезающих опций (через контур отката)
manage.py catalog_taxonomy_downgrade … --emit-from from.json --emit-to to.json
manage.py catalog_tool_type_rollback --from from.json --to to.json --apply

# 3. Удаление освободившихся опций (fail-closed по usage)
manage.py catalog_taxonomy_downgrade … --drop-options            # dry-run
manage.py catalog_taxonomy_downgrade … --drop-options --apply    # write

# 4. Возврат опций, которые были в N-1 и исчезли в N
manage.py load_tool_types --manifest path/to/tool_type_taxonomy.v0.json
```

Решение по каждому slug:

| disposition | условие | действие |
|---|---|---|
| `keep` | есть в обоих манифестах, `value` совпадает | ничего |
| `reappearing` | есть только в N-1 | вернёт seed (шаг 4) |
| `drop` | исчезает, товаров нет | удаляется (шаг 3) |
| `remap` | исчезает, товары есть, владелец задал явную цель | перенос (шаг 2), затем удаление |
| `blocked` | однозначного отката нет | понижение не исполнимо |

`remap.json` — плоское отображение `{"исчезающий_slug": "целевой_slug"}`. Цели
проверяются: должна существовать в N-1, существовать в live-словаре и сама не
исчезать при понижении.

## 7. Fail-closed матрица

Понижение объявляется неисполнимым (`feasible=false`, exit 1), если:

| код | ситуация | почему нельзя «догадаться» |
|---|---|---|
| `orphaned_products` | исчезающая опция несёт товары, remap не задан | цель переноса — продуктовое решение |
| `remap_target_disappearing` | цель переноса сама исчезает в N-1 | получился бы новый сирота |
| `remap_target_unknown` | цели нет в манифесте N-1 | опции создаются только из манифеста |
| `remap_target_not_live` | цель есть в N-1, но её нет в живой БД | перенос некуда исполнить |
| `value_change_requires_manual` | у выжившей опции меняется `value` | seed на конфликте `value` падает, а не чинит |
| `live_not_at_from_manifest` | живой словарь не приведён к манифесту N | план строился бы по несуществующему состоянию |

Структурно невозможные запросы отклоняются раньше плана (exit 2): несмежные версии
(поддерживается только `N → N-1`), обратное направление, манифесты по разным
атрибутам, `remap` для slug, который при понижении не исчезает.

Удаление опций (`--drop-options --apply`) fail-closed отдельно: usage проверяется
**в момент выполнения** внутри транзакции, и любая исчезающая опция с товарами
отменяет операцию целиком. Поэтому перенос физически невозможно перепрыгнуть.

## 8. Известные пробелы

1. **`option_uid` не введён.** Без стабильного идентификатора опции переименование
   slug неотличимо от «удалили одну опцию, добавили другую», поэтому remap может
   быть только явным решением владельца — автоматически вывести цель переноса
   нельзя. Это осознанное ограничение, а не недоделка: см.
   `future_evolution.immutable_option_identity` в манифесте и раздел решения в
   `scratchpad/wave7/wave7-h5-report.md`.
2. **Смена `value` при понижении не автоматизирована** — блокируется явно
   (`value_change_requires_manual`), потому что инструмента изменения `value`
   существующей опции в контуре нет.
3. **Откат восстанавливает только `tool_type`.** Другие атрибуты и категория —
   вне контура; для них действуют плейбуки
   [enrich](operations/enrich.md) / [recategorize](operations/recategorize.md).
4. **`manifest_version` = 1.** Реального понижения ещё не было: контур построен и
   проверен на синтетических манифестах во временных каталогах.
