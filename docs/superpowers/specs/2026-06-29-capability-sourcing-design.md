# Capability `sourcing`: поиск внешнего контента для карточек товара

**Дата:** 2026-06-29
**Статус:** дизайн утверждён (5 раундов ревью), готов к плану реализации
**Предшественник:** EPIC-ENRICH (`docs/superpowers/specs/2026-06-26-epic-enrich-design.md`) — §12 YAGNI прямо откладывал внешние источники «под отдельный ADR, когда появятся ключи/выгрузки». Этот документ закрывает ту отложенную часть.
**Связанные:** `docs/ARCHITECTURE.md`, `docs/ARCHITECTURE-AI.md`, `data/attribute_rules.json` (каноническая карта провенанса).

---

## 1. Контекст и решения по курсу

После импорта из 1С и детерминированного обогащения у части товаров остаются пробелы:
пустые `description`/`short_description`, ненаполненные `is_ai_feature`-характеристики.
`enrich` (capability генерации) на dummy-провайдере лепит шаблон из `original_name` —
это не *реальный* контент. `sourcing` добывает **реальные факты со ссылкой** из внешних
источников и проводит их через человека-модератора.

**Зафиксированные бизнес-решения (5 раундов ревью):**

| Решение | Выбор |
|---|---|
| Граница плана | **Поиск** внешнего контента (НЕ свободная LLM-генерация, НЕ скрейпинг, НЕ файловые фиды) |
| Источники | **web-поиск** (LLM + search) + **API маркетплейсов/брендов**; оба возвращают факт со ссылкой |
| Публикация | **Всё через модерацию** — ни один внешний факт не публикуется без человека |
| Провенанс внешних фактов | выше `llm`, ниже извлечённых: `web/marketplace = 25` (между `keyword 30` и `llm 20`) |
| Подход к данным | **Approach B** — таблица доказательств (`ContentFinding` + `FindingEvidence`) |

**Явный YAGNI (вне этого дизайна):** скрейпинг сайтов брендов, файловые фиды поставщиков,
свободная LLM-генерация без заземления, авто-сведение/разрешение конфликтов источников
(оркестратор), авто-публикация без модерации.

---

## 2. Границы и инварианты

- `sourcing` — capability в `apps/ai`, рядом с `enrich`/`recommend`.
- **ADR-0004 (зависимость направлена `ai → catalog`, не наоборот):**
  - `sourcing` читает товар только через `catalog`-сервисы (`get_enrichable_product`,
    `pending_for_enrichment`) и **изменяет** карточку только через нейтральный
    catalog-owned контракт `apply_sourced_value(SourcedValueCommand)`.
  - Каталог **не знает** о моделях `apps/ai` (`ContentFinding` и пр.). Прямые
    `Product.objects` / `ProductAttributeValue.objects` из `apps/ai` запрещены
    (покрыто `test_boundaries`); допустимы только FK через собственные модели `ai`.
- **Три флага** проверяются и при постановке задачи, и **повторно внутри worker**:
  `ai`, `ai_sourcing` (новый env-флаг в `settings.FEATURES`), `external_integrations`.
- **LLM/внешний вывод — недоверенный ввод:** guardrails до сохранения; запрещённые поля
  (цена / остаток / статус заказа) применить физически нельзя.
- **`content_locked=True` — абсолютная защита:** проверяется в `apply_sourced_value`.
- `source_content()` **не изменяет** `Product` (читает через сервис, копит находки).
  Очередь модерации строится по `ContentFinding.status`, не по `Product.enrich_status`.

---

## 3. Провенанс — один резолвер, одна карта

Каноническая карта — единственная, в `data/attribute_rules.json` → `source_priority`.
Добавляем `web` и `marketplace`; существующие значения не трогаем:

```
manual 100 > import_1c 60 > regex 40 > keyword 30 > web 25 = marketplace 25 > llm 20 > inferred 10
```

