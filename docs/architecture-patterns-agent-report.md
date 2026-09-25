# Отчет для агента: паттерны архитектуры и требуемые правки

Дата ревью: 2026-06-20

Роль ревью: Principal Software Architect / Django Tech Lead.

Фокус ревью:

- гибкость архитектуры;
- паттерны проектирования;
- анти-паттерны;
- SOLID / DRY;
- Django / DRF практики;
- безопасность интеграций;
- Postgres / производительность;
- тестируемость и план правок.

## 1. Краткий вердикт

Кодовая база уже имеет хорошую архитектурную основу: выделены домены `catalog`, `pricing`, `sync_1c`, `core`, есть сервисный слой, use-case слой для 1С, DTO-нормализация входных данных, read-model для фасетов и единый реестр доменных событий.

Главный риск гибкости сейчас - смешение домена цен и интеграционного слоя 1С. `apps.pricing` читает `PriceRecord` из `apps.sync_1c`, а каталог в админке также напрямую знает о модели интеграции. Это нарушает Dependency Inversion и будет мешать развитию заказов, B2B-цен, промо, резервов и будущих источников цен.

Второй риск - постепенное разрастание `apps/catalog/services.py` в слишком широкий сервисный модуль: там уже смешаны `attrs_cache`, фасеты, дерево категорий, product queries и tool_type facets.

Третий риск - частичное дублирование правил сборки `attrs_cache` между обычным сервисом и batch-командами обогащения.

## 2. Карта текущих доменов

### `apps.catalog`

Ответственность:

- товарный каталог;
- категории;
- EAV-характеристики;
- фасетные фильтры;
- витринные API;
- админская модерация и публикация товаров;
- read-model `Product.attrs_cache`.

Хороший текущий паттерн:

- EAV как источник истины;
- `attrs_cache` как read-model для быстрых фильтров;
- `GinIndex` по JSONB для ускорения containment-запросов;
- технические сигналы только для пересборки кеша.

### `apps.pricing`

Ответственность:

- единый публичный контракт получения цены;
- выбор розницы / опта;
- возвращение стабильного `PriceResult`.

Проблема:

- домен цен зависит от `apps.sync_1c.models.PriceRecord`;
- фактически источник опта лежит в интеграционном приложении, а не в pricing-домене.

### `apps.sync_1c`

Ответственность:

- прием данных 1С;
- нормализация;
- staging;
- matching;
- запись товаров;
- обновление цен и остатков;
- API для 1С;
- фоновые задачи.

Хороший текущий паттерн:

- `use_cases.py` как application service;
- `normalizers.Item` как DTO;
- `product_writer.py` отделен от staging/API;
- partial failure: сбой строки не валит весь прогон;
- `update_products` реализует update-only режим;
- snapshot поддерживает keyset pagination.

### `apps.core`

Ответственность:

- общие события;
- healthcheck;
- feature flags.

Хороший текущий паттерн:

- доменные события объявлены централизованно;
- payload событий - id/снапшоты, а не живые ORM-объекты;
- отправка событий через `transaction.on_commit`.

## 3. Найденные паттерны проектирования

### Service Layer

Где есть:

- `apps.pricing.services.price_for`;
- `apps.catalog.services.build_facets`;
- `apps.catalog.services.products_in`;
- `apps.sync_1c.use_cases`;
- `apps.sync_1c.product_writer`;
- `apps.sync_1c.pricing`;
- `apps.sync_1c.stock`.

Оценка:

Паттерн выбран правильно. Бизнес-логика в основном вынесена из views и serializers.

Риск:

`catalog.services` становится слишком широким и начинает превращаться в "god service".

### Application Service / Use Case Layer

Где есть:

- `apps.sync_1c.use_cases.process_row`;
- `apps.sync_1c.use_cases.import_products`;
- `apps.sync_1c.use_cases.update_products`;
- `apps.sync_1c.use_cases.update_prices`;
- `apps.sync_1c.use_cases.update_stocks`.

