# ХАР-20 — манифест отката corrective-миграции `piece_count` → `package_quantity`

Область: `tool_type = str-skoby`, 22 товара (active + `available_quantity > 0`),
снимок стенда `proff58_staging` от 2026-08-12 (read-only).

**Откат строится по `product_id`, а не по PAV ID.** После corrective-прогона
старые PAV удаляются, а после отката создаются заново — идентификаторы будут
другими. Сверять нужно пару «атрибут + значение» на товар.

## Формат

```
product_id | old_attribute | old_value | new_attribute | new_value
```

`old_*` — состояние ДО миграции (то, что откат обязан восстановить),
`new_*` — состояние ПОСЛЕ миграции. Значение сохраняется семантически:
число не меняется, меняется только ось.

## Строки (22)

```
37737 | piece_count | 5000 | package_quantity | 5000
37738 | piece_count | 5000 | package_quantity | 5000
37739 | piece_count | 5000 | package_quantity | 5000
37743 | piece_count | 5000 | package_quantity | 5000
37744 | piece_count | 5000 | package_quantity | 5000
37745 | piece_count | 5000 | package_quantity | 5000
37746 | piece_count | 5000 | package_quantity | 5000
37747 | piece_count | 5000 | package_quantity | 5000
37749 | piece_count | 1000 | package_quantity | 1000
37754 | piece_count | 5000 | package_quantity | 5000
37758 | piece_count | 1000 | package_quantity | 1000
37759 | piece_count | 1000 | package_quantity | 1000
37760 | piece_count | 1000 | package_quantity | 1000
37761 | piece_count | 1000 | package_quantity | 1000
37762 | piece_count | 1000 | package_quantity | 1000
37763 | piece_count | 2500 | package_quantity | 2500
37764 | piece_count | 2500 | package_quantity | 2500
37765 | piece_count | 2500 | package_quantity | 2500
37766 | piece_count | 2500 | package_quantity | 2500
37767 | piece_count | 2500 | package_quantity | 2500
37771 | piece_count | 5000 | package_quantity | 5000
37772 | piece_count | 5000 | package_quantity | 5000
```

Распределение значений: `5000` — 11 товаров, `1000` — 6, `2500` — 5.
Источник всех 22 старых PAV — `regex` (∈ `PRUNABLE_SOURCES`), поэтому prune
имеет право их удалить.

PAV ID на момент снимка (только для сверки «ничего не разъехалось» ПЕРЕД
прогоном; для отката не использовать): 64925, 64927, 64929, 64931, 64933,
64935, 64937, 64939, 64941, 64943, 64945, 64947, 64949, 64951, 64953, 64955,
64957, 64959, 64961, 64963, 64965, 64967.

## Как исполняется откат

Ручной SQL и ручная правка `attrs_cache` запрещены. Откат — тот же штатный
движок по **зеркальному** ruleset (проверено тестом
`test_rollback_restores_original_attribute_and_value`):

1. в блоке `str-skoby` вернуть `piece_count` рабочий regex фасовки
   `(?<!\d)(\d{3,5})\s*шт` и убрать у него `skip_if`;
2. `package_quantity` **оставить объявленным** в том же блоке, но заглушить его
   так же, как глушился `piece_count`: `skip_if: ["шт"]` +
   `regex: ["(?<!\\d)(\\d{3,5})\\s+шт"]`.
   Убирать `package_quantity` из блока НЕЛЬЗЯ: prune обходит только managed-slug'и
   своего `tool_type`, и вне managed-множества 22 новых PAV осиротеют;
3. прогнать `enrich_attributes --tool-type str-skoby --in-stock-only --active-only`
   на тех же 22 товарах;
4. сверить результат с таблицей выше: у каждого `product_id` должен снова быть
   `piece_count` с прежним значением и не быть `package_quantity`.

## CategoryAttribute ↔ категория 108 — обязательная часть контракта

Категория 108 = «Скобы и стержни клеевые» (`skoby-i-sterzhni-kleevye`),
потомков нет (проверено на стенде 2026-08-13).

**Before snapshot старой привязки** (снят со стенда `proff58_staging`
2026-08-13, до записи):

```
id                = 242            # surrogate, на восстановление НЕ рассчитывать
category_id       = 108
attribute_id      = 32
attribute_slug    = piece_count
attribute_name    = Предметов в наборе
attribute_type    = decimal
attribute_unit    = шт
is_filterable     = True           # поле Attribute, глобальное
is_required       = False
is_filter         = True
group             = main
is_seo_facet      = False
display_name      = ""             # пусто
sort_order        = 0
```

