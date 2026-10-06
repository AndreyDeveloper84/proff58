# Enrich — присвоение tool_type (класс 1)

Scoped-присвоение `tool_type` товарам (PAV + attrs_cache). Для new type и reuse.

## Когда
- reuse существующего `AttributeOption` (leaf-scoped);
- после создания нового типа ([new-tool-type](new-tool-type.md)).

## Процедура
1. **Leaf-scoped выборка** untyped-товаров (без PAV `tool_type`) в целевом leaf;
   ключи — узкие подстроки поверх leaf-контекста (широкие запрещены).
2. **Dry-run:** `PLAN_CREATE` (сколько получат тип), `PLAN_UPDATE=0`, FP-исключения,
   overlap (first-match priority при нескольких типах). Показать план.
3. **pg_dump** ([pgdump-policy](pgdump-policy.md)).
4. **Write:** `bulk_create` PAV(option) **+** синхронно `attrs_cache["tool_type"]`
   ([cache-sync](cache-sync.md)) через `bulk_update` — в одной транзакции на чанк
   (команды enrich пишут чанками по 500 товаров, DRF-2738; scoped-скрипт на десятки
   товаров — одной `transaction.atomic`).
5. **Post-audit** ([audit](audit.md)): статус `ImportRun` = `done` (при `failed` —
   повтор до `done` или откат по снимку), option usage before→after == plan, cache N/N,
   cache_bad=0, вне scope=0, repeat-preview=0.

## Guards
`len(plan)==N` · per-type counts == dry-run · все в целевом leaf · none-typed сейчас ·
FP-id не в наборе · `option.value` корректен.

## Уроки
- **RECOVERY ≠ NEWASSIGN:** recovery = у товара уже есть stored-PAV (словарь его лишь
  воспроизводит) → enrich идемпотентен, 0 изменений. NEWASSIGN = untyped получает тип.
- **Глобальный enrich опасен:** снимает типы, которые словарь не воспроизводит
  (reconcile-урок, PR #470). Только scoped-apply.
- FP по одному слову (`клей`→«Клеймо», `лак`→электроизоляция) — только leaf + узкие ключи.
