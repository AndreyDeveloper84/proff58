# EPIC-ENRICH (capability `enrich`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать AI-обогащение карточек товара (`enrich`) как гибрид «детерминированный слой + LLM-добивка» за портом, с журналом `AiCallLog`, guardrails, Celery-runtime, очередью модерации и CLI — строго по `docs/ARCHITECTURE-AI.md`.

**Architecture:** `enrich` — capability за `apps/ai/services.py`. `apps/ai` читает/пишет каталог только через сервис `apps/catalog/enrichment.py` (граница ADR-0004). LLM спрятан за портом `apps/ai/ports.py`; сейчас активен `dummy`-провайдер. Выход модели — недоверенный ввод: валидируется в `guardrails.py`; `content_locked` и провенанс (`source=llm` — низший) неприкосновенны. Всё под фичефлагом `ai`.

**Tech Stack:** Django 5 + DRF, PostgreSQL, Celery, Pillow (ImagePipeline), pytest.

## Global Constraints

- Общение и комментарии в коде — на русском (CLAUDE.md).
- Стиль: ruff + black, line-length 100. Миграции из линта исключены.
- Тестам нужен PostgreSQL; `pytest` с `--reuse-db` (см. `pyproject.toml`), маркер `@pytest.mark.django_db`.
- `apps/ai` НЕ обращается к `OtherApp.objects.*` напрямую — только через сервисы каталога или FK в своих моделях.
- LLM не источник истины для цены/остатка/статуса заказа — apply физически их не трогает.
- Приоритет провенанса: `manual > import_1c > regex > keyword > llm`. `source=llm` пишется только в пробел или поверх существующего `llm`.
- `content_locked=True` — абсолютная защита: при ней enrich не пишет ничего, кроме `AiCallLog`.
- Фичефлаг: `apps.core.features.is_enabled("ai")` (env `FEATURE_AI`, default False).
- Conventional Commits; коммит в конце каждой задачи. Подпись коммита:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## File Structure

| Файл | Создать/Изменить | Ответственность |
|---|---|---|
| `apps/catalog/models.py` | Изменить | `EnrichStatus`, `ContentSource` (TextChoices) + поля `Product`: `enrich_status`, `content_source`, `content_confidence`; proxy `ModerationProduct` |
| `apps/catalog/migrations/0019_product_enrich_fields.py` | Создать | миграция полей Product |
| `apps/catalog/migrations/0020_moderationproduct.py` | Создать | proxy-модель (без изменения схемы) |
| `apps/catalog/enrichment.py` | Создать | `get_enrichable_product`, `apply_ai_enrichment`, `pending_for_enrichment`, dataclass `AiAttr` — единственная точка записи enrich-результата в каталог |
| `apps/ai/models.py` | Создать | `AiCallLog` |
| `apps/ai/migrations/0001_initial.py` | Создать | миграция `AiCallLog` |
| `apps/ai/ports.py` | Создать | порт `ModelPort` + dataclass `ModelCall`/`ModelReply` + `get_provider()` |
| `apps/ai/providers/{__init__,dummy,claude}.py` | Создать | провайдеры: dummy (активен), claude (каркас) |
| `apps/ai/guardrails.py` | Создать | `EnrichedAttr`, `EnrichResult`, `parse_enrich_output()` |
| `apps/ai/services.py` | Изменить | добавить `enrich(*, product_id, force=False) -> EnrichResult` |
| `apps/ai/tasks.py` | Создать | `enrich_product_task`, `batch_enrich_task` |
| `apps/ai/receivers.py` | Создать | подписка на `product_created` |
| `apps/ai/apps.py` | Изменить | `ready()` — подписка receivers под флагом `ai` |
| `apps/ai/admin.py` | Создать | `AiCallLogAdmin` + `ModerationQueueAdmin` |
| `apps/ai/management/commands/{enrich_product,enrich_catalog,enrich_report}.py` | Создать | CLI |
| `apps/catalog/image_pipeline.py` | Создать | `ImagePipeline` (минимальный) |
| `apps/{ai,catalog}/tests/test_*.py` | Создать | тесты |

---

## Task 1: Поля обогащения на Product + миграция

**Files:**
- Modify: `apps/catalog/models.py` (рядом со статусами `ProductStatus`/`StockStatus`, стр. ~383–393, и в теле `Product`)
- Create: `apps/catalog/migrations/0019_product_enrich_fields.py`
- Test: `apps/catalog/tests/test_enrich_fields.py`

**Interfaces:**
- Produces: `Product.enrich_status` (str), `Product.content_source` (str|None), `Product.content_confidence` (float|None); `EnrichStatus`, `ContentSource` (TextChoices).

- [ ] **Step 1: Тест на дефолты полей**

```python
# apps/catalog/tests/test_enrich_fields.py
import pytest
from apps.catalog.models import Category, Product, ProductStatus, EnrichStatus


def _product(**kw):
    cat = Category.add_root(name="Перфораторы", slug="perf")
    data = dict(category=cat, name="t", slug="t", status=ProductStatus.IMPORTED,
                is_active=False, price="1000")
    data.update(kw)
    return Product.objects.create(**data)


@pytest.mark.django_db
def test_enrich_fields_defaults():
    p = _product()
    assert p.enrich_status == EnrichStatus.PENDING
    assert p.content_source is None
    assert p.content_confidence is None
```

- [ ] **Step 2: Запустить — упадёт** (нет `EnrichStatus`/полей)

Run: `pytest apps/catalog/tests/test_enrich_fields.py -v`
Expected: FAIL (ImportError `EnrichStatus` / AttributeError).

- [ ] **Step 3: Добавить choices и поля**

Рядом с `ProductStatus`/`StockStatus` в `apps/catalog/models.py`:

```python
class EnrichStatus(models.TextChoices):
    PENDING = "pending", _("Ожидает")
    IN_QUEUE = "in_queue", _("В очереди")
    DONE = "done", _("Готово")
    MODERATION = "moderation", _("На модерации")
    FAILED = "failed", _("Ошибка")


class ContentSource(models.TextChoices):
    MANUAL = "manual", _("Вручную")
    IMPORT_1C = "import_1c", _("Импорт 1С")
    LLM = "llm", _("AI-генерация")
```

В теле `Product` (после `content_locked`):

```python
    enrich_status = models.CharField(
        _("Статус обогащения"),
        max_length=12,
        choices=EnrichStatus.choices,
        default=EnrichStatus.PENDING,
        db_index=True,
    )
    content_source = models.CharField(
        _("Источник карточного контента"),
        max_length=12,
        choices=ContentSource.choices,
        null=True,
        blank=True,
    )
    content_confidence = models.FloatField(
        _("Уверенность контента"), null=True, blank=True
    )
```

- [ ] **Step 4: Сгенерировать миграцию**

Run: `python manage.py makemigrations catalog --name product_enrich_fields`
Expected: создан `0019_product_enrich_fields.py` с `dependencies = [("catalog", "0018_category_hero_cta_href_category_hero_cta_label_and_more")]`.

- [ ] **Step 5: Прогнать тест и миграцию**

Run: `python manage.py migrate catalog && pytest apps/catalog/tests/test_enrich_fields.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/catalog/models.py apps/catalog/migrations/0019_product_enrich_fields.py apps/catalog/tests/test_enrich_fields.py
git commit -m "feat(enrich): поля enrich_status/content_source/content_confidence на Product"
```

