# ADR-0012: Уникальность `AttributeOption.slug` — разрешение DEVIATION-2

- Статус: принято (2026-07-22); remediation реализована в Phase 7A.2
  (ветка `feat/phase7a2-deviation2-remediation`); RESOLVED — после
  post-deploy verification на staging
- Дата: 2026-07-22
- Связано: ADR-0001 (tool_type — атрибут, не категория),
  ADR-0010 (catalog processing foundation),
  ADR-0011 (материализация option через changeset),
  `docs/plans/2026-07-22-PHASE7A_2_DEVIATION2_REMEDIATION_PLAN.md`

## Контекст

Phase 7A.1 (read-only investigation, staging) установила:

- Единственный duplicate slug в каталоге: `tool_type` / `steplery` ×2 —
  **id=16** «Степлеры и заклёпочники» (sort_order=15, 10 PAV/10 товаров) и
  **id=73** «Степлеры (скобозабивные)» (sort_order=28, 42 PAV/42 товара).
- Дивергенция подсистем при резолве slug `steplery`:
  apply/provenance (`.first()` по `Meta.ordering`) выбирал **id=16**,
  facets (`_option_slug_maps`, last-write-wins) — **id=73**. 10 товаров
  id=16 были недостижимы через facet-URL `?tool_type=steplery`.
- Root cause: seed `data/tool_type_rules.json` содержал обе записи со
  slug `steplery`; схема имела `unique_together = (attribute, value)` и не
  имела ограничения на `(attribute, slug)`; `load_tool_types` принимал
  дубль молча; `backfill_option_slugs` заполнял только пустые slug.

Класс проблемы: комбинация data-integrity defect, user-visible taxonomy
ambiguity (активная) и latent nondeterminism (выбор зависел от
инцидентального `sort_order`).

## Рассмотренные варианты

### Вариант (b) — слияние в одну запись

Миграция 10 PAV на id=73, удаление id=16. **Отклонён**: «Степлеры и
заклёпочники» и «Степлеры (скобозабивные)» — разные таксономические
сущности; слияние необратимо на уровне смысла данных.

### Вариант (d) — только код (детерминированный lookup)

`order_by` / `.get()` без правки данных. **Отклонён как недостаточный**:
оба значения продолжали бы эмитить один slug в фасетах — user-visible
ambiguity сохранялась бы.

### Вариант (c+) — re-slug + constraint + fail-fast (принят)

Сохранить обе сущности; id=16 получает новый уникальный slug; id=73
сохраняет `steplery`; плюс схемный констрейнт, строгие lookup и
валидация импорта.

## Решение

1. **Каноническая запись**: id=73 «Степлеры (скобозабивные)» сохраняет
   slug `steplery` (42 товара; фактический резолв витрины до remediation).
2. **Re-slug**: id=16 «Степлеры и заклёпочники» → slug
   `steplery-i-zaklepochniki` (вывод `slugify_value` значения; pre-flight
   на staging — свободен). Значение, sort_order, PAV и `attrs_cache` не
   изменяются — меняется только идентификатор.
3. **Схема**: partial `UniqueConstraint(attribute, slug)` для непустых
   slug (`uniq_attributeoption_attr_slug_nonempty`); пустые slug остаются
   разрешёнными (на момент решения их 0).
4. **Runtime**: все slug-lookup опций переведены с `.filter().first()` на
   `.get()` с явной обработкой: `DoesNotExist` → прежние коды
   (`missing_attribute` / `unknown_option`), `MultipleObjectsReturned` →
   новый громкий `option_slug_conflict` (`processing.py` validate/apply,
   `provenance.py`).
5. **Импорт**: `load_tool_types` получил preflight `_validate_option_slugs`
   — до транзакции отклоняет: slug с >1 distinct value в seed
   (`duplicate option slugs in seed`); >1 записи на slug в БД
   (`duplicate option slugs in DB`); расхождение slug→value с БД
   (`option slug conflicts with DB`).
6. **Инвариант seed**: slug обязан отображаться ровно в одно distinct
   value. Повтор пары (value, slug) в нескольких категориях **легален**
   (loader дедупит по value через `update_or_create`; существующие
   повторы `zaryadnye`, `svar-klemmy` — осознанные cross-category).
7. **Тесты**: repo-тест инварианта seed, preflight-тесты loader,
   strict-lookup тесты (mock MultipleObjectsReturned), guard-тесты
   миграции (no-op / idempotent / RuntimeError), DB-инвариант
   (IntegrityError на дубль; slug свободен между атрибутами; пустые
   разрешены).

## Последствия

**Плюсы:**

- `(attribute, slug)` уникален на уровне схемы — класс DEVIATION-2
  закрыт системно, независимо от пути записи (seed, админка, код);
- slug→option становится функцией: importer, runtime и фасеты резолвят
  однозначно и согласованно; 10 товаров id=16 получают собственный
  facet-URL `?tool_type=steplery-i-zaklepochniki`;
- нарушение инварианта — громкая ошибка (CommandError /
  `option_slug_conflict` / IntegrityError), а не молчаливый выбор
  «первой» записи;
- таксономическая информация сохранена полностью.

**Минусы / компромиссы:**

- URL фасета «Степлеры и заклёпочники» меняется
  (`?tool_type=steplery` → `?tool_type=steplery-i-zaklepochniki`) —
  осознанный SEO trade-off; старый slug однозначно ведёт на id=73
  (42 товара), что корректнее прежнего last-write-wins;
- pinned taxonomy export Phase 7A сохраняет исторический дубль (328
  rows / 327 unique) как артефакт своего снапшота — не регенерируется.

**Риски и ограничения:**

- `load_attributes.py` имеет тот же класс риска (slug из seed), но в его
  seed дублей нет (инвариант-SELECT Phase 7A.1); системная защита —
  констрейнт; отдельный preflight — follow-up при необходимости;
- дословные junk-дубли записей `mfi`/`shlifmashiny` в seed (одно value,
  одна категория) признаны seed hygiene, не DEVIATION-2 — отдельный
  cleanup, вне scope этой remediation;
- rollback: reverse-миграция (`migrate catalog 0026`) снимает констрейнт
  и возвращает slug `steplery` записи id=16; потерь данных нет (меняется
  одно поле одной строки).

**Блокировки:** Phase 7B разблокируется только после post-deploy
verification (инвариант-SELECT → 0 rows; facets smoke обоих slug) и
отдельного архитектурного решения.