- В `catalog.models.Source` enum добавляем `WEB`, `MARKETPLACE`.
- В `catalog.models.ContentSource` enum добавляем `WEB`, `MARKETPLACE`
  (`content_source` уже `max_length=12` — влезает).
- Новый **`apps/catalog/provenance.py`** — единственный резолвер, читает ту же карту:

```python
def can_overwrite(new: str, existing: str, *, allow_equal: bool = False) -> bool:
    """Авто: строго priority(new) > priority(existing).
    allow_equal=True — явное решение модератора (web поверх marketplace и т.п.)."""
```

- Авто-применение: **строго `>`**.
- Равный приоритет (`web` vs `marketplace`, повтор того же источника) — авто **запрещено**;
  модератор разрешает явно (`allow_equal=True`).

**Смешанный провенанс полей.** `Product.content_source` один — не выразит
«name=manual, description=web, attr=marketplace», поэтому объявляется как
**last-applied (legacy/coarse)** и обновляется **только при применении текстового
поля** (применение EAV-атрибута его не трогает — источник атрибута живёт в
`ProductAttributeValue.source`). Истинный провенанс карточных текстов — новый
`Product.content_field_sources` JSON (`{"name":"manual","description":"web"}`).

---

## 4. Модель данных

Жизненный цикл:
```
SourcingRun                      — один логический запуск source_content() по товару
 ├── ExternalCall                — один вызов источника (web|marketplace)
 └── ContentFinding              — дедуп-канон значения для (product, target)
      └── FindingEvidence        — каждое подтверждение факта (вызов + url + baseline)
              ↓ (модератор выбирает evidence)
      catalog.apply_sourced_value(SourcedValueCommand)   — нейтральный DTO
```

### 4.1 `SourcingRun` (`apps/ai/models.py`)
Запуск поиска — **не вызов модели**, поэтому отдельно от `AiCallLog`.

| Поле | Тип | Назначение |
|---|---|---|
| `idempotency_key` | CharField, unique | один на логический запуск; retry/redelivery переиспользует run |
| `product_ref` | PositiveIntegerField (index) | снимок id (без FK — как `AiCallLog`) |
| `status` | choices: `running/ok/degraded/configuration_error/error` | включённый sourcing без реальных источников → `configuration_error` (заметно) |
| `created_at`, `finished_at` | | для janitor зависших `running` |

### 4.2 `ExternalCall` (`apps/ai/models.py`, FK→SourcingRun)
Унифицирует web и marketplace; источник телеметрии и аудита оплаты.

| Поле | Тип | Назначение |
|---|---|---|
| `run` | FK→SourcingRun (CASCADE) | |
| `adapter` | CharField (`web`/`marketplace`) | |
| `provider` | CharField | конкретный провайдер/модель |
| `status` | choices: `running/ok/error/unknown` | `running` создаётся **до сети** |
| `provider_idempotency_key` | CharField, blank | если внешний API поддерживает |
| `tokens_in/out` | Int | |
| `cost` | Decimal | фактическая стоимость (reconciliation) |
| `reserved_cost` | Decimal | зарезервированная верхняя граница (бюджет) |
| `latency_ms`, `http_status` | | |
| `raw_excerpt` | TextField (лимит размера) | очищается retention-задачей |
| `created_at`, `finished_at` | | |

Constraint: `UniqueConstraint(run, adapter)` — один вызов адаптера на run (защита от
повторной оплаты). Статус-машина: `running → ok | error`; зависший `running` (crash)
janitor переводит в `unknown` (НЕ авто-ретрай).

### 4.3 `ContentFinding` (`apps/ai/models.py`)
Канонический кандидат значения для `(product, target)`; агрегаты — **только для отображения**.