---

## Task 2: Модель `AiCallLog` + миграция + admin

**Files:**
- Create: `apps/ai/models.py`, `apps/ai/migrations/__init__.py`, `apps/ai/migrations/0001_initial.py`
- Create: `apps/ai/admin.py` (здесь только `AiCallLogAdmin`; очередь модерации — Task 8)
- Test: `apps/ai/tests/test_ai_call_log.py`

**Interfaces:**
- Produces: `AiCallLog` (поля: `capability`, `provider`, `model`, `input_ref`, `output`, `tokens_in`, `tokens_out`, `cost`, `latency_ms`, `status`, `reason`, `entity_ref`, `created_at`); `AiCallLog.Capability`, `AiCallLog.Status`.

- [ ] **Step 1: Тест создания записи**

```python
# apps/ai/tests/test_ai_call_log.py
import pytest
from apps.ai.models import AiCallLog


@pytest.mark.django_db
def test_ai_call_log_minimal():
    log = AiCallLog.objects.create(
        capability=AiCallLog.Capability.ENRICH,
        provider="dummy",
        model="dummy-1",
        status=AiCallLog.Status.OK,
        entity_ref=123,
    )
    assert log.pk and log.created_at is not None
    assert log.tokens_in == 0 and log.tokens_out == 0
```

- [ ] **Step 2: Запустить — упадёт** (нет `apps.ai.models`)

Run: `pytest apps/ai/tests/test_ai_call_log.py -v`
Expected: FAIL (ModuleNotFoundError / no model).

- [ ] **Step 3: Создать модель**

```python
# apps/ai/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _


class AiCallLog(models.Model):
    """Журнал каждого обращения к модели (ARCHITECTURE-AI §6).

    Пишется всегда — включая fallback и error. FK на чужие модели нет:
    связь с доменом — через ``entity_ref`` (например product_id).
    """

    class Capability(models.TextChoices):
        ENRICH = "enrich", _("Обогащение")
        RECOMMEND = "recommend", _("Рекомендации")
        ASSIST = "assist", _("Ассистент")

    class Status(models.TextChoices):
        OK = "ok", _("Успех")
        FALLBACK = "fallback", _("Фолбэк")
        ERROR = "error", _("Ошибка")

    capability = models.CharField(max_length=12, choices=Capability.choices, db_index=True)
    provider = models.CharField(max_length=32, blank=True)
    model = models.CharField(max_length=64, blank=True)
    input_ref = models.CharField(max_length=255, blank=True)
    output = models.JSONField(null=True, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=5, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=8, choices=Status.choices, db_index=True)
    reason = models.CharField(max_length=255, blank=True)
    entity_ref = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Вызов AI")
        verbose_name_plural = _("Журнал вызовов AI")
        indexes = [models.Index(fields=["capability", "status"])]

    def __str__(self) -> str:
        return f"{self.capability}/{self.status} #{self.entity_ref or '-'}"
```

- [ ] **Step 4: Создать пакет миграций и миграцию**

Создать пустой `apps/ai/migrations/__init__.py`, затем:
Run: `python manage.py makemigrations ai --name initial`
Expected: `apps/ai/migrations/0001_initial.py` (без зависимостей от catalog).

- [ ] **Step 5: Зарегистрировать в admin**

```python
# apps/ai/admin.py
from django.contrib import admin

from .models import AiCallLog


@admin.register(AiCallLog)
class AiCallLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "capability", "status", "provider", "model",
                    "entity_ref", "tokens_out", "latency_ms")
    list_filter = ("capability", "status", "provider")
    search_fields = ("entity_ref", "input_ref", "reason")
    readonly_fields = ("output",)
    date_hierarchy = "created_at"
```

- [ ] **Step 6: Прогнать**

Run: `python manage.py migrate ai && pytest apps/ai/tests/test_ai_call_log.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/ai/models.py apps/ai/migrations apps/ai/admin.py apps/ai/tests/test_ai_call_log.py
git commit -m "feat(enrich): модель AiCallLog + admin"
```

---

## Task 3: Порт модели и провайдеры (dummy + каркас claude)

**Files:**
- Create: `apps/ai/ports.py`, `apps/ai/providers/__init__.py`, `apps/ai/providers/dummy.py`, `apps/ai/providers/claude.py`
- Test: `apps/ai/tests/test_providers.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) ModelCall(system: str, user: str, max_tokens: int = 1024)`
  - `@dataclass(frozen=True) ModelReply(text: str, tokens_in: int = 0, tokens_out: int = 0, model: str = "", provider: str = "")`
  - `class ModelPort(Protocol): def complete(self, call: ModelCall) -> ModelReply: ...`
  - `def get_provider() -> ModelPort` — claude при `settings.ANTHROPIC_API_KEY`, иначе dummy.
  - `DummyProvider.complete` отдаёт валидный JSON enrich-схемы (см. Task 4).

- [ ] **Step 1: Тест dummy-провайдера**

```python
# apps/ai/tests/test_providers.py
import json

from apps.ai.ports import ModelCall, get_provider
from apps.ai.providers.dummy import DummyProvider


def test_dummy_returns_valid_enrich_json():
    prov = DummyProvider()
    reply = prov.complete(ModelCall(system="s", user="Перфоратор HR2470 Makita 780Вт"))
    data = json.loads(reply.text)
    assert {"name", "short_description", "description", "attributes", "confidence"} <= data.keys()
    assert reply.provider == "dummy"


def test_get_provider_defaults_to_dummy(settings):
    settings.ANTHROPIC_API_KEY = ""
    assert get_provider().__class__.__name__ == "DummyProvider"
```

- [ ] **Step 2: Запустить — упадёт**

Run: `pytest apps/ai/tests/test_providers.py -v`
Expected: FAIL (нет модулей).

- [ ] **Step 3: Порт**

```python
# apps/ai/ports.py
"""Порт-абстракция вызова модели (ARCHITECTURE-AI §5).

Сервисы знают только порт. Конкретный провайдер выбирается ``get_provider()``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from django.conf import settings


@dataclass(frozen=True)
class ModelCall:
    system: str
    user: str
    max_tokens: int = 1024


@dataclass(frozen=True)
class ModelReply:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    provider: str = ""


class ModelPort(Protocol):
    def complete(self, call: ModelCall) -> ModelReply: ...


def get_provider() -> ModelPort:
    """claude при наличии ключа, иначе детерминированный dummy."""
    if getattr(settings, "ANTHROPIC_API_KEY", ""):
        from .providers.claude import ClaudeProvider

        return ClaudeProvider()
    from .providers.dummy import DummyProvider

    return DummyProvider()
```

- [ ] **Step 4: Dummy-провайдер**

