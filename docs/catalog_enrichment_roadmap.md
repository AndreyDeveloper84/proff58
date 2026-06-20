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

**Реализовано:**
- `apps/catalog/source_priority.py` — `Source` + ранги + `can_overwrite` (без magic numbers).
- `apps/catalog/attribute_extract.py` — движок (зеркало `tool_type.py`): number (regex),
  boolean (негативные паттерны ДО позитивных), select (по ключевым словам).
- `data/attribute_rules.json` — словарь для «Дрели и шуруповёрты»: `power_source`, `voltage`,
  `torque`, `battery_included`, `motor_type` с богатыми вариантами написания.
- Модель: `ProductAttributeValue.source/confidence` (SmallInteger 0–100 с валидаторами),
  `Attribute.is_ai_feature`, `CategoryAttribute.filter_kind` (select/range). Миграция `0004`.
- Команды: `load_attributes`, `enrich_attributes` (bulk + провенанс), `attribute_coverage`
  (read-only отчёт покрытия ДО enrichment). Добавлены в `bootstrap_catalog`.
- Backend range-фильтров: `?voltage_min=&voltage_max=` → по `value_decimal` (UI-ползунки позже).
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