| Поле | Тип | Назначение |
|---|---|---|
| `product` | FK→Product, `on_delete=SET_NULL`, null | навигация, пока товар жив |
| `product_ref` | PositiveIntegerField (index) | неизменяемый снимок (аудит переживает удаление) |
| `target_kind` | choices: `name/short_description/description/attribute` | |
| `attribute_slug` | CharField, `null=False, default=""` | обязателен при `attribute`; `""` для текстов (NULL-дубли исключены) |
| `value` | JSONField | типизированный конверт (§4.5) |
| `normalized_hash` | CharField | дедуп вместо длинного value |
| `source_name` | CharField | производный: источник evidence с макс. приоритетом (отображение) |
| `confidence` | Float | агрегат (отображение) |
| `status` | choices: `pending/applied/rejected/superseded` | терминальные: applied/rejected/superseded |
| `last_outcome` | CharField, blank | `conflict/locked/priority_blocked/invalid/missing_product/missing_attribute/apply_failed` |
| `attempt_token` | CharField, blank | защита guarded-записи `apply_failed` (§6) |
| `reviewed_by` | FK→User, `SET_NULL`, null | |
| `reviewed_at`, `applied_at`, `rejection_reason`, `created_at` | | audit trail |

Constraints:
- `CheckConstraint`: `attribute_slug != ""` ⇔ `target_kind == "attribute"`.
- `UniqueConstraint(product_ref, target_kind, attribute_slug, normalized_hash)` —
  дедуп факта (корроборация из разных источников/URL хранится в `FindingEvidence`).
- Индексы `(product_ref, status)`, `(status)`.

### 4.4 `FindingEvidence` (`apps/ai/models.py`)
Каждое подтверждение факта. Повторный запуск дедуплицирует `finding`, но **всегда**
добавляет evidence. `run` доступен через `evidence.external_call.run` (прямого `run`/
`external_call` на `finding` нет — рассинхрон невозможен).

| Поле | Тип | Назначение |
|---|---|---|
| `finding` | FK→ContentFinding (CASCADE) | |
| `external_call` | FK→ExternalCall, `on_delete=PROTECT`, `null=False` | какой вызов породил факт (аудит не удаляется) |
| `source_name` | CharField (`web`/`marketplace`) | |
| `confidence` | Float | |
| `observed_value_hash` | CharField | **baseline** целевого поля на момент ЭТОГО наблюдения |
| `observed_source` | CharField | источник, который был в поле на момент наблюдения |
| `canonical_url` | URLField | цитата (обязательна для `web`) |
| `observed_at` | | |

Constraint: `UniqueConstraint(finding, external_call, canonical_url)`.

### 4.5 Типизированный конверт `value`
JSON сохраняет тип EAV; decimal — строкой (без потери точности):
```json
{"type": "decimal",  "value": "12.34"}
{"type": "integer",  "value": 780}
{"type": "boolean",  "value": true}
{"type": "text",     "value": "SDS-plus"}
{"type": "option",   "value": "sds-plus"}
```
`apply_sourced_value` валидирует `type` против `AttributeType` целевого атрибута →
несоответствие = `ApplyResult("invalid")`.

### 4.6 `SourcingBudget` (`apps/ai/models.py`)
Атомарная защита дневного бюджета от параллельных workers.

| Поле | Тип |
|---|---|
| `day` | DateField, unique |
| `daily_cap` | Decimal |
| `reserved` | Decimal |
| `spent` | Decimal |

---

## 5. Контракты

### 5.1 Catalog-owned применение (нейтральный DTO)
```python
# apps/catalog/provenance.py — каталог НЕ знает про ContentFinding
@dataclass(frozen=True)
class SourcedValueCommand:
    product_id: int
    target_kind: str            # name|short_description|description|attribute
    attribute_slug: str         # "" для текстов
    value: dict                 # типизированный конверт §4.5
    source: str                 # Source: web|marketplace
    confidence: float
    observed_value_hash: str    # baseline ИЗ ВЫБРАННОГО evidence
    observed_source: str
    allow_equal_override: bool = False

@dataclass(frozen=True)
class ApplyResult:
    status: str   # applied|skipped_locked|conflict|priority_blocked|invalid|missing_product|missing_attribute
    reason: str = ""

def apply_sourced_value(cmd: SourcedValueCommand) -> ApplyResult:
    """Атомарно (select_for_update по Product): content_locked → skipped_locked;
    baseline (observed_value_hash vs текущее) → conflict; can_overwrite (строго >,
    либо allow_equal) → priority_blocked; тип конверта → invalid; иначе applied.
    Текстовое поле → обновляет content_source(last-applied)+content_field_sources;
    атрибут → PAV.source + rebuild_attrs_cache. content_source при атрибуте НЕ трогает."""
```