```python
# apps/ai/providers/dummy.py
"""Детерминированный провайдер: валидный enrich-JSON из original_name.

Без сети и без LLM. Используется сейчас и в тестах. Формирует короткое имя
(первые слова до токена с цифрой) и шаблонные описания.
"""
from __future__ import annotations

import json
import re

from ..ports import ModelCall, ModelReply

_NUM = re.compile(r"\d")


def _short_name(raw: str) -> str:
    words = []
    for w in raw.replace(";", " ").split():
        if _NUM.search(w) and len(words) >= 2:
            break
        words.append(w)
        if len(words) >= 4:
            break
    return " ".join(words) or raw[:64]


class DummyProvider:
    name = "dummy"
    model = "dummy-1"

    def complete(self, call: ModelCall) -> ModelReply:
        raw = call.user.strip()
        name = _short_name(raw)
        payload = {
            "name": name,
            "short_description": f"{name} — инструмент для профессионального применения.",
            "description": (
                f"{name}. Описание сгенерировано детерминированным провайдером "
                f"на основе данных из учётной системы. Применение, особенности и "
                f"назначение уточняются при наполнении карточки."
            ),
            "attributes": [],
            "confidence": 0.5,
        }
        text = json.dumps(payload, ensure_ascii=False)
        return ModelReply(
            text=text, tokens_in=len(raw.split()), tokens_out=len(text.split()),
            model=self.model, provider=self.name,
        )
```

- [ ] **Step 5: Каркас claude-провайдера + пакет**

```python
# apps/ai/providers/claude.py
"""Каркас реального провайдера. Живые вызовы — следующая итерация.

Активируется ``get_provider()`` при непустом ``settings.ANTHROPIC_API_KEY``.
Пока метод явно не реализован — осознанная заглушка под будущий PR.
"""
from __future__ import annotations

from ..ports import ModelCall, ModelReply


class ClaudeProvider:
    name = "claude"
    model = "claude-sonnet-4-6"

    def complete(self, call: ModelCall) -> ModelReply:
        raise NotImplementedError(
            "ClaudeProvider — каркас; живые вызовы появятся в отдельной итерации"
        )
```

И пустой `apps/ai/providers/__init__.py`.

- [ ] **Step 6: Прогнать**

Run: `pytest apps/ai/tests/test_providers.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/ai/ports.py apps/ai/providers apps/ai/tests/test_providers.py
git commit -m "feat(enrich): порт модели + dummy-провайдер (+каркас claude)"
```

---

## Task 4: Guardrails — парсинг и валидация выхода

**Files:**
- Create: `apps/ai/guardrails.py`
- Test: `apps/ai/tests/test_guardrails.py`

**Interfaces:**
- Consumes: `ModelReply.text` (str).
- Produces:
  - `@dataclass(frozen=True) EnrichedAttr(slug: str, value, confidence: int = 60)`
  - `@dataclass(frozen=True) EnrichResult(name, short_description, description, attributes: list[EnrichedAttr], confidence: float, source: str)`
  - `def parse_enrich_output(text: str) -> EnrichResult | None` — `None` при невалидном выходе.

- [ ] **Step 1: Тесты парсинга**

```python
# apps/ai/tests/test_guardrails.py
from apps.ai.guardrails import parse_enrich_output


def test_parses_plain_json():
    text = '{"name":"Дрель X","short_description":"кратко","description":"полно",' \
           '"attributes":[{"slug":"power","value":780,"confidence":60}],"confidence":0.8}'
    r = parse_enrich_output(text)
    assert r.name == "Дрель X" and r.confidence == 0.8
    assert r.attributes[0].slug == "power" and r.attributes[0].value == 780


def test_parses_json_code_fence():
    text = '```json\n{"name":"X","short_description":"a","description":"b",' \
           '"attributes":[],"confidence":0.5}\n```'
    assert parse_enrich_output(text).name == "X"


def test_rejects_garbage_returns_none():
    assert parse_enrich_output("извините, не понял") is None


def test_rejects_missing_keys():
    assert parse_enrich_output('{"name":"X"}') is None
```

- [ ] **Step 2: Запустить — упадёт**

Run: `pytest apps/ai/tests/test_guardrails.py -v`
Expected: FAIL (нет модуля).

- [ ] **Step 3: Реализация guardrails**

```python
# apps/ai/guardrails.py
"""Валидация выхода LLM (ARCHITECTURE-AI §7). Выход — недоверенный ввод.

``parse_enrich_output`` возвращает ``None`` на любой невалидный выход — вызывающий
деградирует (берёт то, что дал детерминированный слой), а не падает 500.
Защищённые поля (цена/остаток/заказ) физически отсутствуют в схеме.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)
_REQUIRED = {"name", "short_description", "description", "attributes", "confidence"}


@dataclass(frozen=True)
class EnrichedAttr:
    slug: str
    value: object
    confidence: int = 60


@dataclass(frozen=True)
class EnrichResult:
    name: str | None
    short_description: str | None
    description: str | None
    attributes: list[EnrichedAttr]
    confidence: float
    source: str  # "llm" | "fallback"


def _extract_json(text: str) -> dict | None:
    text = (text or "").strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def parse_enrich_output(text: str) -> EnrichResult | None:
    data = _extract_json(text)
    if data is None or not _REQUIRED <= data.keys():
        return None
    try:
        conf = float(data["confidence"])
    except (TypeError, ValueError):
        return None
    attrs: list[EnrichedAttr] = []
    for raw in data.get("attributes") or []:
        if not isinstance(raw, dict) or "slug" not in raw or "value" not in raw:
            continue
        try:
            c = int(raw.get("confidence", 60))
        except (TypeError, ValueError):
            c = 60
        attrs.append(EnrichedAttr(slug=str(raw["slug"]), value=raw["value"],
                                  confidence=max(0, min(100, c))))
    return EnrichResult(
        name=(str(data["name"]).strip() or None) if data["name"] else None,
        short_description=(str(data["short_description"]).strip() or None)
        if data["short_description"] else None,
        description=(str(data["description"]).strip() or None)
        if data["description"] else None,
        attributes=attrs,
        confidence=max(0.0, min(1.0, conf)),
        source="llm",
    )
```

- [ ] **Step 4: Прогнать**

Run: `pytest apps/ai/tests/test_guardrails.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/ai/guardrails.py apps/ai/tests/test_guardrails.py
git commit -m "feat(enrich): guardrails — парсинг и валидация выхода LLM"
```

---

## Task 5: Сервис применения в каталоге (`apps/catalog/enrichment.py`)

**Files:**
- Create: `apps/catalog/enrichment.py`
- Test: `apps/catalog/tests/test_enrichment_apply.py`

**Interfaces:**
- Produces:
  - `@dataclass AiAttr(slug: str, value, confidence: int = 60)`
  - `def get_enrichable_product(pk: int) -> Product | None`
  - `def pending_for_enrichment(*, category_slug=None, limit=100, only_empty=True) -> list[int]` — id товаров для батча, приоритет `available_quantity > 0` (используется в Task 7/9, чтобы `apps/ai` не звал `Product.objects` напрямую).
  - `def apply_ai_enrichment(product, *, name=None, short_description=None, description=None, attributes: list[AiAttr] = (), confidence: float | None = None, force: bool = False) -> dict` — пишет только пробелы; PAV `source=llm` только в пробел или поверх `llm`; пересобирает `attrs_cache`; ставит `content_source/content_confidence/enrich_status` (`moderation` при `confidence < 0.7`). При `content_locked` без `force` — `{"locked": True, "fields_updated": []}`.

- [ ] **Step 1: Тесты применения**

