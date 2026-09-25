# attrs_cache sync — синхронизация фасет-кэша

`attrs_cache` (JSONB на `Product`) — источник фасетов витрины. `attrs_cache["tool_type"]`
должен совпадать с PAV `tool_type`.

## Почему это критично
- Фасеты читают **attrs_cache** (JSONB GROUP BY), а не PAV напрямую.
- `bulk_create` / `bulk_update` **обходят сигналы Django** → кэш НЕ пересчитывается сам.
- PAV без синхронного кэша = тип есть в БД, но **в фасете невидим** (или наоборот).

## Правило
При enrich — обновлять `attrs_cache["tool_type"]` **в той же `transaction.atomic`**,
что и `bulk_create` PAV:
```python
with transaction.atomic():
    ProductAttributeValue.objects.bulk_create(rows)          # PAV
    for p in prods:
        c = dict(p.attrs_cache or {}); c["tool_type"] = VALUE; p.attrs_cache = c
    Product.objects.bulk_update(prods, ["attrs_cache"])       # cache — синхронно
```
Никаких промежуточных состояний (PAV без кэша / кэш без PAV).

## Recategorize
Чистый перенос `category_id` **не трогает** attrs_cache (тип не меняется). Комбинированные
операции (category+тип) — обновляют кэш в той же транзакции.

## Post-audit
`attrs_cache synced == N/N`, `cache_bad == 0`. Ложная тревога бывает от бага probe
(`root_of.get(product_id)` вместо category→root) — проверять логику скрипта, не данные.