### 5.2 AI оркестрирует (выбор конкретного evidence)
```python
# apps/ai/services.py
def approve_and_apply_finding(finding_id: int, evidence_id: int, reviewer_id: int) -> ApplyResult:
    attempt = new_token()
    try:
        with transaction.atomic():
            # P0: фикс. порядок блокировок — все находки мишени по pk, ЗАТЕМ Product
            siblings = (ContentFinding.objects
                .filter(product_ref=pr, target_kind=tk, attribute_slug=slug)
                .select_for_update().order_by("pk"))
            findings = {f.pk: f for f in siblings}
            f = findings[finding_id]
            if f.status != PENDING:                       # идемпотентность повтора
                return ApplyResult("skipped", "already_processed")
            f.attempt_token = attempt
            ev = FindingEvidence.objects.get(pk=evidence_id, finding=f)
            cmd = command_from_evidence(f, ev)            # value=канон finding; source/conf/baseline=evidence
            result = catalog.apply_sourced_value(cmd)     # внутри select_for_update(Product)
            if result.status == "applied":
                f.status, f.applied_at = APPLIED, now()
                f.reviewed_by, f.reviewed_at = reviewer_id, now()
                supersede_competitors(findings, f)        # applied той же мишени → superseded
            else:
                f.last_outcome = result.status            # conflict/locked/priority_blocked/invalid/...
                f.reviewed_by, f.reviewed_at = reviewer_id, now()
            f.save()
            return result
    except CatalogError as exc:                           # ТЕХНИЧЕСКАЯ ошибка
        # rollback всей транзакции уже произошёл; пишем apply_failed ОТДЕЛЬНОЙ транзакцией,
        # guarded: только если finding всё ещё pending и тот же attempt (не затереть чужой результат)
        ContentFinding.objects.filter(
            pk=finding_id, status=PENDING, attempt_token=attempt
        ).update(last_outcome="apply_failed", rejection_reason=str(exc)[:255])
        raise
```

### 5.3 Порт источника (с телеметрией)
```python
# apps/ai/sourcing/ports.py
@dataclass(frozen=True)
class SourceQuery:
    article: str; name: str; brand: str; category: str; needed_targets: list

@dataclass(frozen=True)
class Finding:
    target_kind: str; attribute_slug: str; value: dict; canonical_url: str; confidence: float

@dataclass(frozen=True)
class SourceReply:                       # телеметрия → ExternalCall
    findings: list                       # list[Finding]
    provider: str
    tokens_in: int = 0; tokens_out: int = 0
    cost: float = 0.0; http_status: int | None = None

class ContentSourcePort(Protocol):
    def find(self, query: SourceQuery) -> SourceReply: ...
```

---

## 6. Поток и runtime

### 6.1 `services.source_content(*, product_id, sources=None, idempotency_key) -> SourcingResult`
1. Перепроверить флаги (`ai`, `ai_sourcing`, `external_integrations`) и бюджет.
2. `get_or_create(SourcingRun, idempotency_key=...)` (status=`running`).
3. Прочитать товар через `catalog` (нет товара → `error`/skip).
4. `content_locked` → не ищем, run `degraded`, причина в логе.
5. Для каждого включённого адаптера:
   - если для run уже есть `ExternalCall(adapter, status=ok)` → **пропустить** (idempotency, без повторной оплаты);
   - **бюджет** (§6.4): резерв верхней границы до сети;
   - создать `ExternalCall(status=running)` до сети; вызвать `port.find()`; reconcile → `ok`/`error`;
   - изоляция: исключение адаптера → `ExternalCall.error`, остальные адаптеры работают.