Соседняя привязка той же категории (ХАР-20 её не трогает, служит контролем):

```
id=241 | category 108 | length | is_required=False | is_filter=True |
group=main | is_seo_facet=True | display_name="" | sort_order=0
```

Forward:

```
DELETE  piece_count      ↔ category 108   (строка id=242)
CREATE  package_quantity ↔ category 108
```

Rollback:

```
DELETE  package_quantity ↔ category 108
RESTORE piece_count      ↔ category 108   с полями из before snapshot выше
```

Восстанавливается **семантически та же запись**, а не surrogate `id=242`:
пара (`category_id=108`, `attribute=piece_count`) плюс перечисленные флаги и
метаданные. Новый `id` допустим и ожидаем.

Обоснование, почему снос старой привязки безопасен (проверено на стенде):

- у категории 108 потомков нет — наследовать фасет некому;
- после миграции валидных потребителей `piece_count` в категории 108 не
  остаётся (все 22 её товара переходят на `package_quantity`);
- остальные 165 валидных `piece_count` живут в других категориях
  (`nabory-otvertok` 160, `sharoshki` 5) и обслуживаются своими привязками —
  ХАР-20 их не касается.

Технически: удаление привязки `package_quantity ↔ 108` и восстановление
`piece_count ↔ 108` — это операции над `CategoryAttribute`, а не правка
значений товаров; `load_attributes` — no-delete, поэтому снятие привязки
выполняется явным удалением ровно одной строки по паре
(`category_id=108`, `attribute__slug=package_quantity`), а восстановление —
повторным `load_attributes` по зеркальному ruleset (он создаст
`piece_count ↔ 108` с флагами блока) с последующей сверкой полей по snapshot
выше.

## Attribute `package_quantity` — удаление только под guard

`load_attributes` сам ничего не удаляет (no-delete), поэтому удаление самого
`Attribute package_quantity` при откате — отдельное явное действие, и оно
разрешено **только** при одновременном выполнении:

```
package_quantity has 0 ProductAttributeValue
AND
package_quantity has 0 CategoryAttribute (и любых иных ссылок)
```

Порядок отката: сначала шаги 1–4 выше (22 PAV возвращены на `piece_count`),
затем снятие привязки `package_quantity ↔ 108`, и только потом — проверка
guard и удаление атрибута.

Если между forward и rollback появились сторонние значения или связи
`package_quantity` (другое окно, другая волна, ручная правка) — guard не
проходит:

```
ROLLBACK STOP
```

Останавливаемся безопасно и докладываем. Чужие данные ради отката ХАР-20 не
удаляются. Незакрытый откат в таком состоянии — это `package_quantity`,
оставшийся в БД как неиспользуемый атрибут; это допустимый исход, потеря
данных — нет.

## Товар 37732 — вне области отката

```
37732 / length=12 / OUTSIDE HAR-20 ROLLBACK SCOPE
```

Название на стенде: «Скобы для пневматического степлера, тип 80, 12 мм,»
(категория 352, `is_active=True`, остаток 1). До ХАР-20 у товара был ровно
один PAV — `tool_type=str-skoby` (`source=manual`).

Три доказательства, что `length=12` — корректный независимый side effect:

1. **Единственный дополнительный CREATE вне package-миграции.** В песочнице
   `create=23` при `prune=22`: 22 создания — это `package_quantity` у 22
   товаров с фасовкой, 23-е — `length=12` у 37732. Больше ни одного создания
   вне пары `piece_count → package_quantity` план не содержит; проверяется
   повторно финальным dry-run на стенде перед записью.
2. **Значение корректно по названию.** «тип 80, **12 мм**» — высота ножки
   скобы, ровно та величина, которую описывает атрибут `length` («Длина», мм).
   Фасовки в названии нет (нет «шт»), поэтому `package_quantity` у 37732
   не создаётся — и не должен.
3. **Создаётся постоянным ruleset, а не transitional-правилом.** Правило
   `length` в блоке `str-skoby` — `(?<![\d.,\-])(\d{1,2})\s*мм` — существовало
   до ХАР-20 и коммитами ветки `feature/har-20-package-quantity` не менялось
   (diff `ac63d10..621df98` по `data/attribute_rules.json` затрагивает только
   `package_quantity` и `piece_count`). Значение появляется потому, что 37732
   впервые попал в прогон `enrich_attributes` по этому блоку, а не потому,
   что ХАР-20 что-то добавил.

Следствие: откат ХАР-20 **не удаляет** `37732 / length=12`. Зеркальный ruleset
шага 1 оставляет правило `length` нетронутым, поэтому повторный прогон это
значение сохранит (`action=keep`).
