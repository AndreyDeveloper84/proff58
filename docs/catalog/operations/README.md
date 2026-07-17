# Catalog Operations Framework

Переиспользуемая методология изменений каталога (v2-дерево «Профессионал»),
извлечённая из серии работ над разделом «Строительный» (reconcile + Round 1–4).
Цель — чтобы любой разработчик/агент выполнял операции по каталогу **одинаково,
воспроизводимо и с откатом**, а не «руками по разделам».

Рабочий пример применения всех плейбуков: [`../stroitelnyy-roadmap.md`](../stroitelnyy-roadmap.md).

## Каталог делится не по разделам, а по 4 классам задач

| Класс | Что это | Механизм | Плейбуки |
|---|---|---|---|
| **1. Safe enrichment** | присвоение tool_type (new type / reuse), PAV + attrs_cache | scoped enrich | [enrich](enrich.md), [new-tool-type](new-tool-type.md), [cache-sync](cache-sync.md) |
| **2. Safe recategorize** | перенос товара между ветками дерева (`category_id`) | category migration | [recategorize](recategorize.md), [rollback](rollback.md) |
| **3. Tree architecture** | новый leaf / раздел (Хозтовары, Стройматериалы, leaf гвоздодёров) | структура дерева | [new-leaf](new-leaf.md) |
| **4. Семантические типы** | развитие словаря типов (Ковши, Loctite, Антикор, Стройхимия) | new option / словарь | [new-tool-type](new-tool-type.md) |

Классы 1–2 доведены до промышленного уровня. Классы 3–4 — реальные оставшиеся задачи.

## Универсальный гейт-цикл (для любой операции класса 1–2)

`read-only анализ → preflight → dry-run → pg_dump → write → post-audit`

Подробно и с инвариантами: [gate-policy](gate-policy.md). Опорные политики:
[pgdump-policy](pgdump-policy.md) · [rollback](rollback.md) · [audit](audit.md).

## Золотые инварианты (соблюдать во ВСЕХ write)

1. `category_is_manual=True` **сохраняется** при переносах (сайт — мастер контента;
   исправляем конкретное ошибочное размещение, не отменяем ручное управление).
2. **Только явно утверждённые `product_id`** — никаких широких правил на write.
3. **Свежий pg_dump перед каждым write** + запись в одной `transaction.atomic`.
4. **rollback-map** обязателен (product_id → old→new; для комбинированных — двойной).
5. **slug и publish-status не меняются** recat'ом/enrich'ем.
6. `tool_type`/`attrs_cache` меняются **только там, где это часть утверждённого плана**.
7. **Никаких глобальных write-команд** — всё scoped и идемпотентно проверено
   (repeat-preview = 0 после write).
8. **Сначала leaf, потом keywords** — v2-лист даёт контекст; широкие подстроки запрещены.

## Catalog processing foundation (rule/AI/research)

Для воспроизводимого применения любых массовых решений (rule-based, AI, Codex research)
используется единый механизм в `apps/catalog/processing.py`:

- `CatalogProcessingRun` — запуск со scope и версионностью.
- `CatalogProcessingItem` — snapshot одного товара на момент запуска
  (`input_snapshot`, `input_hash`, `baseline_hashes`, `needed_targets`).
- `CatalogChange` — append-only запись предложенного и применённого значения.
- `apply_catalog_decision(...)` — атомарно применяет решение через
  `provenance.apply_sourced_value`, пересобирает `attrs_cache` и фиксирует результат.

Инварианты foundation:

1. БД — источник истины; JSON/SQL-файлы — только транспорт/бэкап.
2. Snapshot фиксирует baseline; изменение baseline после snapshot → `conflict`.
3. `idempotency_key` гарантирует, что повторный вызов не создаёт дубликатов.
4. `content_locked=True` блокирует write.
5. Source priority единый — `data/attribute_rules.json` + `provenance.py`.
6. `apply_catalog_decision` не создаёт новые taxonomy entities, не меняет цены/остатков.

Текущий scope foundation — `tool_type`; категория и атрибуты добавляются последовательно
(см. ADR-0010).

## Приоритеты развития (проект целиком)

1. **Архитектура дерева** — v2 «Хозтовары», раздел «Стройматериалы», leaf гвоздодёров.
   Снимает большинство defer-задач Round 3/4.
2. **Словарь типов** — Ковши, Фиксаторы резьбы (Loctite), Антикор, Стройхимия.
3. **Следующий раздел каталога** — технология отлажена, можно масштабировать.
4. **Автоматизация** — `manage.py catalog_preflight / catalog_dryrun / catalog_apply /
   catalog_postaudit`, чтобы round занимал минуты, а не день.