6. guardrails по каждому `Finding`; сохранить `ContentFinding` (`get_or_create` по unique)
   + **всегда** `FindingEvidence` (с baseline-снимком целевого поля сейчас).
7. Закрыть run (`ok`/`degraded`/`error`, `finished_at`). **Товар не изменяется.**

### 6.2 Guardrails (`apps/ai/sourcing/guardrails.py`)
`web` без `canonical_url` → reject; URL вне allowlist (по нормализованному hostname) → reject;
запрещённые поля (цена/остаток/статус) → reject всегда; тип `value` по атрибуту; клампы
confidence [0,1], лимиты длины. Выход адаптера = недоверенный ввод.

### 6.3 Целостность платного вызова (честный exactly-once)
`UniqueConstraint(run, adapter)` + `running`-до-сети + provider idempotency key (если есть).
Без поддержки idempotency внешним API **exactly-once гарантировать нельзя**: зависший
`running` = возможная оплаченная-но-неподтверждённая попытка → janitor переводит в
`unknown`, авто-ретрая нет; повтор — только после ручного решения/сверки с провайдером.
Это зафиксированное ограничение, не баг.

### 6.4 Бюджет (атомарная резервация)
```python
with transaction.atomic():
    b = SourcingBudget.objects.select_for_update().get_or_create(day=today())[0]
    if b.spent + b.reserved + max_call_cost > b.daily_cap:
        raise BudgetExceeded            # громко стопит батч ДО платного вызова
    b.reserved += max_call_cost; b.save()    # резервируем ВЕРХНЮЮ границу
# после вызова: reserved -= max_call_cost; spent += actual (reconciliation)
# crash: резерв остаётся занятым до janitor/reconciliation по unknown-вызову
```

### 6.5 Celery (`apps/ai/tasks.py`)
- `source_product_task(product_id, idempotency_key)` — bind, backoff; ретраит только
  transient (сеть/таймаут/429); `configuration_error` не ретраит. Флаги+бюджет — внутри.
- `batch_source_task(category_slug=None, limit=100)` — приоритет `available_quantity>0`;
  стоп по бюджету.
- `mark_stale_sourcing_runs` — janitor зависших `running` (run и `ExternalCall`→`unknown`).
- `purge_sourcing_excerpts` — retention: очистка `ExternalCall.raw_excerpt` старше N дней
  (структурные находки + url + метаданные остаются).

### 6.6 Источники (`apps/ai/sourcing/sources/`)
`web_search.py` (Claude web_search / search API; ключ `ANTHROPIC_API_KEY`),
`marketplace.py` (Яндекс.Маркет и пр.; свой ключ), `dummy.py` — **только тест**.
`get_sources()` включает адаптеры по наличию ключей; включённый sourcing без реальных
источников → run `configuration_error` (заметно), dummy в проде не подменяет.

**Безопасность web:** allowlist доменов (офиц. бренды + известные ритейлеры) по
нормализованному hostname; сервер произвольные URL из вывода модели сам не фетчит
(только `https`, хост не private/loopback/link-local, запрет редиректов в private,
таймаут, лимит размера — если фетч вообще нужен); rate-limit по домену и провайдеру;
ToS/лицензии — только короткий `raw_excerpt` + атрибуция через url.

### 6.7 Admin (`apps/ai/admin.py`)
`ContentFindingAdmin` — очередь по `status=pending`; конкурирующие находки одной мишени
рядом + baseline vs текущее (конфликт виден до применения); inline `FindingEvidence`
(выбор конкретного evidence). Действия **частично успешны**: отдельная транзакция и
результат на каждую находку; одобрение моддером передаёт `allow_equal_override=True`.
- `approve` → `approve_and_apply_finding(finding_id, evidence_id, reviewer_id)`;
- `reject` → `status=rejected` + `rejection_reason`.

