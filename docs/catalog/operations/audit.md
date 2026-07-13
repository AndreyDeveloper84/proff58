# Post-audit — обязательный чеклист после write

Выполняется в той же сессии сразу после write. Остановиться на post-audit (не идти
дальше автоматически).

## Общий чеклист
- **счётчики операции:** `moved`/`created` == план; `still_in_source == 0`;
- **target:** count `before → after` (+N); **source:** `−N`;
- **excluded / соседние id:** не тронуты;
- **`category_is_manual=True`** сохранён у всех N;
- **publish-status** без изменений (`before == after`);
- **`slug`** без изменений;
- **`tool_type` / `attrs_cache`** — изменены только там, где это часть плана
  (иначе `before == after`);
- **total products / categories** без изменений;
- **repeat dry-run / migration-preview == 0** (идемпотентность);
- **rollback-map** зафиксирован;
- записан **путь pg_dump**.

## По типам операций
- **enrich:** `option usage before→after == plan`; `attrs_cache synced N/N`; `cache_bad=0`.
- **recategorize:** `target +N`, `source −N`, `migration-preview=0`.
- **new option:** `dup_name==1`, `dup_slug==1`, `usage==0`, totals без изменений.

## Формат
Показывать таблицей с явными before→after и отметкой ✅/значением по каждому пункту.
Любое расхождение — стоп и разбор до продолжения.