Оценка:

Это одна из самых сильных частей текущей архитектуры. Оркестрация импорта вынесена в отдельный слой и не размазана по API, задачам Celery и моделям.

### DTO / Data Transfer Object

Где есть:

- `apps.sync_1c.normalizers.Item`.

Оценка:

Хорошее решение. Внутренние слои работают не с сырыми строками 1С, а со стабильным объектом.

Польза:

- проще тестировать;
- проще добавлять новые форматы колонок;
- меньше утечек транспортного формата в домен.

### Anti-Corruption Layer

Где есть:

- `apps.sync_1c.normalizers`;
- `apps.sync_1c.parsers`;
- `apps.sync_1c.matching`.

Оценка:

Интеграция 1С частично изолирована от каталога. Это хорошо. Но `PriceRecord` пока лежит внутри `sync_1c`, из-за чего слой 1С все еще протекает наружу.

### Read Model / CQRS-like pattern

Где есть:

- `ProductAttributeValue` как source of truth;
- `Product.attrs_cache` как read-model;
- `catalog.services.rebuild_attrs_cache`;
- фасеты поверх `attrs_cache`.

Оценка:

Очень подходящий паттерн для каталога с фасетами. EAV удобно хранит гибкие характеристики, а JSONB read-model ускоряет чтение.

Риск:

Правила формирования `attrs_cache` должны быть в одном месте. Сейчас есть дублирование в batch-командах.

### Observer / Domain Events

Где есть:

- `apps.core.events`;
- `product_created`;
- `product_updated`;
- `price_changed`;
- `transaction.on_commit`.

Оценка:

Паттерн применен правильно. Особенно важно, что доменные события не завязаны на `post_save` моделей.

Правило на будущее:

Критичные бизнес-события заказов, оплат и резервов не должны жить в Django model signals. Их надо эмитить из use-case слоя.

### Repository-like Query Helpers

Где есть:

- `visible_products`;
- `filtered_products`;
- `products_in`;
- query helpers в сервисах каталога.

Оценка:

Это полезный шаг к отделению запросов от API. Следующий этап - выделить отдельный модуль `catalog/queries.py`.

### Strategy / Rules

Где есть:

- `CategoryMappingRule`;
- `AttributeRules`;
- `tool_type` правила;
- `COLUMN_ALIASES` в normalizers.

Оценка:

Хорошая расширяемость без переписывания use-case слоя. Это соответствует Open/Closed Principle.

## 4. Найденные анти-паттерны и риски

### A1. Integration model leaks into domain

Серьезность: Major.

Проблема:

`apps.pricing.services` импортирует `PriceRecord` из `apps.sync_1c.models`. Это делает pricing зависимым от интеграционного слоя.

Почему это плохо:

- `pricing` должен быть доменом, а `sync_1c` - адаптером;
- будущие источники цен будут вынуждены зависеть от 1С-модели;
- заказы и корзина начнут подтягивать интеграционные детали;
- сложнее добавить промо, контрактные цены, прайс-листы, B2B tiers.

Целевое состояние:

- `PriceRecord` переезжает в `apps.pricing.models`;
- `sync_1c` пишет цены через pricing API/service;
- каталог и заказы читают цены только через `apps.pricing.services`;
- `sync_1c` не является владельцем цены, он только источник обновления.

### A2. Catalog services becoming god module

Серьезность: Minor -> Major при росте.

Проблема:

`apps/catalog/services.py` содержит несколько разных ответственностей:

- сборка `attrs_cache`;
- фасеты;
- дерево категорий;
- запросы товаров в категории;
- range filters;
- tool_type facets.

Почему это плохо:

- модуль станет трудно читать;
- сложнее тестировать отдельные контракты;
- изменения фасетов могут случайно затронуть дерево категорий;
- сложнее новым агентам быстро понять границы.

Целевое состояние:

