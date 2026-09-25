# EPIC-ENRICH: дизайн обогащения карточек товара (capability `enrich`)

**Дата:** 2026-06-26
**Ветка:** `feature/epic-enrich` (от `dev`)
**Статус:** дизайн утверждён, готов к плану реализации
**Связанные документы:** `docs/ARCHITECTURE.md`, `docs/ARCHITECTURE-AI.md`,
`docs/catalog_enrichment_history.md`, `docs/catalog_enrichment_roadmap.md`

---

## 1. Контекст и решение по курсу

После импорта из 1С карточка товара имеет только `original_name` («мусорное» имя
вида `Перфоратор HR2470 Makita 780Вт;SDS-plus;2.8Дж`), пустые `description` /
`short_description`, нет фото и характеристик.

Существовало внешнее ТЗ (`D:\Проекты\…\epic-enrich.md`) с подходом «4 источника»:
выгрузки поставщиков → парсинг сайтов брендов → Яндекс.Маркет API → AI-генерация,
с моделью `EnrichLog` и `EnrichOrchestrator`. Этот подход **противоречит уже
принятой и частично реализованной архитектуре проекта** (`ARCHITECTURE-AI.md`:
deterministic-first, AI за портом, `AiCallLog`; `catalog_enrichment_*`:
извлечение характеристик словарём, precision ≥ 98%, без скрейпинга).

**Принятое решение (подтверждено заказчиком): идём по архитектуре проекта.**
Скрейперы брендов, Яндекс.Маркет API, `VendorFeed`, `EnrichOrchestrator` (4
источника) и `EnrichLog` **выпадают** из эпика — это отдельное решение под ADR,
когда появятся ключи/выгрузки.

### Решения по параметрам итерации
- **LLM:** только dummy-провайдер сейчас. Порт реальный, claude-провайдер —
  каркас, активируется при `ANTHROPIC_API_KEY`; живые вызовы — следующая итерация.
- **ImagePipeline:** минимальная инфраструктура под ручную загрузку URL и будущие
  выгрузки. Enrich-поток фото не тянет (источника URL нет).
- **Объём:** полный `enrich` end-to-end (порт + провайдер + `AiCallLog` +
  guardrails + receivers + Celery + `services.enrich` + admin + CLI + тесты).
- **Ветка:** `feature/epic-enrich` от `dev`.
- **`product_writer`:** эмит `product_created` в импортёр **не добавляем**;
  1С-товары обогащаются батчем (CLI/Celery). Подписка на `product_created`
  остаётся для admin/API-создания товаров.

---

## 2. Границы и инварианты

- `enrich` — capability за `apps/ai/services.py`. `apps/ai` зависит от `catalog`
  только через публичные хелперы/FK; чтение товара — через каталог (как уже делает
  `recommend` через `apps.catalog.filters`). Прямые `Catalog.objects.filter(...)`
  из `apps/ai` запрещены (ADR — правило зависимостей).
- Весь AI-слой работает под фичефлагом `ai` (`apps.core.features.is_enabled("ai")`).
- **LLM — последнее средство и низший приоритет** (`source=llm`). Приоритет
  источников значений: `manual > import_1c > regex > keyword > llm`.
- **LLM никогда не источник истины для цены / остатка / статуса заказа.** Применение
  результата физически не может тронуть эти поля.
- **`content_locked=True` — абсолютная защита.** Проверка перед любой записью
  контента; при блокировке — тихий выход с записью в `AiCallLog`.
- Выход LLM — недоверенный ввод: валидируется guardrails перед применением; сбой
  AI = «тихо без обогащения», а не 500.

---

## 3. Модель данных

### 3.1 Расширение `Product` (одна миграция в `apps/catalog`)
`content_locked` уже существует — не трогаем. Добавляем:

| Поле | Тип | Назначение |
|---|---|---|
| `enrich_status` | CharField(choices), default `pending` | `pending/in_queue/done/moderation/failed` |
| `content_source` | CharField(choices), null/blank | провенанс **карточного** контента (name/description): `manual/import_1c/llm` |
| `content_confidence` | FloatField, null/blank | уверенность 0.0–1.0 по карточному контенту |

Провенанс **характеристик** уже живёт в `ProductAttributeValue.source` /
`confidence` — не дублируем.

### 3.2 `AiCallLog` (новая модель в `apps/ai/models.py`)
По `ARCHITECTURE-AI` §6 (заменяет `EnrichLog` из внешнего ТЗ):

