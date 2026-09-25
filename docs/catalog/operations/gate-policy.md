# Gate Policy — гейт-цикл любой операции каталога

Единый цикл для операций класса 1 (enrichment) и 2 (recategorize). Каждый шаг —
отдельный, с явным ОК владельца перед любым write.

## Цикл

1. **Read-only анализ** — понять состав, объёмы, leaf, семантику. Никаких предположений
   по одному слову: сначала leaf + контекст + samples.
2. **Preflight (read-only)** — зафиксировать канонический target (leaf/option), scope,
   `category_is_manual`, FP=0, существующие аналоги/опции.
3. **Dry-run (read-only)** — точный план: `PLAN_CREATE/UPDATE/SKIP`, per-type counts,
   scope-проверки, rollback-map. Показать владельцу. **Write не выполнять.**
4. **pg_dump** — свежий бэкап (см. [pgdump-policy](pgdump-policy.md)) ПОСЛЕ отдельного ОК.
5. **Write** — в одной `transaction.atomic`, со всеми guard-`assert` до записи.
6. **Post-audit** — обязательный набор проверок (см. [audit](audit.md)), включая
   repeat-preview = 0. Остановиться на post-audit.

## Правило разбиения scope

Если target **не однозначен** (нет корректного leaf/дома) или бакет **не однороден** —
**НЕ идти в write**. Разбить на под-бакеты или вынести в DEFER (архитектура). Примеры из
практики: 3C.2 гвоздодёры (нет leaf), 3A бытовая химия (нет v2-Хозтоваров), 3D.2 вибро
(разделилось на оснастку + реальные вибраторы + приводы).

## Guard-`assert` перед каждым write (шаблон)

```python
assert len(ids) == <N>                       # точный ожидаемый scope
assert set(ids) == {<явные id>}              # или явный список
assert all(p.category_id == SRC_LEAF for p in aff)
assert all(p.category_is_manual is True for p in aff)
assert target.id == TARGET and TARGET in <root_descendants>
assert target.on_site is True and target.is_active is True
# доп. по операции: option.value ok / none-have-tool_type / excluded ids not in scope
```

Любой невыполненный инвариант → скрипт падает ДО записи (транзакция не открывается).

## Изоляция инструментов

- Read-only анализ и write — через `docker compose ... exec web python manage.py shell`.
- Write-скрипты пишем inline (heredoc), чтобы не триггерить hooks на файлы-скрипты.
- Документацию правим git-only через **worktree от `origin/dev`** (в commit — только целевой
  файл; память/`MEMORY.md` — вне репозитория, коммитить нельзя).