- `catalog/read_models.py` - `attrs_cache`;
- `catalog/facets.py` - фасеты и парсинг фильтров;
- `catalog/queries.py` - product/category query helpers;
- `catalog/category_tree.py` - дерево категорий и кеш;
- `catalog/services.py` остается фасадом или исчезает постепенно.

### A3. Duplicated attrs_cache serialization

Серьезность: Minor.

Проблема:

Логика JSON-safe значения есть в `catalog.services.attr_value_to_json`, но batch-команда `enrich_attributes` имеет похожую `_cache_value`.

Почему это плохо:

- формат `attrs_cache` может разъехаться;
- фасеты будут зависеть от того, каким путем обновляли атрибут;
- баги будут сложнее ловиться.

Целевое состояние:

- один общий модуль `catalog/attribute_values.py` или `catalog/read_models.py`;
- функции:
  - `attr_value_to_json(pav)`;
  - `extracted_value_to_json(kind, value, option)`;
  - или общий value object/converter.

### A4. Pricing N+1 for B2B listings

Серьезность: Major для B2B витрины.

Проблема:

`ProductListSerializer.to_representation` вызывает `price_for(instance, user)` на каждый товар. Для B2B это может делать запрос в `PriceRecord` на каждый продукт.

Целевое состояние:

- добавить bulk price resolver;
- view получает список товаров;
- одним запросом подтягиваются текущие оптовые цены;
- serializer берет готовые результаты из context.

Вариант API:

```python
prices = price_map_for_products(products, user=request.user)
serializer = ProductListSerializer(products, many=True, context={"price_map": prices})
```

### A5. Deprecated importer can preserve old coupling

Серьезность: Minor.

Проблема:

`apps.sync_1c.importer` оставлен как deprecated compatibility layer.

Почему это риск:

- новый код может продолжить импортировать старый shim;
- архитектура фактически будет иметь два публичных входа.

Целевое состояние:

- добавить архитектурный тест, запрещающий новые импорты `apps.sync_1c.importer`;
- оставить только старые тесты совместимости;
- назначить срок удаления.

### A6. Signals are acceptable but must stay technical

Серьезность: Watch.

Проблема:

`catalog.signals` сейчас обслуживает только `attrs_cache` и кеш дерева категорий. Это нормально. Но Django signals легко превращаются в скрытый бизнес-flow.

Правило:

- технический кеш - можно;
- бизнес-события заказов/цен/резервов - только из use-case слоя через `core.events`.

## 5. SOLID-анализ

### Single Responsibility Principle

Хорошо:

- `normalizers.py` отвечает за нормализацию;
- `product_writer.py` отвечает за запись Product;
- `use_cases.py` отвечает за оркестрацию;
- `permissions.py` отвечает за проверку ключа 1С.

Слабые места:

- `catalog.services.py` имеет слишком много ответственностей;
- `catalog.admin.py` содержит и UI-логику, и pricing queries, и event emission.

### Open/Closed Principle

Хорошо:

- `COLUMN_ALIASES` расширяет входные форматы без изменения use-case слоя;
- правила категорий и атрибутов расширяются данными;
- feature flags заложены в архитектуру.

Слабые места:

- pricing пока не готов к новым источникам цен без изменения кода, потому что завязан на `sync_1c.PriceRecord`.

### Liskov Substitution Principle

Сейчас почти не применимо: мало наследования и полиморфных иерархий. Это нормально для Django-проекта.

### Interface Segregation Principle

Хорошо:

- API 1С разделен на products/prices/stocks/snapshot;
- use-case функции достаточно явные.

Слабые места:

- `catalog.services` как интерфейс слишком широкий.

### Dependency Inversion Principle

Главное нарушение:

- `apps.pricing` зависит от `apps.sync_1c`.

Цель:

- домены зависят от абстрактных сервисных контрактов;
- интеграции зависят от доменов, а не наоборот.

## 6. DRY-анализ

### Хорошо

- единый `price_for` как публичный контракт цены;
- единая нормализация 1С через `Item`;
- единый event registry в `core.events`;
- фасетный API использует `build_facets`, а не дублирует подсчет во view.