```python
# apps/catalog/tests/test_enrichment_apply.py
import pytest

from apps.catalog.enrichment import (AiAttr, apply_ai_enrichment,
                                     get_enrichable_product, pending_for_enrichment)
from apps.catalog.models import (Attribute, AttributeType, Category, EnrichStatus,
                                  Product, ProductAttributeValue, ProductStatus, Source)


def _product(**kw):
    cat = Category.objects.first() or Category.add_root(name="Перфораторы", slug="perf")
    data = dict(category=cat, name="", slug="p1", original_name="Перфоратор HR2470 Makita",
                status=ProductStatus.IMPORTED, is_active=False, price="1000")
    data.update(kw)
    return Product.objects.create(**data)


@pytest.mark.django_db
def test_get_enrichable_returns_unpublished():
    p = _product()
    assert get_enrichable_product(p.pk).pk == p.pk
    assert get_enrichable_product(999999) is None


@pytest.mark.django_db
def test_fills_only_empty_card_fields():
    p = _product(slug="p2", description="уже есть")
    res = apply_ai_enrichment(p, name="Перфоратор Makita HR2470",
                              description="новое", confidence=0.9)
    p.refresh_from_db()
    assert p.name == "Перфоратор Makita HR2470"
    assert p.description == "уже есть"
    assert p.content_source == "llm" and p.enrich_status == EnrichStatus.DONE
    assert "name" in res["fields_updated"] and "description" not in res["fields_updated"]


@pytest.mark.django_db
def test_low_confidence_goes_to_moderation():
    p = _product(slug="p3")
    apply_ai_enrichment(p, name="X", confidence=0.5)
    p.refresh_from_db()
    assert p.enrich_status == EnrichStatus.MODERATION


@pytest.mark.django_db
def test_content_locked_blocks_everything():
    p = _product(slug="p4", content_locked=True)
    res = apply_ai_enrichment(p, name="X", confidence=0.9)
    p.refresh_from_db()
    assert p.name == "" and res["locked"] is True


@pytest.mark.django_db
def test_llm_does_not_overwrite_manual_pav():
    p = _product(slug="p5")
    attr = Attribute.objects.create(slug="power", name="Мощность",
                                    attribute_type=AttributeType.INTEGER, unit="Вт")
    ProductAttributeValue.objects.create(product=p, attribute=attr, value_integer=900,
                                         source=Source.MANUAL, confidence=100)
    apply_ai_enrichment(p, attributes=[AiAttr(slug="power", value=780)], confidence=0.9)
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    assert pav.value_integer == 900 and pav.source == Source.MANUAL


@pytest.mark.django_db
def test_llm_writes_into_gap_pav():
    p = _product(slug="p6")
    Attribute.objects.create(slug="power", name="Мощность",
                             attribute_type=AttributeType.INTEGER, unit="Вт")
    apply_ai_enrichment(p, attributes=[AiAttr(slug="power", value=780)], confidence=0.9)
    pav = ProductAttributeValue.objects.get(product=p, attribute__slug="power")
    assert pav.value_integer == 780 and pav.source == Source.LLM
    p.refresh_from_db()
    assert p.attrs_cache.get("power") == 780


@pytest.mark.django_db
def test_pending_prioritizes_in_stock():
    _product(slug="instock", available_quantity=10)
    _product(slug="nostock", available_quantity=0)
    ids = pending_for_enrichment(limit=1)
    assert Product.objects.get(slug="instock").id == ids[0]
```

- [ ] **Step 2: Запустить — упадёт**

Run: `pytest apps/catalog/tests/test_enrichment_apply.py -v`
Expected: FAIL (нет модуля).

- [ ] **Step 3: Реализация**

```python
# apps/catalog/enrichment.py
"""Применение AI-результата к каталогу — единственная точка записи enrich.

apps/ai сюда делегирует чтение и запись (граница ADR-0004: ai не трогает таблицы
каталога напрямую). Правила: content_locked неприкосновенен; карточные поля
пишутся только в пустоту (или при force); PAV source=llm — только в пробел или
поверх llm (низший приоритет провенанса); attrs_cache пересобирается.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import (Attribute, AttributeType, ContentSource, EnrichStatus, Product,
                     ProductAttributeValue, Source)
from .read_models import rebuild_attrs_cache

MODERATION_THRESHOLD = 0.7
LLM_CONFIDENCE_DEFAULT = 60
_VALUE_FIELDS = ["value_text", "value_integer", "value_decimal", "value_boolean",
                 "value_option"]


@dataclass
class AiAttr:
    slug: str
    value: object
    confidence: int = LLM_CONFIDENCE_DEFAULT


def get_enrichable_product(pk: int) -> Product | None:
    """Товар по pk для обогащения (в т.ч. неопубликованный)."""
    return Product.objects.filter(pk=pk).select_related("category").first()


def pending_for_enrichment(*, category_slug: str | None = None, limit: int = 100,
                           only_empty: bool = True) -> list[int]:
    """id товаров для батча: pending, не locked, приоритет available_quantity>0."""
    qs = Product.objects.filter(content_locked=False, enrich_status=EnrichStatus.PENDING)
    if only_empty:
        qs = qs.filter(description="")
    if category_slug:
        qs = qs.filter(category__slug=category_slug)
    return list(qs.order_by("-available_quantity", "id")
               .values_list("id", flat=True)[:limit])


def _set_typed_value(pav: ProductAttributeValue, attr: Attribute, value) -> bool:
    for f in _VALUE_FIELDS:
        setattr(pav, f, None)
    pav.value_text = ""
    try:
        if attr.attribute_type == AttributeType.INTEGER:
            pav.value_integer = int(value)
        elif attr.attribute_type == AttributeType.DECIMAL:
            pav.value_decimal = Decimal(str(value))
        elif attr.attribute_type == AttributeType.BOOLEAN:
            pav.value_boolean = bool(value)
        else:  # TEXT (SELECT/MULTISELECT из LLM в этой итерации не поддерживаем)
            pav.value_text = str(value)
    except (TypeError, ValueError, InvalidOperation):
        return False
    return True


def _apply_attributes(product: Product, attributes: list[AiAttr]) -> list[str]:
    updated: list[str] = []
    for ai_attr in attributes:
        attr = Attribute.objects.filter(slug=ai_attr.slug).first()
        if attr is None or attr.attribute_type in (AttributeType.SELECT,
                                                   AttributeType.MULTISELECT):
            continue
        existing = ProductAttributeValue.objects.filter(product=product,
                                                        attribute=attr).first()
        if existing is not None and existing.source != Source.LLM:
            continue  # llm — низший приоритет: не затираем manual/1c/regex/keyword
        pav = existing or ProductAttributeValue(product=product, attribute=attr)
        if not _set_typed_value(pav, attr, ai_attr.value):
            continue
        pav.source = Source.LLM
        pav.confidence = max(0, min(100, ai_attr.confidence))
        pav.save()
        updated.append(ai_attr.slug)
    return updated


@transaction.atomic
def apply_ai_enrichment(product: Product, *, name=None, short_description=None,
                        description=None, attributes: list[AiAttr] = (),
                        confidence: float | None = None, force: bool = False) -> dict:
    if product.content_locked and not force:
        return {"locked": True, "fields_updated": []}

    fields: list[str] = []
    if name and (force or not product.name):
        product.name = name
        fields.append("name")
    if short_description and (force or not product.short_description):
        product.short_description = short_description
        fields.append("short_description")
    if description and (force or not product.description):
        product.description = description
        fields.append("description")

    attr_updated = _apply_attributes(product, list(attributes))

    product.content_source = ContentSource.LLM
    product.content_confidence = confidence
    if confidence is not None and confidence < MODERATION_THRESHOLD:
        product.enrich_status = EnrichStatus.MODERATION
    else:
        product.enrich_status = EnrichStatus.DONE
    product.save(update_fields=["name", "short_description", "description",
                                "content_source", "content_confidence", "enrich_status"])
    if attr_updated:
        rebuild_attrs_cache(product)
    return {"locked": False, "fields_updated": fields + attr_updated,
            "status": product.enrich_status}
```

