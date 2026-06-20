# Обогащение каталога — дорожная карта (что дальше)

История выполненного — в [`catalog_enrichment_history.md`](catalog_enrichment_history.md).

## Очередь работ
**#96 характеристики → #25 фасетные фильтры → #60 pricing-контракт → AI**
(рекомендации #73 / enrich-adapter #62). AI — последним: ему нужно опираться на данные
(характеристики), а не на названия.

---

## #96 — Фаза B: характеристики товаров (в работе)

Извлечение характеристик из названий 1С в EAV (`ProductAttributeValue`), отладка каркаса
на «Дрелях и шуруповёртах», затем тираж словарём на остальные типы.

**Реализовано (фундамент Фазы A — PR #99, надстройка Фазы B — этот PR):**
- `apps/catalog/attribute_extract.py` (#99) — движок (зеркало `tool_type.py`): number (regex),
  boolean (негативные паттерны ДО позитивных), select (по ключевым словам). Канон, один движок.
- `data/attribute_rules.json` (#99 + правки) — словарь «Дрели и шуруповёрты»: `power_source`,
  `voltage`, `torque`, `motor_type`, `battery_included`; `battery_capacity` помечен `is_ai_feature`
  (не фильтр). Приоритет источников — карта `source_priority` прямо в словаре.
- Модель: `ProductAttributeValue.source` (choices `Source` в `models.py`) и `confidence`
  (SmallInteger 0–100 с валидаторами, только аналитика), `Attribute.is_ai_feature`. Миграция
  `0004` (+ data-миграция: существующим PAV проставлен `source=manual`). Без `filter_kind`.
- Команды: `load_attributes` (идемпотентно, обновляет только безопасные поля), `enrich_attributes`
  (bulk #93 + провенанс, перезапись по приоритету источника), `attribute_coverage` (#99,
  read-only отчёт покрытия ДО enrichment). Добавлены в `bootstrap_catalog`.
- Backend range-фильтров для `voltage`/`torque`: `?<slug>_min/_max` → по `value_decimal`,
  невалидное значение → HTTP 400 (вид фильтра выводим из типа атрибута; UI-ползунки позже).
- ARCHITECTURE §4.7: правило «EAV-истина + attrs_cache как read-model».

**Процесс настройки нового tool_type:**
1. `attribute_coverage --tool-type <slug>` — посмотреть, что реально извлекается;
2. добавить блок в `attribute_rules.json` (что фильтр, что SEO-фасет, что `is_ai_feature`);
3. `load_attributes` → `enrich_attributes`; проверить `ImportRun.stats` и витрину.

**Что осознанно отложено:** UI диапазонных ползунков; добор низкопокрытых атрибутов через LLM
(метятся `is_ai_feature`, реализуется в #62).

---

## #25 — фасетные фильтры (следующее)
Поверх `attrs_cache` (read-model) и `services.build_facets`: drill-down счётчики, посадочные
страницы SEO-фасетов. Числовые — диапазоны (backend уже готов в #96).

## #60 — pricing-контракт
Розница/опт/договорные цены через `pricing.services` (ADR §4.1).

## AI (#73 рекомендации, #62 enrich-adapter)
Адаптерный контракт `ai.services` (ADR §4.5). Включаем, когда характеристики наполнены:
LLM добирает то, что не берётся regex/словарём (атрибуты с `is_ai_feature`).
