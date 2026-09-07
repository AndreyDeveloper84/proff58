# Промпт для агента --- VI-INT-05: ruleset expansion research

VI-INT-04A принимаю как **PASS**. Batch A доказал, что production-контур
масштабируется на новые товары: strict identity без false assignment, 23
безопасных PAV, 52 изображения, schema delta 0, existing data mutations
0 и полный rerun/no-op.

Но **Batch B на 40 сейчас НЕ запускаем**.

Причина --- G-3. Из актуального long-tail 121 текущая `vi-longtail`
карта покрывает только 36 товаров; после Batch A остаётся всего 16
формально in-scope, причём реально готовых strict-кандидатов без нового
сбора только 4. Запуск 40 сейчас в основном масштабировал бы сбор
изображений, а не полноценное enrichment характеристик.

Следующий этап:

# VI-INT-05 --- ruleset expansion research

Цель: не импортировать данные, а определить **минимальное безопасное
расширение `vi-longtail` map**, которое даст максимальный прирост
характеристик на оставшемся long-tail.

**Только read-only research. Никаких staging writes, PR/deploy или Batch
B.**

## 1. Зафиксировать baseline

Используй актуальный остаток после Batch A:

-   long-tail remaining = 101;
-   текущий map coverage remaining = 16;
-   существующий `vi-longtail` map;
-   ROI artifacts VI-INT-04A;
-   собранные карточки collector;
-   существующую canonical attribute schema.

Не считать все 101 автоматически пригодными для enrichment: отдельно
учитывать identity/source coverage.

## 2. Разложить G-3 на две независимые проблемы

Не смешивать:

### A. TOOL_TYPE_COVERAGE

Какие `tool_type` отсутствуют в `scope_tool_types`, хотя по ним уже есть
или реально можно получить source cards.

### B. ATTRIBUTE_MAPPING_COVERAGE

Какие source characteristic names на уже поддержанных/new candidate
tool_type можно безопасно связать с существующими canonical attributes.

Отчёт должен показать вклад каждой проблемы отдельно.

## 3. Tool-type ROI

Для каждого оставшегося `tool_type` построить таблицу:

`tool_type | products_remaining | collected_strict | collector_not_found | source_chars | safe_existing_attr_candidates | image_only_if_unmapped | estimated_safe_PAV | confidence`

Отсортировать прежде всего по:

1.  числу товаров;
2.  числу уже доступных strict source cards;
3.  ожидаемому числу безопасных PAV;
4.  стоимости дополнительного collector run.

Нужен ответ, какие tool_type дают максимальный прирост при минимальном
расширении ruleset.

Не добавлять тип только потому, что он существует в long-tail.

## 4. Attribute mapping audit

Использовать `04-roi-unmapped` как исходную очередь, но перепроверить
значения в контексте конкретных tool_type.

Для каждого high-ROI source field:

`source_name | tool_types | products | values | units | examples | proposed canonical attr | verdict | reason`

Verdict только из:

-   `SAFE_MAP_EXISTING`
-   `SAFE_SELECT_EXTENSION`
-   `NEEDS_UNIT_RESEARCH`
-   `SEMANTICALLY_AMBIGUOUS`
-   `NEW_ATTRIBUTE_CANDIDATE`
-   `DROP`
-   `INSUFFICIENT_EVIDENCE`

Не превращать similarity имени в доказательство mapping.

## 5. Отдельно разобрать «Материал»

Это самый очевидный ROI-кандидат: dropped_select `Материал → material`
затрагивает 10 товаров.

Но нельзя просто добавить все встретившиеся строки в `AttributeOption`.

Провести read-only аудит:

-   какие canonical `material` options существуют;
-   какие варианты пришли от источника;
-   частоты;
-   какие являются только орфографическими/форматными вариантами одного
    материала;
-   какие действительно новые материалы;
-   где `Материал` относится к изделию;
-   где это материал рабочей части/рукоятки/корпуса и поэтому generic
    `material` семантически неверен.

Особенно проверить:

-   `Cr-V`;
-   `CrV`;
-   пластик;
-   полипропилен.

На выходе дать proposal, но ничего не создавать.

Если `Cr-V` и `CrV` являются одной доказанной сущностью относительно
существующей canonical option --- предложить normalization alias, а не
две новые options.

## 6. «Тип»

Поле `Тип` встречается у 19 товаров --- это высокий frequency, но
название семантически опасное.

Не создавать generic attribute `type`.

Разложить значения по tool_type и определить, означает ли `Тип`:

-   конструкцию;
-   вид инструмента;
-   тип оснастки;
-   форму;
-   механизм;
-   другое.

Mapping разрешать только локально по конкретному tool_type, если
семантика однозначна.