### Требует правки

- `attrs_cache` serialization повторяется в обычном и batch-пути;
- wholesale price query повторяется в `pricing.services` и `catalog.admin`;
- часть query-логики каталога может начать дублироваться между API и storefront.

## 7. Security review

### Что хорошо

- 1С API закрыт permission-классом `HasOneCApiKey`;
- если `ONEC_API_KEY` не задан, доступ закрыт;
- сравнение ключа идет через `constant_time_compare`;
- публичный каталог read-only;
- входные данные 1С проходят через DRF serializers;
- batch import уходит в фон, тяжелые запросы не держат HTTP.

### Риски

#### S1. Shared secret без дополнительных ограничений

Серьезность: Major для production.

Текущий `X-Api-Key` приемлем для 1С 7.7, но для production стоит добавить:

- IP allowlist на Nginx;
- rate limit на `/api/1c/*`;
- аудит неуспешных попыток;
- регламент ротации ключа;
- отдельные ключи для dev/stage/prod.

#### S2. `sync_status` возвращает `error_details`

Серьезность: Minor / Watch.

`error_details` доступны только по API key, но туда могут попасть детали ошибок строк. Нужно следить, чтобы там не было секретов, SQL traceback, персональных данных клиентов.

#### S3. Настройки по умолчанию

`SECRET_KEY = insecure-change-me-in-prod` безопасен только если production строго задает env. Для deploy checklist надо явно проверять `DJANGO_SECRET_KEY`.

## 8. Postgres / производительность

### Что хорошо

- JSONB `attrs_cache` имеет GIN index;
- фасеты считаются через PostgreSQL aggregation, а не через Python по всей выборке;
- batch-команды используют `bulk_create` / `bulk_update`;
- snapshot 1С поддерживает keyset pagination;
- `select_related` / `prefetch_related` применены в API каталога;
- для админки использованы subquery counts вместо опасного fan-out `COUNT(DISTINCT)`.

### Риски

#### P1. B2B price N+1

См. A4.

#### P2. PriceRecord current invariant

Проверить, что уникальность текущей цены действительно защищена partial unique constraint:

- одна актуальная цена на `(code_1c, price_type, currency)`;
- желательно с условием `is_current=True`.

Если constraint уже есть - добавить тест на гонку/дубликат. Если нет - добавить миграцию.

#### P3. `rebuild_attrs_cache` maintenance command

Команда `rebuild_attrs_cache` идет по товарам и вызывает save на каждый товар. Для ручной maintenance-команды это приемлемо, но на большом каталоге лучше сделать batch-вариант с prefetch и bulk_update.

## 9. API design review

### Что хорошо

- 1С endpoints имеют явные контракты: products/import, products/update, prices/update, stocks/update, snapshot;
- update-only режим отделен от import;
- snapshot имеет keyset pagination;
- фасетный endpoint валидирует лимиты и типы фильтров;
- ошибки валидации возвращаются 400.

### Что стоит улучшить

- унифицировать формат ошибок API: сейчас где-то `{"detail": ...}`, где-то serializer errors;
- для публичного каталога проверить pagination defaults и максимальный limit;
- для 1С API добавить OpenAPI/markdown contract как источник истины;
- для 501 order stubs явно держать задачу на реализацию state machine заказов.

## 10. Тестовое покрытие

### Уже хорошо покрыто

- фасеты;
- attrs_cache;
- events;
- 1С API;
- snapshot keyset;
- skip unchanged price;
- admin pricing;
- enrichment rerun.

### Нужные тесты

#### T1. Architecture import boundaries

Цель:

- запретить `apps.pricing` импортировать `apps.sync_1c`;
- запретить `apps.catalog.api` импортироваться из services;
- запретить новый код на `apps.sync_1c.importer`.

Пример:

```python
def test_pricing_does_not_import_sync_1c():
    import apps.pricing.services as module
    src = Path(module.__file__).read_text(encoding="utf-8")
    assert "apps.sync_1c" not in src
```

