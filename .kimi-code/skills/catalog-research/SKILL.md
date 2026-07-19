---
name: catalog-research
description: >
  MUST EXECUTE when the user says "catalog-research", "run catalog-research",
  "$catalog-research", "исследуй batch", "обработай run", "найди tool_type для run",
  or any phrase asking to research catalog items for an exported CatalogProcessingRun.
  Reads the exported JSON for the given run_id, researches tool_type values on the web,
  writes a schema-valid result JSON to var/catalog-processing/inbox/<run_id>.result.json,
  runs catalog_queue_import without --commit (dry-run), and stops before commit to ask
  for explicit user approval.
type: prompt
whenToUse: >
  User provides a CatalogProcessingRun UUID and asks to research tool_type values,
  process a research queue, or research catalog items.
arguments:
  - run_id
---

# $catalog-research

Catalog research skill для безопасного web-исследования `tool_type` товаров из
экспортированного `CatalogProcessingRun`.

## Аргументы

- `$run_id` — UUID `CatalogProcessingRun`, который уже экспортирован
  (`catalog_queue_export --run $run_id`).

## Workflow

1. **Проверить run**
   - Убедись, что `$run_id` — валидный UUID.
   - Найди run в БД:
     ```bash
     python manage.py catalog_queue_status --run $run_id
     ```
   - Run должен быть в статусе `running`.

2. **Прочитать export**
   - Файл: `var/catalog-processing/outbox/$run_id.json`.
   - На staging файл доступен и на хосте: `./var` примонтирован в `/app/var`
     (постоянный bind mount, см. runbook
     `docs/catalog/operations/research-queue.md`). `docker cp` не используем.
   - Запомни `taxonomy_hash`, `checksum`, `target_kind`, `allowed_options`.
   - Перенеси export-поле `checksum` в result-поле `export_checksum`.
   - Убедись, что `target_kind == "tool_type"`.

3. **Обрабатывать items группами по 5–10 штук**
   - Для каждого item выполни identity gate
     (см. `references/source-policy.md`).
   - Ищи только нужные target fields (`tool_type`).
   - Не переноси характеристики без identity match.

4. **Web research**
   - Источники в порядке приоритета:
     1. Официальный сайт производителя.
     2. Официальный PDF/manual/catalog.
     3. Официальный дистрибьютор.
     4. Крупный специализированный магазин.
     5. Marketplace — только как слабое подтверждение.
   - Для каждого предлагаемого значения сохраняй URL/evidence.

5. **Выбрать option slug**
   - Только из `allowed_options` списка export.
   - Не создавай новых taxonomy entities.
   - Если не уверен — верни `status: "review"` или `status: "unknown"`.
   - Любой item с `changes` обязан иметь `identity.status: "matched"`;
     `review` означает сомнение в target value, а не в идентичности товара.

6. **Записать result JSON**
   - Путь: `var/catalog-processing/inbox/$run_id.result.json`.
   - Структура: см. `references/result-contract.md`.
   - Должен проходить JSON Schema в
     `apps/catalog/schemas/catalog_research_result_v1.json`.

7. **Запустить dry-run importer**
   ```bash
   python manage.py catalog_queue_import --file var/catalog-processing/inbox/$run_id.result.json
   ```
   - Если есть ошибки — исправь result JSON и повтори.

8. **Остановиться перед commit**
   - Не запускай `--commit` без явного подтверждения пользователя.
   - Покажи summary: сколько предложений, источники, ошибки, dry-run result.

## Запреты

- Прямой ORM update товаров.
- `--commit` без подтверждения.
- Изменение price/stock/availability/order state.
- Выдуманные URL/evidence.
- Значение без identity match.
- Создание новых category/attribute/option slugs.
- Использование slugs вне `allowed_options`.

## Полезные команды

```bash
# Status run
python manage.py catalog_queue_status --run $run_id

# Export (если ещё не экспортирован)
python manage.py catalog_queue_export --run $run_id

# Dry-run import
python manage.py catalog_queue_import --file var/catalog-processing/inbox/$run_id.result.json

# Commit (только после подтверждения пользователя)
python manage.py catalog_queue_import --file var/catalog-processing/inbox/$run_id.result.json --commit
```

## References

- `references/source-policy.md` — приоритет источников и identity gate.
- `references/result-contract.md` — формат result JSON.
- `references/taxonomy-routing.md` — allowed options и category routing.