- [ ] **Step 4: Прогнать**

Run: `pytest apps/catalog/tests/test_enrichment_apply.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/catalog/enrichment.py apps/catalog/tests/test_enrichment_apply.py
git commit -m "feat(enrich): catalog.enrichment — применение AI-результата (граница ADR-0004)"
```

---

## Task 6: `ai.services.enrich()` — оркестрация

**Files:**
- Modify: `apps/ai/services.py`
- Test: `apps/ai/tests/test_enrich_service.py`

**Interfaces:**
- Consumes: `catalog.enrichment.{get_enrichable_product, apply_ai_enrichment, AiAttr}`, `ports.{get_provider, ModelCall}`, `guardrails.{parse_enrich_output, EnrichResult}`, `models.AiCallLog`.
- Produces: `def enrich(*, product_id: int, force: bool = False) -> EnrichResult` (при пропуске/ошибке — `EnrichResult` с `source="fallback"`).

- [ ] **Step 1: Тесты сервиса**

```python
# apps/ai/tests/test_enrich_service.py
import pytest

from apps.ai.models import AiCallLog
from apps.ai.services import enrich
from apps.catalog.models import Category, Product, ProductStatus


def _product(**kw):
    cat = Category.objects.first() or Category.add_root(name="Перфораторы", slug="perf")
    data = dict(category=cat, name="", slug="p1", description="",
                original_name="Перфоратор HR2470 Makita 780Вт",
                status=ProductStatus.IMPORTED, is_active=False, price="1000")
    data.update(kw)
    return Product.objects.create(**data)


@pytest.mark.django_db
def test_enrich_fills_card_and_logs():
    p = _product()
    res = enrich(product_id=p.pk)
    assert res.source == "llm"
    p.refresh_from_db()
    assert p.name and p.description
    log = AiCallLog.objects.get(entity_ref=p.pk, capability=AiCallLog.Capability.ENRICH)
    assert log.status == AiCallLog.Status.OK


@pytest.mark.django_db
def test_enrich_respects_content_locked():
    p = _product(slug="p2", content_locked=True)
    res = enrich(product_id=p.pk)
    p.refresh_from_db()
    assert p.name == "" and res.source == "fallback"
    log = AiCallLog.objects.get(entity_ref=p.pk)
    assert log.status == AiCallLog.Status.FALLBACK and log.reason == "content_locked"


@pytest.mark.django_db
def test_enrich_missing_product_returns_fallback():
    res = enrich(product_id=999999)
    assert res.source == "fallback"
```

- [ ] **Step 2: Запустить — упадёт**

Run: `pytest apps/ai/tests/test_enrich_service.py -v`
Expected: FAIL (нет `enrich`).

- [ ] **Step 3: Добавить `enrich` в `apps/ai/services.py`**

Импорты в начало файла (рядом с существующими):

```python
from apps.catalog.enrichment import (AiAttr, apply_ai_enrichment,
                                     get_enrichable_product)

from .guardrails import EnrichResult, parse_enrich_output
from .models import AiCallLog
from .ports import ModelCall, get_provider

ENRICH_SYSTEM = (
    "Ты — ассистент интернет-магазина инструментов. По данным из учётной системы "
    "1С сформируй структурированный контент карточки. Отвечай ТОЛЬКО валидным JSON "
    "без markdown и пояснений."
)


def _fallback() -> EnrichResult:
    return EnrichResult(name=None, short_description=None, description=None,
                        attributes=[], confidence=0.0, source="fallback")
```

Тело функции:

```python
def enrich(*, product_id: int, force: bool = False) -> EnrichResult:
    """Гибрид: детерминированный слой уже наполнил EAV; здесь LLM добивает
    карточный текст и пробелы. Запись — через catalog.enrichment (граница ADR).
    Любой сбой → fallback (деградация без исключения), всегда пишем AiCallLog.
    """
    product = get_enrichable_product(product_id)
    if product is None:
        AiCallLog.objects.create(capability=AiCallLog.Capability.ENRICH,
                                 status=AiCallLog.Status.ERROR, entity_ref=product_id,
                                 reason="product_not_found")
        return _fallback()

    if product.content_locked and not force:
        AiCallLog.objects.create(capability=AiCallLog.Capability.ENRICH,
                                 status=AiCallLog.Status.FALLBACK, entity_ref=product_id,
                                 reason="content_locked")
        return _fallback()

    provider = get_provider()
    user = (product.original_name or product.name or "").strip()
    call = ModelCall(system=ENRICH_SYSTEM, user=user)
    try:
        reply = provider.complete(call)
    except Exception as exc:  # noqa: BLE001 — деградация: любой сбой провайдера
        AiCallLog.objects.create(capability=AiCallLog.Capability.ENRICH,
                                 provider=getattr(provider, "name", ""),
                                 status=AiCallLog.Status.ERROR, entity_ref=product_id,
                                 reason=str(exc)[:255])
        return _fallback()

    result = parse_enrich_output(reply.text)
    if result is None:
        AiCallLog.objects.create(capability=AiCallLog.Capability.ENRICH,
                                 provider=reply.provider, model=reply.model,
                                 status=AiCallLog.Status.FALLBACK, entity_ref=product_id,
                                 reason="invalid_output", tokens_in=reply.tokens_in,
                                 tokens_out=reply.tokens_out)
        return _fallback()

    apply_ai_enrichment(
        product, name=result.name, short_description=result.short_description,
        description=result.description,
        attributes=[AiAttr(slug=a.slug, value=a.value, confidence=a.confidence)
                    for a in result.attributes],
        confidence=result.confidence, force=force,
    )
    AiCallLog.objects.create(capability=AiCallLog.Capability.ENRICH,
                             provider=reply.provider, model=reply.model,
                             status=AiCallLog.Status.OK, entity_ref=product_id,
                             output=reply.text[:2000], tokens_in=reply.tokens_in,
                             tokens_out=reply.tokens_out)
    return result
```

- [ ] **Step 4: Прогнать**

Run: `pytest apps/ai/tests/test_enrich_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/ai/services.py apps/ai/tests/test_enrich_service.py
git commit -m "feat(enrich): ai.services.enrich — оркестрация гибридного обогащения"
```

---

## Task 7: Celery-задачи + receivers + ready() под флагом

**Files:**
- Create: `apps/ai/tasks.py`, `apps/ai/receivers.py`
- Modify: `apps/ai/apps.py`
- Test: `apps/ai/tests/test_tasks.py`

**Interfaces:**
- Consumes: `services.enrich`, `catalog.enrichment.pending_for_enrichment`, `apps.core.events.product_created`.
- Produces:
  - `@shared_task enrich_product_task(product_id: int, force: bool = False)`
  - `@shared_task batch_enrich_task(category_slug=None, limit=100, only_empty=True) -> int` (число поставленных задач).

