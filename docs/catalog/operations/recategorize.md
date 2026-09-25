# Recategorize — перенос между ветками дерева (класс 2)

Изменение `product.category_id` для исправления ошибочного размещения.

## Процедура
1. **Preflight:** канонический target-leaf (существующие аналоги там же); target
   `on_site=True`, `is_active=True`, под правильным v2-root; scope, `category_is_manual`.
2. **Dry-run:** rollback-map (`product_id: old → target`), FP=0, единый source leaf.
3. **pg_dump** ([pgdump-policy](pgdump-policy.md)).
4. **Write:** `Product.objects.filter(id__in=ids).update(category_id=TARGET)` в
   `transaction.atomic` (bulk `.update()` — без сигналов, кэш/тип не пересчитываются).
5. **Post-audit** ([audit](audit.md)): moved=N, target +N, source −N, excluded не тронуты,
   migration-preview=0.

## Инварианты
- `category_is_manual=True` **сохраняется** (не отменяем ручное управление).
- `slug` / `publish-status` / `tool_type` / `attrs_cache` — **НЕ трогаем** (если это чистый
  recat). Product — не tree-node, `category_id` = обычный FK, treebeard-move не нужен.

## Комбинированный перенос (category + tool_type)
Если товар одновременно меняет категорию и получает тип (напр. реальные вибраторы →
Электро + option 417): все изменения — **в одной `transaction.atomic`**
(`update(category_id)` + `bulk_create` PAV + `bulk_update` attrs_cache), без промежуточных
состояний. Rollback-map — двойной (category + удалить PAV + cache→None).

## Правило stop
Нет корректного target-leaf → **не переносить** (defer в [new-leaf](new-leaf.md)).
Класть «в ближайшее» — значит закрепить новую ошибку (урок 3C.2, 3A).
