# New tool_type — создание AttributeOption (класс 4)

Создание нового значения словаря типов, когда reuse не подходит семантически.

## Когда
Существующий тип не отражает сущность (напр. «Строительные леса и вышки-туры»,
«Фиксаторы и герметики резьбы», «Ковши штукатурные»). Сначала проверить reuse!

## Preflight (read-only)
- `NAME_EXISTS=False`, `SLUG_TAKEN=False`;
- **naming convention:** транслит с дефисами, **без секционного префикса**
  (напр. `stroitelnye-lesa-vyshki`, `vibratory-betona`); сверить с последними option;
- `sort_order`: поле НЕ уникально → допустим `0` (порядок в панели настраивается отдельно);
- проверить, нет ли похожих по смыслу (не задваиваем).

## Write (одна строка)
```python
AttributeOption.objects.get_or_create(
    attribute=attr, value=NAME, defaults={"slug": SLUG, "sort_order": 0})
```
`transaction.atomic`; идемпотентно (pre-check).

## Post-audit
`created=True`, `dup_name==1`, `dup_slug==1`, `usage_PAV==0`, options `+1`,
products/categories/PAV totals **без изменений** (создание опции ничего не типизирует).

## Далее
Типизация товаров этим option — отдельный gated шаг [enrich](enrich.md).
Одно значение может переиспользоваться в разных секциях (кросс-секционный reuse —
норма: одинаковый `value`, разные `slug` в правилах словаря).