- [ ] **Step 1: Тесты задач (eager)**

```python
# apps/ai/tests/test_tasks.py
import pytest
from django.test import override_settings

from apps.ai.tasks import batch_enrich_task, enrich_product_task
from apps.catalog.models import Category, Product, ProductStatus


def _p(slug, *, stock, **kw):
    cat = Category.objects.first() or Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(category=cat, name="", slug=slug, description="",
                                  original_name="Перфоратор " + slug,
                                  status=ProductStatus.IMPORTED, is_active=False,
                                  price="1000", available_quantity=stock, **kw)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
@pytest.mark.django_db
def test_enrich_product_task_runs():
    p = _p("a", stock=5)
    enrich_product_task(p.pk)
    p.refresh_from_db()
    assert p.name


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
@pytest.mark.django_db
def test_batch_prioritizes_in_stock_and_limits():
    _p("instock", stock=10)
    _p("nostock", stock=0)
    n = batch_enrich_task(limit=1, only_empty=True)
    assert n == 1
    assert Product.objects.get(slug="instock").name != ""
    assert Product.objects.get(slug="nostock").name == ""
```

- [ ] **Step 2: Запустить — упадёт**

Run: `pytest apps/ai/tests/test_tasks.py -v`
Expected: FAIL (нет `tasks`).

- [ ] **Step 3: tasks.py**

```python
# apps/ai/tasks.py
"""Celery-runtime обогащения (ARCHITECTURE-AI §5, runtime-срез)."""
from __future__ import annotations

from celery import shared_task

from apps.catalog.enrichment import pending_for_enrichment

from .services import enrich


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def enrich_product_task(self, product_id: int, force: bool = False):
    enrich(product_id=product_id, force=force)


@shared_task
def batch_enrich_task(category_slug: str | None = None, limit: int = 100,
                      only_empty: bool = True) -> int:
    ids = pending_for_enrichment(category_slug=category_slug, limit=limit,
                                 only_empty=only_empty)
    for pid in ids:
        enrich_product_task.delay(pid)
    return len(ids)
```

- [ ] **Step 4: receivers.py**

```python
# apps/ai/receivers.py
"""Подписка AI на доменные события (ARCHITECTURE-AI §5).

Подключается в AiConfig.ready() ТОЛЬКО под флагом ``ai``. Импортёр 1С эмит не
шлёт — 1С-товары идут батчем; подписка обслуживает admin/API-создание товаров.
"""
from __future__ import annotations

from django.db import transaction

from apps.core.events import product_created

from .tasks import enrich_product_task


def on_product_created(sender, product_id, **kwargs):
    transaction.on_commit(lambda: enrich_product_task.delay(product_id))


def connect():
    product_created.connect(on_product_created, dispatch_uid="ai.enrich.product_created")
```

- [ ] **Step 5: ready() под флагом**

```python
# apps/ai/apps.py
from django.apps import AppConfig


class AiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    verbose_name = "AI-слой (рекомендации, обогащение)"

    def ready(self):
        from apps.core.features import is_enabled

        if is_enabled("ai"):
            from . import receivers

            receivers.connect()
```

- [ ] **Step 6: Прогнать**

Run: `pytest apps/ai/tests/test_tasks.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/ai/tasks.py apps/ai/receivers.py apps/ai/apps.py apps/ai/tests/test_tasks.py
git commit -m "feat(enrich): Celery-задачи, receivers и ready() под флагом ai"
```

---

## Task 8: Очередь модерации в admin

**Files:**
- Modify: `apps/catalog/models.py` (proxy `ModerationProduct`)
- Create: `apps/catalog/migrations/0020_moderationproduct.py`
- Modify: `apps/ai/admin.py`
- Test: `apps/ai/tests/test_admin_moderation.py`

**Interfaces:**
- Produces: `catalog.models.ModerationProduct` (proxy Product); admin-действия `approve_content`, `reject_and_reenrich`.

- [ ] **Step 1: Тест действий**

```python
# apps/ai/tests/test_admin_moderation.py
import pytest

from apps.ai.admin import ModerationQueueAdmin
from apps.catalog.models import (Category, EnrichStatus, ModerationProduct, Product,
                                 ProductStatus)


def _p():
    cat = Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(category=cat, name="X", slug="x", description="d",
                                  status=ProductStatus.IMPORTED, is_active=False,
                                  price="1000", enrich_status=EnrichStatus.MODERATION,
                                  content_confidence=0.5)


@pytest.mark.django_db
def test_approve_locks_and_marks_done():
    p = _p()
    admin = ModerationQueueAdmin(ModerationProduct, None)
    admin.approve_content(None, ModerationProduct.objects.filter(pk=p.pk))
    p.refresh_from_db()
    assert p.enrich_status == EnrichStatus.DONE and p.content_locked is True


@pytest.mark.django_db
def test_queue_shows_only_moderation():
    _p()
    admin = ModerationQueueAdmin(ModerationProduct, None)
    qs = admin.get_queryset(type("R", (), {"GET": {}})())
    assert qs.count() == 1
```

- [ ] **Step 2: Запустить — упадёт**

Run: `pytest apps/ai/tests/test_admin_moderation.py -v`
Expected: FAIL.

- [ ] **Step 3: proxy-модель в catalog**

В конце `apps/catalog/models.py`:

```python
class ModerationProduct(Product):
    """Proxy для очереди модерации обогащения в admin."""

    class Meta:
        proxy = True
        verbose_name = _("Товар на модерации")
        verbose_name_plural = _("Очередь модерации обогащения")
```

Run: `python manage.py makemigrations catalog --name moderationproduct`
Expected: `0020_moderationproduct.py` (proxy).

- [ ] **Step 4: admin-очередь**

В `apps/ai/admin.py` добавить:

```python
from django.contrib import messages

from apps.catalog.models import EnrichStatus, ModerationProduct


@admin.register(ModerationProduct)
class ModerationQueueAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "enrich_status", "content_source",
                    "content_confidence", "available_quantity")
    list_filter = ("content_source", "category")
    search_fields = ("name", "original_name", "article")
    actions = ["approve_content", "reject_and_reenrich"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(enrich_status=EnrichStatus.MODERATION)

    @admin.action(description="Одобрить контент (lock + done)")
    def approve_content(self, request, queryset):
        n = queryset.update(enrich_status=EnrichStatus.DONE, content_locked=True)
        if request is not None:
            self.message_user(request, f"Одобрено: {n}", messages.SUCCESS)

    @admin.action(description="Отклонить и переобогатить")
    def reject_and_reenrich(self, request, queryset):
        for product in queryset:
            product.description = ""
            product.short_description = ""
            product.enrich_status = EnrichStatus.PENDING
            product.save(update_fields=["description", "short_description", "enrich_status"])
```

- [ ] **Step 5: Прогнать**

Run: `python manage.py migrate catalog && pytest apps/ai/tests/test_admin_moderation.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/ai/admin.py apps/catalog/models.py apps/catalog/migrations/0020_moderationproduct.py apps/ai/tests/test_admin_moderation.py
git commit -m "feat(enrich): очередь модерации обогащения в admin"
```

---

## Task 9: CLI — enrich_product, enrich_catalog, enrich_report

