# Память: catalog/stroitelnyy-roadmap

## Round 4C — «Ковши штукатурные» (завершено 2026-07-15)

**Статус**: ✅ Завершено

**Решение**: Вариант A (NEW tool_type)
- Создана опция: `id=419`, `value="Ковши штукатурные"`, `slug="kovshi-shtukaturnye"`, `sort_order=41`.
- Scope: 10 товаров в leaf 406 → root 191.
- Все `category_is_manual=True` сохранены.
- FP=0, все untyped до операции.

**Результат**:
- PAV created: 10.
- attrs_cache synced: 10/10.
- Post-audit: ✅ все проверки пройдены.
- Repeat dry-run: `PLAN_CREATE_OPTION=0`, `PLAN_ENRICH=0` (идемпотентность подтверждена).

**Бэкап**: `db-2026-07-15-0516.sql.gz`

**Rollback**:
- `DELETE FROM catalog_productattributevalue WHERE attribute_id=1 AND value_option_id=419;`
- `DELETE FROM catalog_attributeoption WHERE id=419;`
- Восстановить attrs_cache из rollback-map.

**Примечания**:
- 3 неактивных товара (`37240`, `37241`, `37247`) получили tool_type, но остались невидимыми — корректно.
- `sort_order=41` (`max+1` от предыдущего `40`).