Если одно и то же source name означает разные вещи у разных tool_type
--- это нормальная причина иметь разные per-tool_type mappings.

## 7. «Длина»

`Длина` встречается у 10 товаров и уже исторически была unit-trap.

Поэтому никакого возврата global DIRECT mapping.

Разобрать:

`tool_type → source value → source unit → canonical target → required conversion`

Разделить:

-   безопасное mm;
-   безопасное cm→mm;
-   m;
-   длину кабеля/ленты/изделия;
-   значения, где canonical `length` семантически не тот параметр.

Предложение unit conversion допустимо только как research result.
Реализацию сейчас не делать.

## 8. Остальные high-frequency поля

Обязательно разобрать минимум:

-   `Диэлектрическое покрытие` --- 8;
-   `Класс товара` --- 8;
-   `Трещотка` --- 6;
-   `Тип инструмента`;
-   `Тип патрона`;
-   `Тип хвостовика`;
-   `Квадрат`;
-   `Объем`.

Для `Тип инструмента → tool_type` отдельно проверить: `tool_type`
является taxonomy axis, а не обычным PAV. Не допускать скрытого
изменения taxonomy через characteristics importer.

Если source field лишь подтверждает существующий tool_type --- это может
быть validation signal, но не обязательно импортируемая характеристика.

## 9. Не ограничиваться уже собранными 53 карточками

Сначала определить, хватает ли существующих collector artifacts для
уверенного решения.

Если для top-ROI tool_type доказательств недостаточно, подготовить
**маленький targeted collector research pool**, а не новый массовый
long-tail crawl.

Collector разрешён только для research и только по существующему
безопасному контракту.

Не собирать автоматически все оставшиеся 101.

## 10. Сформировать Ruleset Expansion Pack

На выходе нужен не код, а детерминированный proposal.

### Pack A --- SAFE NOW

Только mappings/option-normalizations/tool_type scope additions, для
которых доказательства достаточны.

Для каждого изменения:

-   точное изменение map;
-   затрагиваемые tool_type;
-   затрагиваемые products;
-   ожидаемый safe PAV gain;
-   regression fixture;
-   negative fixture;
-   риск.

### Pack B --- RESEARCH LATER

Поля с потенциальным ROI, но недостаточной семантической/unit
уверенностью.

### Pack C --- REJECT

Поля, которые не должны попадать в canonical schema/map.

## 11. Посчитать эффект до реализации

Для Pack A сделать offline simulation/read-only replay.

Показать:

### CURRENT

-   remaining products = 101;
-   map-covered products;
-   strict collected products;
-   estimated safe PAV.

### AFTER PACK A

-   map-covered products;
-   strict collected products;
-   estimated safe PAV;
-   additional products meaningfully enriched;
-   additional PAV;
-   dropped reduction;
-   unmapped reduction.

Нужна оценка не только количества mappings, а реального прироста
товаров.

## 12. Подготовить решение по следующему rollout

После simulation предложить один из вариантов:

### R1

Сначала реализовать Pack A → PR → CI → deploy → затем Batch B.

### R2

Pack A имеет слишком маленький ROI → не расширять ruleset сейчас,
продолжать image-first rollout.

### R3

Нужен ещё targeted collector research до решения.

Не выбирать вариант заранее --- вывод должен следовать из цифр.

## Запреты

В VI-INT-05:

-   staging writes --- NO;
-   изменение `attribute_rules.json`/production map --- NO;
-   Attribute creation --- NO;
-   AttributeOption creation --- NO;
-   taxonomy/tool_type writes --- NO;
-   Batch B --- NO;
-   Batch C --- NO;
-   массовый collector 101 --- NO;
-   unit-conversion implementation --- NO;
-   второй importer --- NO;
-   ImagePipeline changes --- NO;
-   PR/push/deploy --- NO.

## Итоговый отчёт

Вернуть:

`VI-INT-05: RESEARCH_COMPLETE / NEEDS_MORE_EVIDENCE / BLOCKED`

и разделы:

1.  current remaining scope;
2.  tool_type coverage gap;
3.  tool_type ROI ranking;
4.  attribute mapping ROI ranking;
5.  material audit;
6.  `Тип` semantic audit;
7.  `Длина`/units audit;
8.  остальные high-frequency fields;
9.  targeted collector research, если понадобился;
10. Pack A SAFE NOW;
11. Pack B RESEARCH LATER;
12. Pack C REJECT;
13. offline simulation current vs Pack A;
14. ожидаемый PAV/product gain;
15. recommendation R1/R2/R3;
16. точный proposed scope следующего implementation track.

После отчёта остановиться. **Ничего не применять и Batch B не
запускать.**