**Files:**
- Create: `apps/ai/management/__init__.py`, `apps/ai/management/commands/__init__.py`
- Create: `apps/ai/management/commands/{enrich_product,enrich_catalog,enrich_report}.py`
- Test: `apps/ai/tests/test_commands.py`

**Interfaces:**
- Consumes: `services.enrich`, `catalog.enrichment.pending_for_enrichment`, `Product`, `EnrichStatus`, `ContentSource`.
- Produces: команды `enrich_product`, `enrich_catalog`, `enrich_report`.

- [ ] **Step 1: Тесты команд**

```python
# apps/ai/tests/test_commands.py
import pytest
from django.core.management import call_command

from apps.catalog.models import Category, Product, ProductStatus


def _p(slug, **kw):
    cat = Category.objects.first() or Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(category=cat, name="", slug=slug, description="",
                                  original_name="Перфоратор " + slug,
                                  status=ProductStatus.IMPORTED, is_active=False,
                                  price="1000", **kw)


@pytest.mark.django_db
def test_enrich_product_by_id():
    p = _p("a")
    call_command("enrich_product", "--id", str(p.pk))
    p.refresh_from_db()
    assert p.name


@pytest.mark.django_db
def test_enrich_catalog_dry_run_writes_nothing():
    _p("a", available_quantity=5)
    call_command("enrich_catalog", "--all", "--limit", "5", "--dry-run")
    assert Product.objects.get(slug="a").name == ""


@pytest.mark.django_db
def test_enrich_report_runs(capsys):
    _p("a")
    call_command("enrich_report")
    out = capsys.readouterr().out
    assert "Ожидает" in out
```

- [ ] **Step 2: Запустить — упадёт**

Run: `pytest apps/ai/tests/test_commands.py -v`
Expected: FAIL (нет команд).

- [ ] **Step 3: enrich_product**

```python
# apps/ai/management/commands/enrich_product.py
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.enrichment import get_enrichable_product

from ...services import enrich


class Command(BaseCommand):
    help = "Обогатить конкретный товар (для отладки)"

    def add_arguments(self, parser):
        parser.add_argument("--id", type=int)
        parser.add_argument("--article", type=str)
        parser.add_argument("--code-1c", type=str, dest="code_1c")
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--verbose", action="store_true")

    def handle(self, *args, **o):
        from apps.catalog.models import Product
        if o.get("id"):
            product = get_enrichable_product(o["id"])
        elif o.get("article"):
            product = Product.objects.filter(article=o["article"]).first()
        elif o.get("code_1c"):
            product = Product.objects.filter(code_1c=o["code_1c"]).first()
        else:
            raise CommandError("укажите --id / --article / --code-1c")
        if product is None:
            raise CommandError("товар не найден")
        result = enrich(product_id=product.pk, force=o["force"])
        self.stdout.write(f"source={result.source} confidence={result.confidence}")
        if o["verbose"]:
            self.stdout.write(f"name={result.name!r}\ndesc={result.description!r}")
```

> Примечание: команды (`management/`) — допустимое место для чтения `Product.objects` (CLI-утилита уровня каталога), это исключение в тесте границ Task 11.

- [ ] **Step 4: enrich_catalog**

```python
# apps/ai/management/commands/enrich_catalog.py
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.enrichment import pending_for_enrichment

from ...services import enrich


class Command(BaseCommand):
    help = "Батч-обогащение каталога (приоритет: available_quantity > 0)"

    def add_arguments(self, parser):
        parser.add_argument("--category", type=str)
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **o):
        if not o["category"] and not o["all"]:
            raise CommandError("укажите --category SLUG или --all")
        ids = pending_for_enrichment(category_slug=o["category"], limit=o["limit"])
        self.stdout.write(f"К обработке: {len(ids)}")
        if o["dry_run"] or not o["commit"]:
            self.stdout.write("dry-run — ничего не записано (добавьте --commit)")
            return
        for pid in ids:
            enrich(product_id=pid, force=o["force"])
        self.stdout.write(self.style.SUCCESS(f"Обогащено: {len(ids)}"))
```

- [ ] **Step 5: enrich_report**

```python
# apps/ai/management/commands/enrich_report.py
from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.catalog.models import ContentSource, EnrichStatus, Product


class Command(BaseCommand):
    help = "Отчёт по статусам обогащения"

    def handle(self, *args, **o):
        total = Product.objects.count() or 1
        self.stdout.write(f"Всего товаров: {total}")
        by_status = dict(Product.objects.values_list("enrich_status")
                         .annotate(n=Count("id")).values_list("enrich_status", "n"))
        for status in EnrichStatus:
            n = by_status.get(status.value, 0)
            self.stdout.write(f"  {status.label}: {n} ({100 * n // total}%)")
        self.stdout.write("Источники готовых:")
        for src in ContentSource.values:
            n = Product.objects.filter(content_source=src,
                                       enrich_status=EnrichStatus.DONE).count()
            self.stdout.write(f"  {src}: {n}")
        self.stdout.write(f"Без описания: {Product.objects.filter(description='').count()}")
```

(+ пустые `apps/ai/management/__init__.py` и `apps/ai/management/commands/__init__.py`.)

> Примечание: `EnrichStatus.PENDING.label == "Ожидает"` — тест `test_enrich_report_runs` ищет «Ожидает» в выводе.

- [ ] **Step 6: Прогнать**

Run: `pytest apps/ai/tests/test_commands.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/ai/management apps/ai/tests/test_commands.py
git commit -m "feat(enrich): CLI enrich_product/enrich_catalog/enrich_report"
```

---

## Task 10: ImagePipeline (минимальная инфраструктура)

**Files:**
- Create: `apps/catalog/image_pipeline.py`
- Modify: `requirements/base.txt` (если нет `Pillow`/`requests`)
- Test: `apps/catalog/tests/test_image_pipeline.py`

**Interfaces:**
- Consumes: `Product`, `ProductImage`, `requests`, `PIL.Image`.
- Produces:
  - `class ImagePipeline` (`MAX_SIZE=(1200,1200)`, `THUMB_SIZE=(400,400)`, `QUALITY=85`)
  - `process_url(self, product, url, *, is_main=False, source="manual") -> ProductImage | None`
  - `process_batch(self, product, urls: list[str]) -> list[ProductImage]`
  - `_process_bytes(self, raw: bytes) -> tuple[ContentFile, ContentFile] | None`
  - `_download(self, url) -> bytes | None`

- [ ] **Step 1: Проверить зависимости**

Проверить `requirements/base.txt` на `Pillow` и `requests`. `Pillow` нужен для `ImageField` в любом случае; если отсутствует — добавить `Pillow>=10`. `requests` уже используется в проекте — подтвердить. Изменения зафиксировать в коммите задачи.

- [ ] **Step 2: Тест обработки байтов (без сети)**