### 6.8 CLI (`apps/ai/management/commands/`)
`source_product` (`--id/--article`, `--dry-run` — без платных вызовов; `--probe` —
вызвать-но-не-сохранять, явно опасный), `source_catalog` (`--category/--all --limit
--commit`), `source_report` (находки по статусам/источникам/стоимости).

---

## 7. Тесты (`pytest apps/ai apps/catalog`)
- провенанс: `web` бьёт `llm`/`inferred`, НЕ `manual/import_1c/regex/keyword`; равный тир требует `allow_equal_override`;
- baseline-конфликт: значение изменилось между поиском и модерацией → `conflict` (не затир);
- rollback всей транзакции: техническая ошибка каталога → finding и product нетронуты; `apply_failed` записан отдельной guarded-транзакцией;
- guarded `apply_failed` не затирает результат другого модератора (другой attempt/статус);
- повторное одобрение → no-op;
- concurrent update двух модераторов на конкурирующие находки → первый applied+supersede, второй `conflict`;
- порядок блокировок исключает дедлок (siblings по pk → Product);
- Celery redelivery: повторная доставка не плодит находок и не вызывает повторную оплату (skip по `ExternalCall(ok)`);
- evidence: повторный запуск дедуплицирует finding, добавляет `FindingEvidence`;
- бюджет: параллельные резервации не превышают `daily_cap`; превышение громко стопит;
- неизвестный source; удалённый товар (`SET_NULL`); удалённый атрибут (`missing_attribute`);
- `content_locked` → `skipped_locked`;
- web без allowlist-hostname → reject; запрещённые поля (цена/остаток) → reject;
- `content_source` (last-applied) меняется только для текстовых targets, не при атрибуте;
- изоляция адаптеров: один упал → остальные находки сохранены;
- границы ADR: нет `Product.objects`/`ProductAttributeValue.objects` в ядре `apps/ai`; каталог не импортирует `ai`.

---

## 8. Порядок реализации (малые PR, как в EPIC-ENRICH)
1. `catalog.provenance` (карта-резолвер `can_overwrite` + DTO `SourcedValueCommand`/`ApplyResult` + `apply_sourced_value`) + миграция: `Source`/`ContentSource` (+`web`,`marketplace`), `Product.content_field_sources`, `web/marketplace` в `attribute_rules.json` + тесты.
2. Модели `SourcingRun`/`ExternalCall`/`ContentFinding`/`FindingEvidence`/`SourcingBudget` + миграция + тесты constraints.
3. `sourcing/ports.py` + `guardrails.py` + `sources/dummy.py` + тесты.
4. `services.source_content` + `approve_and_apply_finding` (транзакция/порядок локов/идемпотентность/конкурентность/guarded apply_failed) + тесты.
5. `tasks.py` (retries/бюджет/идемпотентность) + `mark_stale_sourcing_runs` + `purge_sourcing_excerpts` + флаг `ai_sourcing` + тесты.
6. `admin.py` (очередь + частично-успешные действия + inline evidence) + тесты.
7. CLI `source_product`/`source_catalog`/`source_report` + тесты.
8. Адаптеры `web_search`/`marketplace` (за ключами; allowlist по hostname/SSRF/rate-limit/ToS) + тесты.

## 9. DoD
- [ ] миграции применяются; `Source`/`ContentSource`/`attribute_rules.json` синхронны.
- [ ] `apply_sourced_value` — нейтральный DTO; каталог не импортирует `ai` (тест границ зелёный).
- [ ] весь цикл: `source_content` (dummy) → находка+evidence → admin approve(evidence) → `apply_sourced_value` → `applied`.
- [ ] все P0-инварианты покрыты тестами (§7).
- [ ] `pytest apps/ai apps/catalog -x` зелёные; ruff+black чисто.
- [ ] флаги `ai`/`ai_sourcing`/`external_integrations` гасят capability; без ключей → `configuration_error`.