`capability` (`enrich/recommend/assist`), `provider`, `model`, `input_ref`
(хеш/усечённый снапшот промпта), `output` (усечение/ссылка), `tokens_in`,
`tokens_out`, `cost`, `latency_ms`, `status` (`ok/fallback/error`), `entity_ref`
(напр. `product_id`), `created_at`. Пишется всегда — включая `fallback`/`error`.

---

## 4. Контракт `enrich()` и гибридный поток

```python
@dataclass(frozen=True)
class EnrichResult:
    name: str | None
    short_description: str | None
    description: str | None
    attributes: list[EnrichedAttr]   # slug, value, source="llm", confidence
    confidence: float
    source: str                      # "llm" | "fallback"

def enrich(*, product_id: int, force: bool = False) -> EnrichResult
```

Поток:
1. Загрузить товар через каталог-хелпер (не `objects` напрямую).
2. Если `content_locked` и не `force` → выход, `AiCallLog(status="fallback",
   reason="content_locked")`.
3. Собрать пробелы: пустые `is_ai_feature`-атрибуты (по словарю
   `attribute_extract.py` для tool_type товара) + пустые `description` /
   `short_description` / нормализованное `name`.
4. Собрать контекст: `original_name`, категория, бренд, уже извлечённые
   характеристики.
5. Вызвать порт → провайдер (dummy) → сырой выход.
6. guardrails: валидация схемы/типов; отбросить защищённые поля; вернуть
   `EnrichResult` либо деградировать.
7. Применить:
   - PAV для AI-атрибутов с `source=llm` — **только пробелы**, приоритет не
     затирает `manual/import_1c/regex/keyword`.
   - `description/short_description/name` — только если пусты (или при `force`).
   - `content_source="llm"`, `content_confidence`, `enrich_status` (`moderation`
     при `confidence < 0.7`, иначе `done`).
8. Всегда писать `AiCallLog`.

Идемпотентность: повторный `enrich` не плодит дублей за счёт правил провенанса.

---

## 5. Порт и провайдеры

```
apps/ai/
├── ports.py            # узкий интерфейс «вызвать модель»: вход (промпт/параметры)
│                       #   → выход (текст/структура, токены, латентность)
├── providers/
│   ├── __init__.py
│   ├── dummy.py        # детерминированная заглушка из original_name (сейчас + тесты)
│   └── claude.py       # каркас реального провайдера; активен при ANTHROPIC_API_KEY
```

Сервисы знают только порт. Выбор провайдера — по наличию ключа/настройке; по
умолчанию `dummy`. Смена провайдера = смена внутренности, контракт `services.py`
не меняется.

---

## 6. Guardrails (`apps/ai/guardrails.py`)

