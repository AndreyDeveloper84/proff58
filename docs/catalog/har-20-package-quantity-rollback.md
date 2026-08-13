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

`Attribute package_quantity` при откате не удаляется (`load_attributes` —
no-delete); осиротевшей останется только привязка `CategoryAttribute`
`package_quantity` ↔ «Скобы и стержни клеевые» — пустой фасет, снимается
отдельно.