После рефакторинга тест должен стать обязательным.

#### T2. Bulk price resolver query count

Цель:

- B2B listing не делает N запросов к ценам.

Проверка:

- создать 20 товаров;
- создать оптовые цены;
- запросить list endpoint B2B-пользователем;
- assert max queries.

#### T3. Security tests for 1C

Нужно проверить:

- без ключа - 403;
- неверный ключ - 403;
- пустой `ONEC_API_KEY` на сервере закрывает доступ;
- large payload ограничивается `ONEC_MAX_ITEMS`;
- invalid payload не создает SyncLog/задачу.

Часть этого уже есть, но перед production стоит пересмотреть весь набор.

#### T4. PriceRecord invariant

Нужно проверить:

- повтор такой же цены не создает новую запись;
- изменение цены создает новую current-запись и снимает старую;
- нельзя иметь две `is_current=True` на один `(code_1c, price_type, currency)`.

#### T5. attrs_cache consistency

Нужно проверить:

- обычное сохранение PAV и batch enrichment дают одинаковый формат `attrs_cache`;
- decimal/integer/boolean/select сериализуются одинаково.

## 11. Требуемые правки по приоритетам

### P0 - перед заказами и оплатами

#### 1. Развязать `pricing` и `sync_1c`

Тип: architecture / refactoring.

Цель:

- `apps.pricing` не импортирует `apps.sync_1c`;
- `PriceRecord` принадлежит pricing-домену или скрыт за pricing repository;
- `sync_1c` только пишет цены через публичный сервис.

Варианты:

1. Перенести `PriceRecord` в `apps.pricing.models`.
2. Оставить таблицу временно, но добавить `apps.pricing.repositories.current_price_for_code` и запретить прямой импорт из catalog/pricing.

Предпочтительный вариант:

Перенос модели в `apps.pricing.models` с аккуратной миграцией/переименованием таблицы позже. Если быстро и безопасно - начать с repository facade, потом перенести модель.

Acceptance criteria:

- `apps.pricing` не содержит `from apps.sync_1c`;
- `catalog.admin` не импортирует `PriceRecord` из `sync_1c`;
- тесты pricing и sync_1c проходят;
- добавлен architecture test на запрет обратной зависимости.

#### 2. Bulk price resolver для каталога

Тип: performance / API contract.

Цель:

- убрать N+1 для B2B-цен в листинге товаров.

Acceptance criteria:

- `ProductListView` подготавливает price map;
- serializer не ходит в БД за ценой на каждый товар;
- есть query-count test;
- B2C поведение не изменилось.

### P1 - ближайший рефакторинг каталога

#### 3. Разделить `catalog.services.py`

Тип: refactoring.

Без изменения поведения.

Предлагаемый план:

1. Создать `catalog/read_models.py` и перенести туда `attr_value_to_json`, `rebuild_attrs_cache`.
2. Создать `catalog/facets.py` и перенести туда `FacetError`, `build_facets`, helpers.
3. Создать `catalog/category_tree.py` и перенести cache tree helpers.
4. Создать `catalog/queries.py` и перенести `products_in`, `category_counts`, `tool_type_facets`, `range_filter_attributes`.
5. В `catalog/services.py` временно оставить re-export для обратной совместимости.

Acceptance criteria:

- публичный API не изменился;
- все старые импорты работают;
- тесты фасетов и attrs_cache проходят;
- новый код импортирует из специализированных модулей.

#### 4. Единый converter для `attrs_cache`

Тип: DRY / data consistency.

Цель:

- один источник правил сериализации значений характеристик.

Acceptance criteria:

- `rebuild_attrs_cache` и `enrich_attributes` используют общий converter;
- добавлен тест на одинаковый формат batch/normal paths;
- фасеты не меняют контракт ответа.

### P2 - безопасность и эксплуатация

#### 5. Усилить 1С API

Тип: security / devops.