- **Схема/типы:** выход парсится в ожидаемую структуру (включая случай обёртки
  ```` ```json ````). Несоответствие → результат отбрасывается, деградация к тому,
  что дал детерминированный слой.
- **Защита полей:** применение результата не может тронуть цену/остаток/статус
  заказа; enrich пишет только EAV-атрибуты (`source=llm`) и карточный текст.
- **`content_locked`:** уважается.
- **Лимиты:** размер входа/выхода, бюджет токенов, жёсткий таймаут (runtime).

---

## 7. Runtime: receivers + Celery

- `apps/ai/receivers.py` — подписка на `product_created` (и `product_updated`):
  ставит `enrich_product_task` через `transaction.on_commit`. Подключение — в
  `AiConfig.ready()` **под флагом `ai`**. (Импортёр 1С эмит не добавляет —
  1С-товары идут батчем; подписка обслуживает admin/API-создание.)
- `apps/ai/tasks.py`:
  - `enrich_product_task(product_id, force=False)` — таймаут, ретраи с backoff,
    идемпотентность.
  - `batch_enrich_task(category_slug=None, limit=100, only_empty=True)` —
    приоритет `available_quantity > 0`, затем остальные.

---

## 8. Модерация (admin) и CLI

### 8.1 `apps/ai/admin.py`
- `AiCallLogAdmin` — list_display/filters по `capability`/`status`/`success`,
  `output` readonly.
- Очередь модерации — товары с `enrich_status="moderation"` (proxy/filtered admin)
  с действиями: approve (`done` + `content_locked=True`), reject (сброс карточного
  контента + назад в очередь).

### 8.2 `apps/ai/management/commands/`
- `enrich_product` — `--id/--article/--code-1c`, `--force`, `--verbose`
  (показать raw-выход). Для отладки одного товара.
- `enrich_catalog` — `--category SLUG/--all`, `--limit`, `--dry-run/--commit`,
  `--force`. Батч; приоритет `available_quantity > 0`.
- `enrich_report` — статусы (с числами и %), источники готовых, без описания,
  топ-10 брендов по числу необогащённых.

---

## 9. ImagePipeline (минимальная инфраструктура)

`apps/catalog/image_pipeline.py`:
```python
class ImagePipeline:
    MAX_SIZE = (1200, 1200)
    THUMB_SIZE = (400, 400)
    QUALITY = 85
    def process_url(self, product, url, is_main=False, source="manual") -> ProductImage | None
    def process_batch(self, product, urls: list[str]) -> list[ProductImage]
```
Скачать → валидировать (mime `image/*`, > 100×100, < 10 MB) → снять EXIF →
ресайз 1200 с сохранением пропорций → thumbnail 400 → WebP → `ProductImage`.
Идемпотентно по нормализованному URL/хешу. Уважает `content_locked`. При ошибке —
лог и `None`, не падает. **Вызывается вручную** (admin-действие / опц. команда);
enrich-поток её не дёргает.

---

## 10. Тесты (`pytest apps/ai/ apps/catalog/`)

- `content_locked=True` блокирует любую запись контента (unit).
- `enrich` на dummy-провайдере даёт валидный `EnrichResult` и пишет `AiCallLog`.
- Провенанс: `source=llm` не затирает `manual`/`import_1c`/`regex`/`keyword`.
- guardrails отбрасывает невалидный JSON (включая ```` ```json ````-обёртку) →
  деградация без исключения.
- `enrich_status="moderation"` при `confidence < 0.7`.
- `batch_enrich_task` приоритизирует `available_quantity > 0`.
- ImagePipeline: ресайз 1200 + thumb 400 + WebP, снятие EXIF, идемпотентность,
  отклонение не-изображений.
- Нет прямых `OtherApp.objects.filter()` из `apps/ai` (кроме FK через свои модели).

---

## 11. Порядок реализации и DoD

**Порядок (коммит после каждого шага):**
1. Миграция + поля `Product` (`enrich_status`, `content_source`,
   `content_confidence`).
2. `AiCallLog` (модель + admin).
3. `ports.py` + `providers/dummy.py` (+ каркас `claude.py`).
4. `guardrails.py`.
5. `services.enrich()` (гибрид: детерминированные пробелы + порт + применение).
6. `tasks.py` + `receivers.py` + `AiConfig.ready()` под флагом `ai`.
7. `admin.py` — `AiCallLog` + очередь модерации.
8. CLI: `enrich_product`, `enrich_catalog`, `enrich_report`.
9. `image_pipeline.py` (минимальный) + admin-действие/команда загрузки.
10. Тесты.

**DoD:**
- [ ] `python manage.py migrate` — без ошибок.
- [ ] `python manage.py enrich_product --id <N>` — отрабатывает на реальном товаре
      (на dummy-провайдере).
- [ ] `content_locked=True` блокирует все изменения (unit-тест).
- [ ] `AiCallLog` создаётся для каждой попытки (успех/fallback/error).
- [ ] Очередь модерации в admin показывает товары с `confidence < 0.7`.
- [ ] ImagePipeline: фото скачивается, ресайз до 1200, thumb 400, WebP.
- [ ] `batch_enrich_task` приоритизирует `available_quantity > 0`.
- [ ] dummy-выход парсится корректно (включая ```` ```json ````-обёртку).
- [ ] `python manage.py enrich_report` — корректная статистика.
- [ ] `pytest apps/ai/ apps/catalog/ -x` — зелёные.
- [ ] Нет прямых `OtherApp.objects` из `apps/ai` (кроме FK через свои модели).

---

## 12. Явный YAGNI (вне эпика)

Скрейперы брендов (makita.ru/bosch-pt.ru), Яндекс.Маркет API, модель `VendorFeed`,
`EnrichOrchestrator` (4 источника), `EnrichLog`, мульти-агент/MCP-оркестрация,
реальный claude-провайдер с живыми вызовами, авто-источник изображений. Каждое —
отдельное решение под ADR/ROI.