```python
# apps/catalog/tests/test_image_pipeline.py
import io

import pytest
from PIL import Image

from apps.catalog.image_pipeline import ImagePipeline
from apps.catalog.models import Category, Product, ProductStatus


def _png_bytes(w=1500, h=1500):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _product(**kw):
    cat = Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(category=cat, name="X", slug="x",
                                  status=ProductStatus.IMPORTED, is_active=False,
                                  price="1000", **kw)


def test_process_bytes_resizes_and_thumbs():
    main, thumb = ImagePipeline()._process_bytes(_png_bytes())
    assert Image.open(io.BytesIO(main.read())).size[0] <= 1200
    assert Image.open(io.BytesIO(thumb.read())).size[0] <= 400


def test_process_bytes_rejects_non_image():
    assert ImagePipeline()._process_bytes(b"not-an-image") is None


@pytest.mark.django_db
def test_content_locked_blocks(monkeypatch):
    p = _product(content_locked=True)
    pipe = ImagePipeline()
    monkeypatch.setattr(pipe, "_download", lambda url: _png_bytes())
    assert pipe.process_url(p, "http://x/y.png") is None
    assert p.images.count() == 0


@pytest.mark.django_db
def test_process_url_idempotent(monkeypatch):
    p = _product()
    pipe = ImagePipeline()
    monkeypatch.setattr(pipe, "_download", lambda url: _png_bytes())
    a = pipe.process_url(p, "http://x/y.png")
    b = pipe.process_url(p, "http://x/y.png")
    assert a.pk == b.pk and p.images.count() == 1
```

- [ ] **Step 3: Запустить — упадёт**

Run: `pytest apps/catalog/tests/test_image_pipeline.py -v`
Expected: FAIL (нет модуля).

- [ ] **Step 4: Реализация**

```python
# apps/catalog/image_pipeline.py
"""Минимальный pipeline изображений: скачать → валидировать → ресайз → WebP → thumb.

Вызывается вручную (admin/CLI). Enrich-поток фото не тянет. Идемпотентность —
по URL (хранится в alt-маркере). content_locked уважается.
"""
from __future__ import annotations

import io
import logging

import requests
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

from .models import Product, ProductImage

log = logging.getLogger(__name__)


class ImagePipeline:
    MAX_SIZE = (1200, 1200)
    THUMB_SIZE = (400, 400)
    QUALITY = 85
    TIMEOUT = 10
    MIN_SIDE = 100
    MAX_BYTES = 10 * 1024 * 1024

    def _download(self, url: str) -> bytes | None:
        try:
            r = requests.get(url, timeout=self.TIMEOUT)
            r.raise_for_status()
        except requests.RequestException as exc:
            log.warning("image download failed %s: %s", url, exc)
            return None
        return r.content if len(r.content) <= self.MAX_BYTES else None

    def _process_bytes(self, raw: bytes):
        try:
            img = Image.open(io.BytesIO(raw))
            img.load()
        except (OSError, ValueError):
            return None
        if min(img.size) < self.MIN_SIDE:
            return None
        img = ImageOps.exif_transpose(img).convert("RGB")  # снимаем EXIF

        main_img = img.copy()
        main_img.thumbnail(self.MAX_SIZE)
        main_buf = io.BytesIO()
        main_img.save(main_buf, format="WEBP", quality=self.QUALITY)

        thumb_img = img.copy()
        thumb_img.thumbnail(self.THUMB_SIZE)
        thumb_buf = io.BytesIO()
        thumb_img.save(thumb_buf, format="WEBP", quality=self.QUALITY)
        return ContentFile(main_buf.getvalue()), ContentFile(thumb_buf.getvalue())

    def process_url(self, product: Product, url: str, *, is_main: bool = False,
                    source: str = "manual") -> ProductImage | None:
        if product.content_locked:
            return None
        existing = product.images.filter(alt=url).first()  # идемпотентность по URL
        if existing is not None:
            return existing
        raw = self._download(url)
        if raw is None:
            return None
        processed = self._process_bytes(raw)
        if processed is None:
            return None
        main_file, _thumb = processed
        first = not product.images.exists()
        image = ProductImage(product=product, alt=url, is_main=is_main or first)
        image.image.save(f"products/{product.pk}/{abs(hash(url)) % 10**8}.webp",
                         main_file, save=True)
        return image

    def process_batch(self, product: Product, urls: list[str]) -> list[ProductImage]:
        out: list[ProductImage] = []
        for i, url in enumerate(urls):
            img = self.process_url(product, url, is_main=(i == 0))
            if img is not None:
                out.append(img)
        return out
```

- [ ] **Step 5: Прогнать**

Run: `pytest apps/catalog/tests/test_image_pipeline.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/catalog/image_pipeline.py apps/catalog/tests/test_image_pipeline.py requirements/base.txt
git commit -m "feat(enrich): минимальный ImagePipeline (скачивание/ресайз/WebP/thumb)"
```

---

## Task 11: Проверка границ ADR-0004 + зелёный DoD

**Files:**
- Test: `apps/ai/tests/test_boundaries.py`

- [ ] **Step 1: Тест отсутствия прямых обращений к чужим objects**

```python
# apps/ai/tests/test_boundaries.py
import pathlib
import re

AI_DIR = pathlib.Path(__file__).resolve().parents[1]
_BANNED = re.compile(r"\b(Product|ProductAttributeValue|Category)\.objects\b")


def test_no_direct_catalog_objects_in_ai_core():
    """Ядро apps/ai (services/tasks/receivers/ports/guardrails/providers) не лезет
    в objects каталога. Исключения: tests/ и management/ (CLI уровня каталога)."""
    offenders = []
    for path in AI_DIR.rglob("*.py"):
        parts = path.parts
        if "tests" in parts or "management" in parts or "migrations" in parts:
            continue
        if _BANNED.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path))
    assert not offenders, f"Прямой доступ к objects каталога: {offenders}"
```

- [ ] **Step 2: Прогнать тест границ**

Run: `pytest apps/ai/tests/test_boundaries.py -v`
Expected: PASS (ядро `apps/ai` пишет/читает каталог только через `catalog.enrichment`).

- [ ] **Step 3: Полный прогон**

Run: `pytest apps/ai/ apps/catalog/ -x`
Expected: все зелёные.

- [ ] **Step 4: Линтеры**

Run: `ruff check apps/ai apps/catalog && black --check apps/ai apps/catalog`
Expected: чисто (миграции исключены конфигом).

- [ ] **Step 5: Commit**

```bash
git add apps/ai/tests/test_boundaries.py
git commit -m "test(enrich): проверка границ ADR-0004 + зелёный DoD"
```

---

## Self-Review (выполнено автором плана)

**Покрытие спеки:** §3 модель данных → T1 (Product) + T2 (AiCallLog); §4 enrich-поток → T5 (apply) + T6 (оркестрация); §5 порт/провайдеры → T3; §6 guardrails → T4; §7 runtime → T7; §8 admin+CLI → T8 + T9; §9 ImagePipeline → T10; §10 тесты → распределены по задачам + T11; §11 порядок/DoD → T1→T11.

**Отклонение от спеки (осознанное):** запись результата вынесена из `ai.services` в `catalog.enrichment` (граница ADR-0004) — спека §4 «применить» реализуется делегацией в каталог. `claude.py` — каркас (решение итерации: dummy). Батч-выборка вынесена в `catalog.enrichment.pending_for_enrichment`, чтобы `tasks.py` не трогал `Product.objects` (проходит тест границ T11).

**Типы согласованы:** `EnrichResult`/`EnrichedAttr` (guardrails) → `AiAttr` (catalog) маппятся в T6; `ModelCall`/`ModelReply` едины в ports/providers/services; имена из catalog.models реальные (`attribute_type` не `kind`; `Source.LLM`; `available_quantity`; миграция от `0018_...`).

**Плейсхолдеров нет:** каждый шаг содержит готовый код/команду и ожидаемый результат.