Правки:

- rate limit на `/api/1c/*`;
- IP allowlist на dev/prod, если IP 1С стабилен;
- отдельные ключи dev/prod;
- логировать неуспешные попытки без раскрытия ключа;
- документировать ротацию ключа.

Acceptance criteria:

- Nginx или DRF throttling ограничивает частоту;
- есть docs/runbook по ключам;
- тесты permission проходят.

#### 6. Привести API ошибки к единому формату

Тип: API design.

Вариант:

```json
{
  "error": {
    "code": "validation_error",
    "message": "...",
    "details": {}
  }
}
```

Для внутреннего 1С API можно оставить DRF serializer errors, если это уже согласовано с 1Сником. Но надо явно зафиксировать контракт.

### P3 - качество и поддержка

#### 7. Deprecated importer cleanup

Тип: maintainability.

Правки:

- добавить issue/removal date;
- добавить тест/grep guard, что новый production code не импортирует `sync_1c.importer`;
- постепенно перевести оставшиеся импорты на `sync_1c.use_cases`.

#### 8. Batch rebuild attrs_cache

Тип: performance.

Правки:

- оптимизировать `rebuild_attrs_cache` command под большие каталоги;
- prefetch PAV;
- bulk_update Product.attrs_cache.

## 12. Рекомендуемый порядок работ для агента

### Этап 1. Зафиксировать архитектурные границы тестами

Сначала добавить characterization/architecture tests, чтобы будущий рефакторинг не уронил поведение.

Команды проверки:

```bash
uv run pytest apps/catalog/test_facets.py apps/catalog/test_attrs_cache.py apps/pricing/tests.py apps/sync_1c/test_api.py -q
python manage.py check
python manage.py makemigrations --check --dry-run
```

### Этап 2. Развязать pricing от sync_1c

Минимальный безопасный путь:

1. Создать `apps/pricing/repositories.py`.
2. Перенести туда чтение текущей цены.
3. `pricing.services` использует repository.
4. `catalog.admin` использует pricing helper/repository, а не `sync_1c.models`.
5. Добавить architecture test.

Полный путь:

1. Перенести модель `PriceRecord` в `apps.pricing.models`.
2. Обновить импорты.
3. Миграции сделать без потери данных.
4. `sync_1c` пишет через `pricing.services`.

### Этап 3. Bulk pricing

1. Реализовать `price_map_for_products(products, user=None)`.
2. Для B2B одним запросом получить current wholesale prices.
3. В serializer context передавать map.
4. Добавить query-count test.

### Этап 4. Разделить catalog services

Делать только после зеленых тестов. Сначала mechanical move + re-export, затем обновить импорты.

### Этап 5. Усилить security/devops для 1С

Делать перед production или перед реальным подключением 1С.

## 13. Definition of Done для всего блока

Считаем блок закрытым, когда:

- `apps.pricing` не зависит от `apps.sync_1c`;
- B2B listing не имеет N+1 по ценам;
- `catalog.services.py` разделен или имеет план разделения с тестами;
- `attrs_cache` собирается единым converter;
- 1С API имеет rate limit/IP policy/runbook;
- architecture tests защищают основные границы;
- все релевантные тесты проходят;
- документация `ARCHITECTURE.md` и ADR-0006 обновлены под фактическое состояние.

## 14. Короткая памятка агенту

Не делать:

- не тащить `sync_1c.models` в `pricing`, `catalog`, `orders`;
- не добавлять бизнес-логику в Django signals;
- не обходить `price_for` прямым чтением `Product.price` в пользовательских сценариях;
- не менять API-контракты без тестов и документации;
- не смешивать крупный рефакторинг с функциональными изменениями.

Делать:

- держать интеграции сверху, домены снизу;
- use-case слой для сложных сценариев;
- serializers для входной валидации;
- services/repositories для доменной логики и запросов;
- `transaction.atomic` и `on_commit` для state changes + events;
- query-count tests для списков;
- architecture tests для границ.
