# Capability `sourcing` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить capability `sourcing` — поиск реального контента карточки во внешних источниках (web-поиск + API маркетплейсов) с обязательной модерацией и аудитом.

**Architecture:** Источники за портом (`ContentSourcePort`) копят находки (`ContentFinding` + `FindingEvidence`), товар не меняется. Модератор выбирает evidence → AI оркестрирует применение через нейтральный catalog-owned DTO `apply_sourced_value` (зависимость `ai → catalog` не разворачивается). Всё под флагами `ai`/`ai_sourcing`/`external_integrations`.

**Tech Stack:** Django 5 + DRF, PostgreSQL (JSONB/constraints/`select_for_update`), Celery + Redis, pytest. Спека: `docs/superpowers/specs/2026-06-29-capability-sourcing-design.md`.

## Global Constraints

- Общение/комментарии/коммиты — **на русском**. Подпись коммита: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **ADR-0004:** в `apps/ai` запрещены прямые `Product.objects`/`ProductAttributeValue.objects`/`Category.objects` (кроме `tests/`, `management/`, `migrations/`). Чтение каталога — через сервисы; запись — только через `catalog.provenance.apply_sourced_value`. Каталог **не импортирует** `apps/ai`.
- **Провенанс — одна карта** в `data/attribute_rules.json` → `source_priority`. Резолвер один: `catalog.provenance.can_overwrite`.
- **LLM/внешний вывод — недоверенный ввод.** Применить цену/остаток/статус заказа физически нельзя. `content_locked=True` — абсолютная защита.
- Среда тестов — **Docker**: `docker compose exec -T web ...` (PostgreSQL обязателен). Lint-гейт: `ruff check` + `black --check` по затронутым путям.
- Каждая задача — **отдельная короткая ветка от свежего `dev`** (`feature/sourcing-<кратко>`), отдельный PR. **НЕ** делать `git merge/pull/rebase/checkout` других веток внутри задачи.
- Каноническая карта приоритетов (verbatim): `manual 100 > import_1c 60 > regex 40 > keyword 30 > llm 20 > inferred 10`; добавляем `web 25`, `marketplace 25`.

---

## Файловая карта

| Путь | Ответственность | Задача |
|---|---|---|
| `apps/catalog/provenance.py` | резолвер приоритетов + DTO + `apply_sourced_value` | 1 |
| `apps/catalog/models.py` | `Source`/`ContentSource` (+web,marketplace), `Product.content_field_sources` | 1 |
| `data/attribute_rules.json` | `source_priority`: +web,marketplace | 1 |
| `apps/ai/models.py` | `SourcingRun`/`ExternalCall`/`ContentFinding`/`FindingEvidence`/`FindingApplicationAttempt`/`SourcingBudget` | 2 |
| `apps/ai/sourcing/ports.py` | `SourceQuery`/`Finding`/`SourceReply`/`ContentSourcePort` | 3 |
| `apps/ai/sourcing/guardrails.py` | валидация находок (недоверенный ввод) | 3 |
| `apps/ai/sourcing/sources/{__init__,dummy}.py` | реестр источников + тестовый dummy | 3 |
| `apps/ai/services.py` | `source_content`, `approve_and_apply_finding` | 4 |
| `apps/ai/tasks.py` | Celery: source/batch/janitor/retention | 5 |
| `apps/ai/apps.py`, `config/settings/*` | флаг `ai_sourcing` | 5 |
| `apps/ai/admin.py` | очередь находок + review-форма + bulk | 6 |
| `apps/ai/management/commands/source_*.py` | CLI | 7 |
| `apps/ai/sourcing/sources/{web_search,marketplace}.py` | реальные адаптеры (за ключами) | 8 |
| `config/celery.py` | beat-расписание ночного `batch_source_task` (триггер 1С-импорта) | 9 |

---

## Task 1: `catalog.provenance` — резолвер, DTO, применение

**Files:**
- Create: `apps/catalog/provenance.py`
- Modify: `apps/catalog/models.py` (enum `Source`, `ContentSource`, поле `Product.content_field_sources`)
- Modify: `data/attribute_rules.json` (`source_priority`: +`web`,+`marketplace`)
- Create: миграция `apps/catalog/migrations/00XX_sourcing_provenance.py` (поля + data-migration backfill)
- Test: `apps/catalog/tests/test_provenance.py`

**Interfaces (Produces):**
- `Source.WEB="web"`, `Source.MARKETPLACE="marketplace"`; `ContentSource.WEB`, `ContentSource.MARKETPLACE`.
- `provenance.can_overwrite(new: str, existing: str, *, allow_equal: bool = False) -> bool`
- `provenance.SourcedValueCommand` (dataclass, поля §5.1 спеки) и `provenance.ApplyResult(status: str, reason: str = "")`
- `provenance.apply_sourced_value(cmd: SourcedValueCommand) -> ApplyResult`
- `provenance.value_hash(value) -> str`
- `Product.content_field_sources: dict` (JSON, default `{}`)

- [ ] **Step 1: Расширить enum + поле в `apps/catalog/models.py`**

В `class Source` добавить после `INFERRED`:
```python
    WEB = "web", _("Web-поиск")
    MARKETPLACE = "marketplace", _("Маркетплейс")
```
В `class ContentSource` добавить после `LLM`:
```python
    WEB = "web", _("Web-поиск")
    MARKETPLACE = "marketplace", _("Маркетплейс")
```
В `class Product` рядом с `content_source` добавить:
```python
    content_field_sources = models.JSONField(
        _("Провенанс карточных полей"), default=dict, blank=True,
        help_text="{'name':'manual','description':'web'} — истинный источник по полю",
    )
```

- [ ] **Step 2: Добавить web/marketplace в `data/attribute_rules.json`**

В объект `"source_priority"` добавить (значения существующих не менять):
```json
    "web": 25,
    "marketplace": 25
```

- [ ] **Step 3: Написать падающий тест** — `apps/catalog/tests/test_provenance.py`

```python
import pytest

from apps.catalog import provenance as prov
from apps.catalog.models import (Attribute, AttributeType, Category, ContentSource,
                                 Product, ProductAttributeValue, ProductStatus, Source)


def _product(**kw):
    cat = Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(category=cat, name="", slug="x", description="",
                                  short_description="", status=ProductStatus.IMPORTED,
                                  is_active=False, price="1000", **kw)


def _cmd(product, **kw):
    base = dict(product_id=product.pk, target_kind="description", attribute_slug="",
                value={"type": "text", "value": "Описание из веба"}, source="web",
                confidence=0.9, observed_value_hash=prov.value_hash(""),
                observed_source="", allow_equal_override=False)
    base.update(kw)
    return prov.SourcedValueCommand(**base)


def test_can_overwrite_strict_greater():
    assert prov.can_overwrite("web", "llm") is True          # 25 > 20
    assert prov.can_overwrite("web", "regex") is False        # 25 < 40
    assert prov.can_overwrite("web", "marketplace") is False  # равны → без allow_equal
    assert prov.can_overwrite("web", "marketplace", allow_equal=True) is True


@pytest.mark.django_db
def test_apply_text_into_empty_sets_field_provenance():
    p = _product()
    r = prov.apply_sourced_value(_cmd(p))
    p.refresh_from_db()
    assert r.status == "applied"
    assert p.description == "Описание из веба"
    assert p.content_field_sources["description"] == "web"
    assert p.content_source == ContentSource.WEB           # last-applied (текстовое поле)


@pytest.mark.django_db
def test_apply_blocked_by_content_locked():
    p = _product(content_locked=True)
    assert prov.apply_sourced_value(_cmd(p)).status == "skipped_locked"
    p.refresh_from_db()
    assert p.description == ""


@pytest.mark.django_db
def test_apply_conflict_when_baseline_changed():
    p = _product(description="старое")            # поле уже не пустое
    cmd = _cmd(p, observed_value_hash=prov.value_hash(""))  # baseline думает «было пусто»
    assert prov.apply_sourced_value(cmd).status == "conflict"


@pytest.mark.django_db
def test_apply_priority_blocked_lower_than_existing():
    p = _product(description="ручное", content_source=ContentSource.MANUAL,
                 content_field_sources={"description": "manual"})
    cmd = _cmd(p, observed_value_hash=prov.value_hash("ручное"), observed_source="manual")
    assert prov.apply_sourced_value(cmd).status == "priority_blocked"


@pytest.mark.django_db
def test_apply_attribute_does_not_touch_content_source():
    p = _product()
    attr = Attribute.objects.create(name="Мощность", slug="power",
                                    attribute_type=AttributeType.INTEGER)
    cmd = _cmd(p, target_kind="attribute", attribute_slug="power",
               value={"type": "integer", "value": 780},
               observed_value_hash=prov.value_hash(None), observed_source="")
    r = prov.apply_sourced_value(cmd)
    p.refresh_from_db()
    pav = ProductAttributeValue.objects.get(product=p, attribute=attr)
    assert r.status == "applied" and pav.value_integer == 780 and pav.source == Source.WEB
    assert p.content_source == ""                  # атрибут НЕ трогает карточный source


@pytest.mark.django_db
def test_apply_invalid_type():
    p = _product()
    Attribute.objects.create(name="Мощность", slug="power",
                             attribute_type=AttributeType.INTEGER)
    cmd = _cmd(p, target_kind="attribute", attribute_slug="power",
               value={"type": "integer", "value": "не число"},
               observed_value_hash=prov.value_hash(None), observed_source="")
    assert prov.apply_sourced_value(cmd).status == "invalid"


@pytest.mark.django_db
def test_apply_missing_product():
    cmd = prov.SourcedValueCommand(product_id=999999, target_kind="description",
        attribute_slug="", value={"type": "text", "value": "x"}, source="web",
        confidence=0.5, observed_value_hash=prov.value_hash(""), observed_source="")
    assert prov.apply_sourced_value(cmd).status == "missing_product"
```

- [ ] **Step 4: Прогнать — упадёт**

Run: `docker compose exec -T web pytest apps/catalog/tests/test_provenance.py -v`
Expected: FAIL (нет модуля `provenance`).

- [ ] **Step 5: Реализация** — `apps/catalog/provenance.py`

```python
# apps/catalog/provenance.py
"""Единый резолвер провенанса и применение «найденного» значения к каталогу.

Catalog-owned контракт: apps/ai передаёт нейтральный SourcedValueCommand, каталог
ничего не знает о ContentFinding. Карта приоритетов — единственная, из
data/attribute_rules.json (source_priority)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.db import transaction

from .models import (Attribute, AttributeType, Product, ProductAttributeValue, Source)
from .read_models import rebuild_attrs_cache

_TEXT_TARGETS = {"name", "short_description", "description"}


@lru_cache(maxsize=1)
def _priority_map() -> dict[str, int]:
    path = Path(settings.BASE_DIR) / "data" / "attribute_rules.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("source_priority", {})


def can_overwrite(new: str, existing: str, *, allow_equal: bool = False) -> bool:
    """Авто: строго priority(new) > priority(existing). Пустой existing → True.
    allow_equal=True (явное решение модератора) разрешает равный приоритет."""
    if not existing:
        return True
    pm = _priority_map()
    pn, pe = pm.get(new, 0), pm.get(existing, 0)
    return pn > pe or (allow_equal and pn == pe and pn > 0)


def value_hash(value) -> str:
    """Стабильный хеш текущего значения поля для baseline-сверки. None/'' → хеш ''."""
    return hashlib.sha256(("" if value is None else str(value)).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourcedValueCommand:
    product_id: int
    target_kind: str            # name|short_description|description|attribute
    attribute_slug: str         # "" для текстов
    value: dict                 # {"type": ..., "value": ...}
    source: str                 # Source: web|marketplace
    confidence: float
    observed_value_hash: str
    observed_source: str
    allow_equal_override: bool = False


@dataclass(frozen=True)
class ApplyResult:
    status: str   # applied|skipped_locked|conflict|priority_blocked|invalid|missing_product|missing_attribute
    reason: str = ""


def _coerce(attr_type: str, envelope: dict):
    """Типизированный конверт → значение по типу атрибута. Ошибка → ValueError."""
    raw = envelope.get("value")
    if attr_type == AttributeType.INTEGER:
        return int(raw)
    if attr_type == AttributeType.DECIMAL:
        return Decimal(str(raw))
    if attr_type == AttributeType.BOOLEAN:
        if isinstance(raw, bool):
            return raw
        raise ValueError("not a bool")
    return str(raw)  # TEXT


def _current_attr_value(pav):
    for f in ("value_integer", "value_decimal", "value_boolean", "value_option"):
        v = getattr(pav, f)
        if v is not None:
            return v
    return pav.value_text or None


@transaction.atomic
def apply_sourced_value(cmd: SourcedValueCommand) -> ApplyResult:
    product = Product.objects.select_for_update().filter(pk=cmd.product_id).first()
    if product is None:
        return ApplyResult("missing_product")
    if product.content_locked:
        return ApplyResult("skipped_locked")

    if cmd.target_kind in _TEXT_TARGETS:
        current = getattr(product, cmd.target_kind) or ""
        if value_hash(current) != cmd.observed_value_hash:
            return ApplyResult("conflict", "baseline_changed")
        existing_source = (product.content_field_sources or {}).get(cmd.target_kind, "")
        if not can_overwrite(cmd.source, existing_source, allow_equal=cmd.allow_equal_override):
            return ApplyResult("priority_blocked")
        if cmd.value.get("type") != "text":
            return ApplyResult("invalid", "text target requires type=text")
        setattr(product, cmd.target_kind, str(cmd.value.get("value")))
        fields = dict(product.content_field_sources or {})
        fields[cmd.target_kind] = cmd.source
        product.content_field_sources = fields
        product.content_source = cmd.source            # last-applied (только текст)
        product.content_confidence = cmd.confidence
        product.save(update_fields=[cmd.target_kind, "content_field_sources",
                                    "content_source", "content_confidence"])
        return ApplyResult("applied")

    # attribute
    attr = Attribute.objects.filter(slug=cmd.attribute_slug).first()
    if attr is None:
        return ApplyResult("missing_attribute")
    pav = ProductAttributeValue.objects.filter(product=product, attribute=attr).first()
    current_source = pav.source if pav else ""
    current_hash = value_hash(_current_attr_value(pav) if pav else None)
    if current_hash != cmd.observed_value_hash:
        return ApplyResult("conflict", "baseline_changed")
    if not can_overwrite(cmd.source, current_source, allow_equal=cmd.allow_equal_override):
        return ApplyResult("priority_blocked")
    try:
        coerced = _coerce(attr.attribute_type, cmd.value)
    except (TypeError, ValueError, InvalidOperation):
        return ApplyResult("invalid", "type mismatch")
    pav = pav or ProductAttributeValue(product=product, attribute=attr)
    for f in ("value_text", "value_integer", "value_decimal", "value_boolean", "value_option"):
        setattr(pav, f, None)
    pav.value_text = ""
    if attr.attribute_type == AttributeType.INTEGER:
        pav.value_integer = coerced
    elif attr.attribute_type == AttributeType.DECIMAL:
        pav.value_decimal = coerced
    elif attr.attribute_type == AttributeType.BOOLEAN:
        pav.value_boolean = coerced
    else:
        pav.value_text = coerced
    pav.source = cmd.source
    pav.confidence = max(0, min(100, int(round(cmd.confidence * 100))))
    pav.save()
    rebuild_attrs_cache(product)
    return ApplyResult("applied")
```

- [ ] **Step 6: Миграция полей + backfill**

Run: `docker compose exec -T web python manage.py makemigrations catalog --name sourcing_provenance`
Затем вписать в созданную миграцию data-migration (после AddField/AlterField), добавив `migrations.RunPython(backfill_field_sources, noop)` последней операцией:
```python
def backfill_field_sources(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    for p in Product.objects.exclude(content_source="").iterator():
        fields = {f: p.content_source for f in ("name", "short_description", "description")
                  if getattr(p, f)}
        if fields:
            p.content_field_sources = fields
            p.save(update_fields=["content_field_sources"])


def noop(apps, schema_editor):
    pass
```

- [ ] **Step 7: Прогнать — зелёные**

Run: `docker compose exec -T web python manage.py migrate catalog && docker compose exec -T web pytest apps/catalog/tests/test_provenance.py -v`
Expected: PASS (8 тестов).

- [ ] **Step 8: Lint + commit**

```bash
docker compose exec -T web ruff check apps/catalog/provenance.py apps/catalog/tests/test_provenance.py apps/catalog/models.py
docker compose exec -T web black --check apps/catalog/provenance.py apps/catalog/tests/test_provenance.py
git add apps/catalog/provenance.py apps/catalog/models.py apps/catalog/migrations/ apps/catalog/tests/test_provenance.py data/attribute_rules.json
git commit -m "feat(sourcing): catalog.provenance — резолвер приоритетов + apply_sourced_value"
```

---

## Task 2: Модели sourcing + миграция

**Files:**
- Modify: `apps/ai/models.py` (6 моделей)
- Create: миграция `apps/ai/migrations/00XX_sourcing_models.py`
- Test: `apps/ai/tests/test_sourcing_models.py`

**Interfaces (Produces):** `SourcingRun`, `ExternalCall`, `ContentFinding`, `FindingEvidence`, `FindingApplicationAttempt`, `SourcingBudget` (поля — §4 спеки). Статус-наборы: `ExternalCall.Status`, `ContentFinding.Status`, `FindingApplicationAttempt.Status`, `SourcingRun.Status` (значения строками).

**Consumes:** `catalog.Product` (FK через свою модель — разрешено), `accounts.User`.

- [ ] **Step 1: Написать падающий тест** — `apps/ai/tests/test_sourcing_models.py`

```python
import datetime as dt

import pytest
from django.db import IntegrityError, transaction

from apps.ai.models import (ContentFinding, ExternalCall, FindingApplicationAttempt,
                            FindingEvidence, SourcingBudget, SourcingRun)


@pytest.mark.django_db
def test_external_call_unique_per_run_adapter():
    run = SourcingRun.objects.create(idempotency_key="k1", product_ref=1, status="running")
    ExternalCall.objects.create(run=run, adapter="web", status="running")
    with pytest.raises(IntegrityError), transaction.atomic():
        ExternalCall.objects.create(run=run, adapter="web", status="running")


@pytest.mark.django_db
def test_finding_dedup_unique():
    f = dict(product_ref=1, target_kind="description", attribute_slug="",
             value={"type": "text", "value": "x"}, normalized_hash="h1",
             source_name="web", confidence=0.9, status="pending")
    ContentFinding.objects.create(**f)
    with pytest.raises(IntegrityError), transaction.atomic():
        ContentFinding.objects.create(**f)


@pytest.mark.django_db
def test_attribute_slug_check_constraint():
    with pytest.raises(IntegrityError), transaction.atomic():
        ContentFinding.objects.create(product_ref=1, target_kind="attribute",
            attribute_slug="", value={}, normalized_hash="h2",
            source_name="web", confidence=0.1, status="pending")


@pytest.mark.django_db
def test_one_active_claim_per_finding():
    f = ContentFinding.objects.create(product_ref=1, target_kind="description",
        attribute_slug="", value={"type": "text", "value": "x"}, normalized_hash="h3",
        source_name="web", confidence=0.9, status="pending")
    run = SourcingRun.objects.create(idempotency_key="k2", product_ref=1, status="ok")
    call = ExternalCall.objects.create(run=run, adapter="web", status="ok")
    ev = FindingEvidence.objects.create(finding=f, external_call=call, source_name="web",
        confidence=0.9, observed_value_hash="b", observed_source="", canonical_url="https://x/y")
    FindingApplicationAttempt.objects.create(finding=f, evidence=ev, status="claimed")
    with pytest.raises(IntegrityError), transaction.atomic():
        FindingApplicationAttempt.objects.create(finding=f, evidence=ev, status="claimed")


@pytest.mark.django_db
def test_budget_unique_day():
    SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=10)
    with pytest.raises(IntegrityError), transaction.atomic():
        SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=20)
```

- [ ] **Step 2: Прогнать — упадёт**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_models.py -v`
Expected: FAIL (нет моделей).

- [ ] **Step 3: Реализация** — добавить в КОНЕЦ `apps/ai/models.py`

```python
class SourcingRun(models.Model):
    """Один логический запуск source_content() по товару (аудит)."""

    class Status(models.TextChoices):
        RUNNING = "running"
        OK = "ok"
        DEGRADED = "degraded"
        CONFIGURATION_ERROR = "configuration_error"
        ERROR = "error"

    idempotency_key = models.CharField(max_length=128, unique=True)
    product_ref = models.PositiveIntegerField(db_index=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.RUNNING)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)


class ExternalCall(models.Model):
    """Один вызов источника (web|marketplace). Телеметрия и аудит оплаты."""

    class Status(models.TextChoices):
        RUNNING = "running"
        OK = "ok"
        ERROR = "error"
        UNKNOWN = "unknown"

    run = models.ForeignKey(SourcingRun, on_delete=models.CASCADE, related_name="calls")
    adapter = models.CharField(max_length=16)
    provider = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RUNNING)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    provider_idempotency_key = models.CharField(max_length=128, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    reserved_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    raw_excerpt = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "adapter"],
                                    name="uniq_externalcall_run_adapter")
        ]


class ContentFinding(models.Model):
    """Дедуп-канон значения для (product, target). Агрегаты — для отображения."""

    class Status(models.TextChoices):
        PENDING = "pending"
        APPLIED = "applied"
        REJECTED = "rejected"
        SUPERSEDED = "superseded"

    product = models.ForeignKey("catalog.Product", on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="+")
    product_ref = models.PositiveIntegerField(db_index=True)
    target_kind = models.CharField(max_length=20)
    attribute_slug = models.CharField(max_length=120, blank=True, default="")
    value = models.JSONField()
    normalized_hash = models.CharField(max_length=64)
    source_name = models.CharField(max_length=16)
    confidence = models.FloatField(default=0.0)
    status = models.CharField(max_length=12, choices=Status.choices,
                              default=Status.PENDING, db_index=True)
    last_outcome = models.CharField(max_length=24, blank=True)
    selected_evidence = models.ForeignKey("FindingEvidence", on_delete=models.SET_NULL,
                                          null=True, blank=True, related_name="+")
    reviewed_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product_ref", "target_kind", "attribute_slug", "normalized_hash"],
                name="uniq_finding_dedup"),
            models.CheckConstraint(
                name="finding_attribute_slug_consistency",
                check=(models.Q(target_kind="attribute") & ~models.Q(attribute_slug=""))
                | (~models.Q(target_kind="attribute") & models.Q(attribute_slug="")),
            ),
        ]
        indexes = [models.Index(fields=["product_ref", "status"])]


class FindingEvidence(models.Model):
    """Подтверждение факта (вызов + url + baseline на момент наблюдения)."""

    finding = models.ForeignKey(ContentFinding, on_delete=models.CASCADE,
                                related_name="evidences")
    external_call = models.ForeignKey(ExternalCall, on_delete=models.PROTECT, related_name="+")
    source_name = models.CharField(max_length=16)
    confidence = models.FloatField(default=0.0)
    observed_value_hash = models.CharField(max_length=64)
    observed_source = models.CharField(max_length=16, blank=True)
    canonical_url = models.URLField(max_length=500, blank=True)
    observed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["finding", "external_call", "canonical_url"],
                                    name="uniq_evidence")
        ]


class FindingApplicationAttempt(models.Model):
    """Committed-claim попытки применения (создаётся ДО основной транзакции)."""

    class Status(models.TextChoices):
        CLAIMED = "claimed"
        DONE = "done"
        FAILED = "failed"

    finding = models.ForeignKey(ContentFinding, on_delete=models.CASCADE,
                                related_name="attempts")
    evidence = models.ForeignKey(FindingEvidence, on_delete=models.PROTECT, related_name="+")
    reviewer = models.ForeignKey("accounts.User", on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CLAIMED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["finding"], condition=models.Q(status="claimed"),
                                    name="uniq_active_claim_per_finding")
        ]


class SourcingBudget(models.Model):
    """Атомарная защита дневного бюджета от параллельных workers."""

    day = models.DateField(unique=True)
    daily_cap = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    reserved = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    spent = models.DecimalField(max_digits=10, decimal_places=4, default=0)
```

Проверить вверху файла наличие `from django.db import models` (есть для `AiCallLog`).

- [ ] **Step 4: Миграция**

Run: `docker compose exec -T web python manage.py makemigrations ai --name sourcing_models`

- [ ] **Step 5: Прогнать — зелёные**

Run: `docker compose exec -T web python manage.py migrate ai && docker compose exec -T web pytest apps/ai/tests/test_sourcing_models.py -v`
Expected: PASS (5 тестов).

- [ ] **Step 6: Lint + commit**

```bash
docker compose exec -T web ruff check apps/ai/models.py apps/ai/tests/test_sourcing_models.py
docker compose exec -T web black --check apps/ai/models.py apps/ai/tests/test_sourcing_models.py
git add apps/ai/models.py apps/ai/migrations/ apps/ai/tests/test_sourcing_models.py
git commit -m "feat(sourcing): модели SourcingRun/ExternalCall/ContentFinding/Evidence/Attempt/Budget"
```

---

## Task 3: Порт источника + guardrails + dummy

**Files:**
- Create: `apps/ai/sourcing/__init__.py` (пустой), `apps/ai/sourcing/ports.py`, `apps/ai/sourcing/guardrails.py`
- Create: `apps/ai/sourcing/sources/__init__.py`, `apps/ai/sourcing/sources/dummy.py`
- Test: `apps/ai/tests/test_sourcing_guardrails.py`

**Interfaces (Produces):**
- `ports.SourceQuery(article, name, brand, category, needed_targets)`
- `ports.Finding(target_kind, attribute_slug, value, canonical_url, confidence, source_name)`
- `ports.SourceReply(findings, provider, tokens_in=0, tokens_out=0, cost=Decimal("0"), http_status=None, raw_excerpt="")`
- `ports.ContentSourcePort` (Protocol): `find(self, query, *, idempotency_key) -> SourceReply`
- `guardrails.validate(finding) -> Finding | None`
- `sources.dummy.DummySource`, `sources.get_sources() -> list`

**Consumes:** `ports` (этой же задачи).

- [ ] **Step 1: Падающий тест** — `apps/ai/tests/test_sourcing_guardrails.py`

```python
from apps.ai.sourcing.guardrails import validate
from apps.ai.sourcing.ports import Finding, SourceQuery
from apps.ai.sourcing.sources.dummy import DummySource


def _f(**kw):
    base = dict(target_kind="description", attribute_slug="",
                value={"type": "text", "value": "Перфоратор для бетона"},
                canonical_url="https://makita.ru/x", confidence=0.8, source_name="web")
    base.update(kw)
    return Finding(**base)


def test_web_without_url_rejected():
    assert validate(_f(canonical_url="")) is None


def test_forbidden_target_rejected():
    assert validate(_f(target_kind="price")) is None
    assert validate(_f(target_kind="attribute", attribute_slug="stock_quantity")) is None


def test_confidence_clamped():
    assert validate(_f(confidence=5.0)).confidence == 1.0
    assert validate(_f(confidence=-1.0)).confidence == 0.0


def test_marketplace_without_url_allowed():
    assert validate(_f(source_name="marketplace", canonical_url="")) is not None


def test_dummy_source_returns_reply():
    reply = DummySource().find(
        SourceQuery(article="HR2470", name="Перфоратор Makita HR2470",
                    brand="Makita", category="perf", needed_targets=["description"]),
        idempotency_key="k")
    assert reply.provider == "dummy" and reply.findings
    assert all(f.canonical_url for f in reply.findings)
```

- [ ] **Step 2: Прогнать — упадёт**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_guardrails.py -v`
Expected: FAIL.

- [ ] **Step 3: `apps/ai/sourcing/ports.py`**

```python
# apps/ai/sourcing/ports.py
"""Порт внешнего источника контента. Сервисы знают только порт."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class SourceQuery:
    article: str
    name: str
    brand: str
    category: str
    needed_targets: list


@dataclass(frozen=True)
class Finding:
    target_kind: str
    attribute_slug: str
    value: dict
    canonical_url: str
    confidence: float
    source_name: str


@dataclass(frozen=True)
class SourceReply:
    findings: list                       # list[Finding]
    provider: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost: Decimal = field(default_factory=lambda: Decimal("0"))
    http_status: int | None = None
    raw_excerpt: str = ""


class ContentSourcePort(Protocol):
    def find(self, query: SourceQuery, *, idempotency_key: str) -> SourceReply: ...
```

- [ ] **Step 4: `apps/ai/sourcing/guardrails.py`**

```python
# apps/ai/sourcing/guardrails.py
"""Валидация находок: выход источника — недоверенный ввод."""
from __future__ import annotations

from dataclasses import replace

from .ports import Finding

ALLOWED_TARGETS = {"name", "short_description", "description", "attribute"}
# Поля, которые источник НИКОГДА не может тронуть (цена/остаток/статус).
FORBIDDEN_ATTR_SLUGS = {"price", "stock_quantity", "available_quantity", "sync_1c_status"}
MAX_TEXT = 8000


def validate(finding: Finding) -> Finding | None:
    if finding.target_kind not in ALLOWED_TARGETS:
        return None
    if finding.target_kind == "attribute" and finding.attribute_slug in FORBIDDEN_ATTR_SLUGS:
        return None
    if finding.source_name == "web" and not finding.canonical_url:
        return None
    val = finding.value or {}
    if not isinstance(val, dict) or "type" not in val:
        return None
    if val.get("type") == "text" and len(str(val.get("value", ""))) > MAX_TEXT:
        return None
    conf = max(0.0, min(1.0, float(finding.confidence)))
    return replace(finding, confidence=conf)
```

- [ ] **Step 5: `sources/__init__.py` + `dummy.py`**

`apps/ai/sourcing/sources/__init__.py`:
```python
# apps/ai/sourcing/sources/__init__.py
"""Реестр источников. Включённые — по наличию ключей (Task 8)."""
from __future__ import annotations

from .dummy import DummySource


def get_sources() -> list:
    """Сейчас только dummy (тест). Реальные адаптеры подключаются в Task 8 по ключам.
    Включённый sourcing без реальных источников → вызывающий ставит configuration_error."""
    return [DummySource()]
```
`apps/ai/sourcing/sources/dummy.py`:
```python
# apps/ai/sourcing/sources/dummy.py
"""Детерминированный источник для тестов. Без сети."""
from __future__ import annotations

from decimal import Decimal

from ..ports import Finding, SourceQuery, SourceReply


class DummySource:
    name = "dummy"

    def find(self, query: SourceQuery, *, idempotency_key: str) -> SourceReply:
        url = f"https://example.test/{query.article or 'item'}"
        findings = [
            Finding(target_kind="description", attribute_slug="",
                    value={"type": "text", "value": f"{query.name} — описание из источника."},
                    canonical_url=url, confidence=0.8, source_name="web")
        ]
        return SourceReply(findings=findings, provider=self.name, tokens_in=5,
                           tokens_out=20, cost=Decimal("0"), http_status=200,
                           raw_excerpt="dummy")
```

- [ ] **Step 6: Прогнать — зелёные**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_guardrails.py -v`
Expected: PASS (5 тестов).

- [ ] **Step 7: Lint + commit**

```bash
docker compose exec -T web ruff check apps/ai/sourcing apps/ai/tests/test_sourcing_guardrails.py
docker compose exec -T web black --check apps/ai/sourcing apps/ai/tests/test_sourcing_guardrails.py
git add apps/ai/sourcing apps/ai/tests/test_sourcing_guardrails.py
git commit -m "feat(sourcing): порт ContentSourcePort + guardrails + dummy-источник"
```

---

## Task 4: `services.source_content` + `approve_and_apply_finding`

**Files:**
- Modify: `apps/ai/services.py` (две функции + хелперы)
- Test: `apps/ai/tests/test_sourcing_service.py`

**Interfaces:**
- Consumes: `catalog.provenance.{apply_sourced_value, value_hash, SourcedValueCommand, ApplyResult}`, `catalog.enrichment.get_enrichable_product`, `sourcing.ports.SourceQuery`, `sourcing.guardrails.validate`, `sourcing.sources.get_sources`, модели Task 2.
- Produces: `services.source_content(*, product_id, sources=None, idempotency_key) -> SourcingRun`; `services.approve_and_apply_finding(finding_id, evidence_id, reviewer_id) -> ApplyResult`; `services._today() -> date` (хук для тестов); `services.MAX_CALL_COST`.

**Границы:** `source_content` читает товар через `catalog.enrichment.get_enrichable_product` (НЕ `Product.objects`). Применение — только через `provenance.apply_sourced_value`.

- [ ] **Step 1: Падающий тест** — `apps/ai/tests/test_sourcing_service.py`

```python
import datetime as dt

import pytest

from apps.ai import services
from apps.ai.models import (ContentFinding, ExternalCall, FindingEvidence,
                            SourcingBudget, SourcingRun)
from apps.catalog.models import Category, Product, ProductStatus


def _product(**kw):
    cat = Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(category=cat, name="", slug="x", description="",
        short_description="", original_name="Перфоратор Makita HR2470",
        status=ProductStatus.IMPORTED, is_active=False, price="1000", **kw)


@pytest.fixture
def budget(db):
    return SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=100)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(services, "_today", lambda: dt.date(2026, 6, 29))


@pytest.mark.django_db
def test_source_content_collects_findings_without_touching_product(budget):
    p = _product()
    run = services.source_content(product_id=p.pk, idempotency_key="run-1")
    p.refresh_from_db()
    assert run.status in (SourcingRun.Status.OK, SourcingRun.Status.DEGRADED)
    assert ContentFinding.objects.filter(product_ref=p.pk).exists()
    assert FindingEvidence.objects.exists()
    assert p.description == "" and p.enrich_status == "pending"   # товар не изменён


@pytest.mark.django_db
def test_source_content_idempotent_no_double_call(budget):
    p = _product()
    services.source_content(product_id=p.pk, idempotency_key="run-2")
    services.source_content(product_id=p.pk, idempotency_key="run-2")     # повтор
    run = SourcingRun.objects.get(idempotency_key="run-2")
    assert ExternalCall.objects.filter(run=run, adapter="dummy", status="ok").count() == 1


@pytest.mark.django_db
def test_content_locked_blocks_sourcing(budget):
    p = _product(content_locked=True)
    run = services.source_content(product_id=p.pk, idempotency_key="run-3")
    assert run.status == SourcingRun.Status.DEGRADED
    assert not ContentFinding.objects.filter(product_ref=p.pk).exists()


@pytest.mark.django_db
def test_approve_applies_selected_evidence(budget):
    p = _product()
    services.source_content(product_id=p.pk, idempotency_key="run-4")
    f = ContentFinding.objects.get(product_ref=p.pk, target_kind="description")
    ev = f.evidences.first()
    result = services.approve_and_apply_finding(f.pk, ev.pk, reviewer_id=None)
    p.refresh_from_db(); f.refresh_from_db()
    assert result.status == "applied"
    assert p.description.startswith("Перфоратор") and f.status == "applied"


@pytest.mark.django_db
def test_reapprove_is_noop(budget):
    p = _product()
    services.source_content(product_id=p.pk, idempotency_key="run-5")
    f = ContentFinding.objects.get(product_ref=p.pk, target_kind="description")
    ev = f.evidences.first()
    services.approve_and_apply_finding(f.pk, ev.pk, reviewer_id=None)
    again = services.approve_and_apply_finding(f.pk, ev.pk, reviewer_id=None)
    assert again.status == "skipped"
```

- [ ] **Step 2: Прогнать — упадёт**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_service.py -v`
Expected: FAIL.

- [ ] **Step 3: Реализация** — добавить в `apps/ai/services.py`

```python
# --- sourcing (добавить к существующим импортам файла) ---
import datetime as _dt
import hashlib
import json as _json
from decimal import Decimal

from django.db import transaction

from apps.catalog import provenance
from apps.catalog.enrichment import get_enrichable_product

from .models import (ContentFinding, ExternalCall, FindingApplicationAttempt,
                     FindingEvidence, SourcingBudget, SourcingRun)
from .sourcing.guardrails import validate
from .sourcing.ports import SourceQuery
from .sourcing.sources import get_sources

MAX_CALL_COST = Decimal("1.0")   # верхняя граница одного вызова (резерв бюджета)


class BudgetExceeded(Exception):
    pass


def _today() -> _dt.date:
    return _dt.date.today()


def _norm_hash(value: dict) -> str:
    return hashlib.sha256(
        _json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _baseline_for(product, target_kind, attribute_slug):
    """Снимок (hash, source) целевого поля сейчас — для evidence."""
    if target_kind in provenance._TEXT_TARGETS:
        cur = getattr(product, target_kind) or ""
        src = (product.content_field_sources or {}).get(target_kind, "")
        return provenance.value_hash(cur), src
    return provenance.value_hash(None), ""   # атрибуты упрощённо «пусто» (детально — Task 8)


def source_content(*, product_id, sources=None, idempotency_key) -> SourcingRun:
    run, _ = SourcingRun.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={"product_ref": product_id, "status": SourcingRun.Status.RUNNING})
    product = get_enrichable_product(product_id)
    if product is None:
        run.status = SourcingRun.Status.ERROR
        run.save()
        return run
    if product.content_locked:
        run.status = SourcingRun.Status.DEGRADED
        run.save()
        return run

    adapters = sources if sources is not None else get_sources()
    if not adapters:
        run.status = SourcingRun.Status.CONFIGURATION_ERROR
        run.save()
        return run

    query = SourceQuery(article=getattr(product, "article", "") or "",
                        name=product.original_name or product.name or "",
                        brand=getattr(product, "brand", "") or "",
                        category=product.category.slug if product.category_id else "",
                        needed_targets=["description"])
    any_ok = False
    for adapter in adapters:
        name = getattr(adapter, "name", "src")
        if ExternalCall.objects.filter(run=run, adapter=name,
                                       status=ExternalCall.Status.OK).exists():
            any_ok = True
            continue
        try:
            call, owns = _reserve_and_open_call(run, name)
        except BudgetExceeded:
            run.status = SourcingRun.Status.DEGRADED
            break
        if not owns:                      # вызовом владеет другой worker / уже сделано
            any_ok = True
            continue
        try:
            reply = adapter.find(query, idempotency_key=f"{idempotency_key}:{name}")
        except Exception:  # noqa: BLE001 — изоляция источника
            _close_call(call, ExternalCall.Status.ERROR)
            continue
        _close_call(call, ExternalCall.Status.OK, reply=reply)
        any_ok = True
        _persist_findings(call, product, reply)

    if run.status == SourcingRun.Status.RUNNING:
        run.status = SourcingRun.Status.OK if any_ok else SourcingRun.Status.ERROR
    run.finished_at = _dt.datetime.now()
    run.save()
    return run


def _reserve_and_open_call(run, adapter):
    """Атомарно: владение попыткой + резерв бюджета + ExternalCall(running).
    Возврат (call, owns_attempt): сеть вызывает только владелец попытки."""
    with transaction.atomic():
        b, _ = SourcingBudget.objects.select_for_update().get_or_create(
            day=_today(), defaults={"daily_cap": Decimal("0")})
        call = ExternalCall.objects.select_for_update().filter(run=run, adapter=adapter).first()
        if call and call.status in (ExternalCall.Status.RUNNING, ExternalCall.Status.OK,
                                    ExternalCall.Status.UNKNOWN):
            return call, False
        if b.spent + b.reserved + MAX_CALL_COST > b.daily_cap:
            raise BudgetExceeded
        b.reserved += MAX_CALL_COST
        b.save()
        if call is None:
            call = ExternalCall.objects.create(run=run, adapter=adapter,
                status=ExternalCall.Status.RUNNING, reserved_cost=MAX_CALL_COST, attempt_count=1)
        else:  # error → running (захват retry)
            call.status = ExternalCall.Status.RUNNING
            call.attempt_count += 1
            call.reserved_cost = MAX_CALL_COST
            call.save()
        return call, True


def _close_call(call, status, *, reply=None):
    with transaction.atomic():
        b = SourcingBudget.objects.select_for_update().get(day=_today())
        call.status = status
        call.finished_at = _dt.datetime.now()
        if reply is not None:
            call.provider = reply.provider
            call.tokens_in = reply.tokens_in
            call.tokens_out = reply.tokens_out
            call.cost = reply.cost
            call.http_status = reply.http_status
            call.raw_excerpt = reply.raw_excerpt[:4000]
        if status == ExternalCall.Status.OK:
            b.spent += (reply.cost if reply else Decimal("0"))
            b.reserved -= call.reserved_cost
        elif status == ExternalCall.Status.ERROR:
            b.reserved -= call.reserved_cost          # definite-failed: резерв снимаем
        # unknown: резерв НЕ снимаем (§6.5 спеки)
        b.save()
        call.save()


def _persist_findings(call, product, reply):
    for raw in reply.findings:
        f = validate(raw)
        if f is None:
            continue
        nh = _norm_hash(f.value)
        finding, _ = ContentFinding.objects.get_or_create(
            product_ref=product.pk, target_kind=f.target_kind,
            attribute_slug=f.attribute_slug, normalized_hash=nh,
            defaults={"product_id": product.pk, "value": f.value,
                      "source_name": f.source_name, "confidence": f.confidence,
                      "status": ContentFinding.Status.PENDING})
        bh, bsrc = _baseline_for(product, f.target_kind, f.attribute_slug)
        FindingEvidence.objects.get_or_create(
            finding=finding, external_call=call, canonical_url=f.canonical_url,
            defaults={"source_name": f.source_name, "confidence": f.confidence,
                      "observed_value_hash": bh, "observed_source": bsrc})


def approve_and_apply_finding(finding_id, evidence_id, reviewer_id):
    pre = ContentFinding.objects.filter(pk=finding_id).values(
        "product_ref", "target_kind", "attribute_slug").first()
    if pre is None:
        return provenance.ApplyResult("missing_product")
    ev_obj = FindingEvidence.objects.filter(pk=evidence_id, finding_id=finding_id).first()
    if ev_obj is None:
        return provenance.ApplyResult("invalid", "evidence_not_found")
    attempt = FindingApplicationAttempt.objects.create(
        finding_id=finding_id, evidence_id=evidence_id, reviewer_id=reviewer_id,
        status=FindingApplicationAttempt.Status.CLAIMED)
    try:
        with transaction.atomic():
            siblings = list(ContentFinding.objects.filter(
                product_ref=pre["product_ref"], target_kind=pre["target_kind"],
                attribute_slug=pre["attribute_slug"]).select_for_update().order_by("pk"))
            by_id = {f.pk: f for f in siblings}
            f = by_id[finding_id]
            if f.status != ContentFinding.Status.PENDING:
                attempt.status = FindingApplicationAttempt.Status.DONE
                attempt.save()
                return provenance.ApplyResult("skipped", "already_processed")
            cmd = provenance.SourcedValueCommand(
                product_id=pre["product_ref"], target_kind=f.target_kind,
                attribute_slug=f.attribute_slug, value=f.value, source=ev_obj.source_name,
                confidence=ev_obj.confidence, observed_value_hash=ev_obj.observed_value_hash,
                observed_source=ev_obj.observed_source, allow_equal_override=True)
            result = provenance.apply_sourced_value(cmd)
            if result.status == "applied":
                f.status = ContentFinding.Status.APPLIED
                f.applied_at = _dt.datetime.now()
                f.reviewed_by_id = reviewer_id
                f.reviewed_at = _dt.datetime.now()
                f.save()
                for other in siblings:
                    if other.pk != f.pk and other.status == ContentFinding.Status.APPLIED:
                        other.status = ContentFinding.Status.SUPERSEDED
                        other.save()
            else:
                f.last_outcome = result.status
                f.reviewed_by_id = reviewer_id
                f.reviewed_at = _dt.datetime.now()
                f.save()
            attempt.status = FindingApplicationAttempt.Status.DONE
            attempt.save()
            return result
    except Exception as exc:  # noqa: BLE001 — техническая ошибка → rollback всей txn
        with transaction.atomic():
            FindingApplicationAttempt.objects.filter(pk=attempt.pk).update(
                status=FindingApplicationAttempt.Status.FAILED)
            ContentFinding.objects.filter(
                pk=finding_id, status=ContentFinding.Status.PENDING).update(
                last_outcome="apply_failed", rejection_reason=str(exc)[:255])
        raise
```

- [ ] **Step 4: Прогнать — зелёные**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_service.py -v`
Expected: PASS (5 тестов).

- [ ] **Step 5: Lint + commit**

```bash
docker compose exec -T web ruff check apps/ai/services.py apps/ai/tests/test_sourcing_service.py
docker compose exec -T web black --check apps/ai/services.py apps/ai/tests/test_sourcing_service.py
git add apps/ai/services.py apps/ai/tests/test_sourcing_service.py
git commit -m "feat(sourcing): source_content + approve_and_apply_finding (транзакция/идемпотентность/бюджет)"
```

---

## Task 5: Celery-задачи, janitor, retention, флаг `ai_sourcing`

**Files:**
- Modify: `apps/ai/tasks.py` (4 задачи)
- Modify: `config/settings/base.py` (флаг `ai_sourcing` в `FEATURES`)
- Test: `apps/ai/tests/test_sourcing_tasks.py`

**Interfaces (Produces):** `tasks.source_product_task`, `tasks.batch_source_task`, `tasks.mark_stale_sourcing_runs`, `tasks.purge_sourcing_excerpts`.

**Consumes:** `services.source_content`, `catalog.enrichment.pending_for_enrichment`, `features.is_enabled`.

- [ ] **Step 1: Падающий тест** — `apps/ai/tests/test_sourcing_tasks.py`

```python
import datetime as dt

import pytest

from apps.ai import services, tasks
from apps.ai.models import ContentFinding, ExternalCall, SourcingBudget, SourcingRun
from apps.catalog.models import Category, Product, ProductStatus


def _product(**kw):
    cat = Category.objects.first() or Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(category=cat, name="", slug=kw.pop("slug", "x"),
        description="", original_name="Перфоратор Makita", status=ProductStatus.IMPORTED,
        is_active=False, price="1000", available_quantity=kw.pop("q", 5), **kw)


@pytest.fixture
def budget(db):
    return SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=100)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(services, "_today", lambda: dt.date(2026, 6, 29))


@pytest.mark.django_db
def test_source_product_task_runs(budget, settings):
    settings.FEATURES = {**getattr(settings, "FEATURES", {}),
                         "ai": True, "ai_sourcing": True, "external_integrations": True}
    p = _product()
    tasks.source_product_task(p.pk, "task-run-1")
    assert ContentFinding.objects.filter(product_ref=p.pk).exists()


@pytest.mark.django_db
def test_task_skipped_when_flag_off(budget, settings):
    settings.FEATURES = {**getattr(settings, "FEATURES", {}), "ai_sourcing": False}
    p = _product()
    tasks.source_product_task(p.pk, "task-run-2")
    assert not SourcingRun.objects.filter(idempotency_key="task-run-2").exists()


@pytest.mark.django_db
def test_mark_stale_sourcing_runs(budget):
    run = SourcingRun.objects.create(idempotency_key="stale", product_ref=1,
                                     status=SourcingRun.Status.RUNNING)
    call = ExternalCall.objects.create(run=run, adapter="web",
                                       status=ExternalCall.Status.RUNNING)
    SourcingRun.objects.filter(pk=run.pk).update(
        created_at=dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc))
    tasks.mark_stale_sourcing_runs(older_than_minutes=60)
    call.refresh_from_db()
    assert call.status == ExternalCall.Status.UNKNOWN
```

- [ ] **Step 2: Прогнать — упадёт**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_tasks.py -v`
Expected: FAIL.

- [ ] **Step 3: Флаг в `config/settings/base.py`**

Найти словарь `FEATURES = {...}` и добавить ключ рядом с `"ai"`:
```python
    "ai_sourcing": env.bool("FEATURE_AI_SOURCING", default=False),
```

- [ ] **Step 4: Реализация** — добавить в `apps/ai/tasks.py`

```python
# --- sourcing tasks (добавить к существующим импортам) ---
import datetime as _dt

from celery import shared_task
from django.utils import timezone

from apps.core.features import is_enabled

from . import services
from .models import ExternalCall, SourcingRun


def _sourcing_enabled() -> bool:
    return (is_enabled("ai") and is_enabled("ai_sourcing")
            and is_enabled("external_integrations"))


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def source_product_task(self, product_id, idempotency_key):
    if not _sourcing_enabled():
        return "disabled"
    services.source_content(product_id=product_id, idempotency_key=idempotency_key)
    return idempotency_key


@shared_task
def batch_source_task(category_slug=None, limit=100):
    if not _sourcing_enabled():
        return 0
    from apps.catalog.enrichment import pending_for_enrichment
    ids = pending_for_enrichment(category_slug=category_slug, limit=limit)
    for pid in ids:
        source_product_task.delay(pid, f"batch:{category_slug or 'all'}:{pid}")
    return len(ids)


@shared_task
def mark_stale_sourcing_runs(older_than_minutes=60):
    cutoff = timezone.now() - _dt.timedelta(minutes=older_than_minutes)
    stale = SourcingRun.objects.filter(status=SourcingRun.Status.RUNNING, created_at__lt=cutoff)
    n = 0
    for run in stale:
        ExternalCall.objects.filter(run=run, status=ExternalCall.Status.RUNNING).update(
            status=ExternalCall.Status.UNKNOWN)   # резерв НЕ снимаем — нужна сверка
        run.status = SourcingRun.Status.ERROR
        run.save()
        n += 1
    return n


@shared_task
def purge_sourcing_excerpts(older_than_days=30):
    cutoff = timezone.now() - _dt.timedelta(days=older_than_days)
    return (ExternalCall.objects.filter(created_at__lt=cutoff).exclude(raw_excerpt="")
            .update(raw_excerpt=""))
```

- [ ] **Step 5: Прогнать — зелёные**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_tasks.py -v`
Expected: PASS (3 теста). Затем `docker compose exec -T web pytest apps/ai -q` — пакет зелёный.

- [ ] **Step 6: Lint + commit**

```bash
docker compose exec -T web ruff check apps/ai/tasks.py apps/ai/tests/test_sourcing_tasks.py config/settings/base.py
docker compose exec -T web black --check apps/ai/tasks.py apps/ai/tests/test_sourcing_tasks.py
git add apps/ai/tasks.py apps/ai/tests/test_sourcing_tasks.py config/settings/base.py
git commit -m "feat(sourcing): Celery source/batch + janitor + retention + флаг ai_sourcing"
```

---

## Task 6: Admin — очередь находок, review/evidence, bulk

**Files:**
- Modify: `apps/ai/admin.py` (`ContentFindingAdmin` + inline)
- Test: `apps/ai/tests/test_sourcing_admin.py`

**Interfaces (Produces):** `ContentFindingAdmin` (очередь по `status=pending`); bulk-`approve_selected` (по `selected_evidence`), bulk-`reject_selected`.

**Consumes:** `services.approve_and_apply_finding`, модели Task 2.

- [ ] **Step 1: Падающий тест** — `apps/ai/tests/test_sourcing_admin.py`

```python
import datetime as dt

import pytest

from apps.ai import services
from apps.ai.admin import ContentFindingAdmin
from apps.ai.models import ContentFinding, SourcingBudget
from apps.catalog.models import Category, Product, ProductStatus


@pytest.fixture
def budget(db):
    return SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=100)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(services, "_today", lambda: dt.date(2026, 6, 29))


def _seed():
    cat = Category.add_root(name="Перф", slug="perf")
    p = Product.objects.create(category=cat, name="", slug="x", description="",
        original_name="Перфоратор Makita", status=ProductStatus.IMPORTED,
        is_active=False, price="1000")
    services.source_content(product_id=p.pk, idempotency_key="admin-run")
    return p


@pytest.mark.django_db
def test_queue_shows_only_pending(budget):
    _seed()
    admin = ContentFindingAdmin(ContentFinding, None)
    qs = admin.get_queryset(type("R", (), {"GET": {}})())
    assert qs.count() >= 1 and all(f.status == "pending" for f in qs)


@pytest.mark.django_db
def test_bulk_approve_applies_selected_evidence(budget):
    p = _seed()
    f = ContentFinding.objects.get(product_ref=p.pk, target_kind="description")
    f.selected_evidence = f.evidences.first()
    f.save()
    admin = ContentFindingAdmin(ContentFinding, None)
    admin.approve_selected(None, ContentFinding.objects.filter(pk=f.pk))
    p.refresh_from_db(); f.refresh_from_db()
    assert f.status == "applied" and p.description.startswith("Перфоратор")
```

- [ ] **Step 2: Прогнать — упадёт**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_admin.py -v`
Expected: FAIL.

- [ ] **Step 3: Реализация** — добавить в `apps/ai/admin.py`

```python
# --- sourcing admin (добавить к существующим импортам admin/messages) ---
from . import services
from .models import ContentFinding, FindingEvidence


class FindingEvidenceInline(admin.TabularInline):
    model = FindingEvidence
    extra = 0
    readonly_fields = ("external_call", "source_name", "confidence", "observed_value_hash",
                       "observed_source", "canonical_url", "observed_at")
    can_delete = False


@admin.register(ContentFinding)
class ContentFindingAdmin(admin.ModelAdmin):
    list_display = ("product_ref", "target_kind", "attribute_slug", "source_name",
                    "confidence", "status", "last_outcome")
    list_filter = ("status", "source_name", "target_kind")
    search_fields = ("product_ref", "attribute_slug")
    inlines = [FindingEvidenceInline]
    actions = ["reject_selected", "approve_selected"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(status=ContentFinding.Status.PENDING)

    @admin.action(description="Отклонить выбранные")
    def reject_selected(self, request, queryset):
        n = queryset.update(status=ContentFinding.Status.REJECTED,
                            rejection_reason="отклонено модератором")
        if request is not None:
            self.message_user(request, f"Отклонено: {n}", messages.SUCCESS)

    @admin.action(description="Одобрить (по выбранному evidence)")
    def approve_selected(self, request, queryset):
        rid = getattr(getattr(request, "user", None), "pk", None)
        applied = skipped = 0
        for f in queryset:
            if f.selected_evidence_id is None:
                skipped += 1
                continue
            res = services.approve_and_apply_finding(f.pk, f.selected_evidence_id, rid)
            applied += 1 if res.status == "applied" else 0
        if request is not None:
            self.message_user(request,
                f"Применено: {applied}; без evidence: {skipped}", messages.INFO)
```

(Конкретный evidence модератор выбирает в change-форме находки, проставляя `selected_evidence`
среди inline; стандартный bulk-action не умеет выбирать inline, поэтому bulk-approve применяет
только находки с уже выбранным evidence. Каждая находка — отдельная транзакция внутри сервиса
→ частичный успех.)

- [ ] **Step 4: Прогнать — зелёные**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_admin.py -v`
Expected: PASS (2 теста).

- [ ] **Step 5: Lint + commit**

```bash
docker compose exec -T web ruff check apps/ai/admin.py apps/ai/tests/test_sourcing_admin.py
docker compose exec -T web black --check apps/ai/admin.py apps/ai/tests/test_sourcing_admin.py
git add apps/ai/admin.py apps/ai/tests/test_sourcing_admin.py
git commit -m "feat(sourcing): admin-очередь находок + review/evidence + bulk"
```

---

## Task 7: CLI — `source_product`, `source_catalog`, `source_report`

**Files:**
- Create: `apps/ai/management/commands/source_product.py`, `source_catalog.py`, `source_report.py`
- Test: `apps/ai/tests/test_sourcing_commands.py`

**Interfaces:** команды `source_product`/`source_catalog`/`source_report`.
**Consumes:** `services.source_content`, `catalog.enrichment.pending_for_enrichment`, модели Task 2. `management/` — допустимое место для `Product.objects` (исключение теста границ).

- [ ] **Step 1: Падающий тест** — `apps/ai/tests/test_sourcing_commands.py`

```python
import datetime as dt

import pytest
from django.core.management import call_command

from apps.ai import services
from apps.ai.models import ContentFinding, SourcingBudget
from apps.catalog.models import Category, Product, ProductStatus


@pytest.fixture
def budget(db):
    return SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=100)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(services, "_today", lambda: dt.date(2026, 6, 29))


def _p(slug, **kw):
    cat = Category.objects.first() or Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(category=cat, name="", slug=slug, description="",
        original_name="Перфоратор " + slug, status=ProductStatus.IMPORTED,
        is_active=False, price="1000", **kw)


@pytest.mark.django_db
def test_source_product_by_id(budget):
    p = _p("a")
    call_command("source_product", "--id", str(p.pk))
    assert ContentFinding.objects.filter(product_ref=p.pk).exists()


@pytest.mark.django_db
def test_source_product_dry_run_no_findings(budget):
    p = _p("b")
    call_command("source_product", "--id", str(p.pk), "--dry-run")
    assert not ContentFinding.objects.filter(product_ref=p.pk).exists()


@pytest.mark.django_db
def test_source_report_runs(budget, capsys):
    _p("c")
    call_command("source_report")
    assert "Находки" in capsys.readouterr().out
```

- [ ] **Step 2: Прогнать — упадёт**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_commands.py -v`
Expected: FAIL.

- [ ] **Step 3: `apps/ai/management/commands/source_product.py`**

```python
from django.core.management.base import BaseCommand, CommandError

from ...services import source_content


class Command(BaseCommand):
    help = "Поиск внешнего контента для одного товара"

    def add_arguments(self, parser):
        parser.add_argument("--id", type=int)
        parser.add_argument("--article", type=str)
        parser.add_argument("--dry-run", action="store_true",
                            help="без платных вызовов — только показать план")

    def handle(self, *args, **o):
        from apps.catalog.models import Product
        if o.get("id"):
            product = Product.objects.filter(pk=o["id"]).first()
        elif o.get("article"):
            product = Product.objects.filter(article=o["article"]).first()
        else:
            raise CommandError("укажите --id или --article")
        if product is None:
            raise CommandError("товар не найден")
        if o["dry_run"]:
            self.stdout.write(f"dry-run: искали бы контент для #{product.pk} "
                              f"'{product.original_name}'. Платных вызовов нет.")
            return
        run = source_content(product_id=product.pk, idempotency_key=f"cli:{product.pk}")
        self.stdout.write(f"run={run.idempotency_key} status={run.status}")
```

- [ ] **Step 4: `apps/ai/management/commands/source_catalog.py`**

```python
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.enrichment import pending_for_enrichment

from ...services import source_content


class Command(BaseCommand):
    help = "Батч-поиск внешнего контента (приоритет available_quantity > 0)"

    def add_arguments(self, parser):
        parser.add_argument("--category", type=str)
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--commit", action="store_true")

    def handle(self, *args, **o):
        if not o["category"] and not o["all"]:
            raise CommandError("укажите --category SLUG или --all")
        ids = pending_for_enrichment(category_slug=o["category"], limit=o["limit"])
        self.stdout.write(f"К обработке: {len(ids)}")
        if not o["commit"]:
            self.stdout.write("dry-run — добавьте --commit для реальных вызовов")
            return
        for pid in ids:
            source_content(product_id=pid, idempotency_key=f"cli-batch:{pid}")
        self.stdout.write(self.style.SUCCESS(f"Обработано: {len(ids)}"))
```

- [ ] **Step 5: `apps/ai/management/commands/source_report.py`**

```python
from django.core.management.base import BaseCommand
from django.db.models import Count, Sum

from ...models import ContentFinding, ExternalCall


class Command(BaseCommand):
    help = "Отчёт по находкам внешнего контента"

    def handle(self, *args, **o):
        self.stdout.write("Находки по статусам:")
        for row in (ContentFinding.objects.values("status")
                    .annotate(n=Count("id")).order_by("status")):
            self.stdout.write(f"  {row['status']}: {row['n']}")
        self.stdout.write("По источникам (pending):")
        for row in (ContentFinding.objects.filter(status="pending")
                    .values("source_name").annotate(n=Count("id"))):
            self.stdout.write(f"  {row['source_name']}: {row['n']}")
        cost = ExternalCall.objects.aggregate(s=Sum("cost"))["s"] or 0
        self.stdout.write(f"Суммарная стоимость вызовов: {cost}")
```

- [ ] **Step 6: Прогнать — зелёные**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_commands.py -v`
Expected: PASS (3 теста).

- [ ] **Step 7: Lint + commit**

```bash
docker compose exec -T web ruff check apps/ai/management/commands/source_product.py apps/ai/management/commands/source_catalog.py apps/ai/management/commands/source_report.py apps/ai/tests/test_sourcing_commands.py
docker compose exec -T web black --check apps/ai/management/commands/source_product.py apps/ai/management/commands/source_catalog.py apps/ai/management/commands/source_report.py
git add apps/ai/management/commands/source_product.py apps/ai/management/commands/source_catalog.py apps/ai/management/commands/source_report.py apps/ai/tests/test_sourcing_commands.py
git commit -m "feat(sourcing): CLI source_product/source_catalog/source_report"
```

---

## Task 8: Реальные адаптеры web_search + marketplace (за ключами)

**Files:**
- Create: `apps/ai/sourcing/safety.py` (allowlist по hostname)
- Create: `apps/ai/sourcing/sources/web_search.py`, `apps/ai/sourcing/sources/marketplace.py`
- Modify: `apps/ai/sourcing/sources/__init__.py` (`get_sources` по ключам), `config/settings/base.py` (ключи)
- Test: `apps/ai/tests/test_sourcing_adapters.py`

**Interfaces:** `safety.host_allowed(url, allowlist) -> bool`; `web_search.WebSearchSource`, `marketplace.MarketplaceSource` (реализуют `ContentSourcePort`); `get_sources(*, include_dummy=True)` — включает адаптер только при ключе; без ключей (и не DEBUG) → `[]` → `configuration_error`.

**Consumes:** `ports`, `safety`, настройки ключей.

- [ ] **Step 1: Падающий тест** — `apps/ai/tests/test_sourcing_adapters.py`

```python
from apps.ai.sourcing.safety import host_allowed
from apps.ai.sourcing.sources import get_sources

ALLOW = {"makita.ru", "market.yandex.ru"}


def test_allowlist_normalized_hostname():
    assert host_allowed("https://makita.ru/tool/x", ALLOW) is True
    assert host_allowed("https://www.makita.ru/x", ALLOW) is True        # субдомен www
    assert host_allowed("https://makita.ru.evil.com/x", ALLOW) is False  # не endswith-обман
    assert host_allowed("http://makita.ru/x", ALLOW) is False            # только https
    assert host_allowed("https://EVIL.com/makita.ru", ALLOW) is False


def test_get_sources_empty_without_keys(settings):
    settings.ANTHROPIC_API_KEY = ""
    settings.YANDEX_MARKET_API_KEY = ""
    assert get_sources(include_dummy=False) == []
```

- [ ] **Step 2: Прогнать — упадёт**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_adapters.py -v`
Expected: FAIL.

- [ ] **Step 3: `apps/ai/sourcing/safety.py`**

```python
# apps/ai/sourcing/safety.py
"""Безопасность web-источника: allowlist по нормализованному hostname (не endswith)."""
from __future__ import annotations

from urllib.parse import urlparse


def _host(url: str) -> str:
    p = urlparse(url)
    if p.scheme != "https":
        return ""
    return (p.hostname or "").lower().rstrip(".")


def host_allowed(url: str, allowlist) -> bool:
    host = _host(url)
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in allowlist)
```

- [ ] **Step 4: ключи в `config/settings/base.py`**

```python
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
YANDEX_MARKET_API_KEY = env("YANDEX_MARKET_API_KEY", default="")
SOURCING_ALLOWLIST = set(env.list("SOURCING_ALLOWLIST", default=[]))
```

- [ ] **Step 5: `web_search.py` и `marketplace.py` (каркас за ключом)**

`apps/ai/sourcing/sources/web_search.py`:
```python
# apps/ai/sourcing/sources/web_search.py
"""Web-поиск через Claude web_search / search API. Живые вызовы — за ключом.

Реализация сети — отдельный PR при наличии ANTHROPIC_API_KEY; здесь контракт и
безопасность (allowlist/https). Без сети метод явно не реализован (как claude.py в enrich)."""
from __future__ import annotations

from django.conf import settings

from ..ports import SourceQuery, SourceReply
from ..safety import host_allowed


class WebSearchSource:
    name = "web"

    def find(self, query: SourceQuery, *, idempotency_key: str) -> SourceReply:
        raise NotImplementedError(
            "WebSearchSource — каркас; живой вызов появится в отдельном PR при ANTHROPIC_API_KEY")

    @staticmethod
    def _accept(url: str) -> bool:
        return host_allowed(url, settings.SOURCING_ALLOWLIST)
```
`apps/ai/sourcing/sources/marketplace.py`:
```python
# apps/ai/sourcing/sources/marketplace.py
"""Источник по API маркетплейса (Яндекс.Маркет и пр.). Живые вызовы — за ключом."""
from __future__ import annotations

from ..ports import SourceQuery, SourceReply


class MarketplaceSource:
    name = "marketplace"

    def find(self, query: SourceQuery, *, idempotency_key: str) -> SourceReply:
        raise NotImplementedError(
            "MarketplaceSource — каркас; живой вызов появится в отдельном PR при YANDEX_MARKET_API_KEY")
```

- [ ] **Step 6: `get_sources` по ключам** — переписать `apps/ai/sourcing/sources/__init__.py`

```python
# apps/ai/sourcing/sources/__init__.py
"""Реестр источников. Включаются по наличию ключей; иначе список пуст → configuration_error."""
from __future__ import annotations

from django.conf import settings

from .dummy import DummySource
from .marketplace import MarketplaceSource
from .web_search import WebSearchSource


def get_sources(*, include_dummy: bool = True) -> list:
    out = []
    if getattr(settings, "ANTHROPIC_API_KEY", ""):
        out.append(WebSearchSource())
    if getattr(settings, "YANDEX_MARKET_API_KEY", ""):
        out.append(MarketplaceSource())
    if not out and include_dummy and settings.DEBUG:   # dummy — только dev/тест
        out.append(DummySource())
    return out
```

(`source_content` вызывает `get_sources()` с `include_dummy=True` по умолчанию; в проде без
ключей и без DEBUG → `[]` → `configuration_error`. Тесты Task 4 идут с `DEBUG=True`, поэтому
dummy доступен — сервисные тесты не регрессируют.)

- [ ] **Step 7: Прогнать — зелёные**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_adapters.py apps/ai/tests/test_sourcing_service.py -v`
Expected: PASS (адаптеры + сервис не регрессировали).

- [ ] **Step 8: Полный прогон + lint + commit**

```bash
docker compose exec -T web pytest apps/ai apps/catalog -q
docker compose exec -T web ruff check apps/ai/sourcing config/settings/base.py apps/ai/tests/test_sourcing_adapters.py
docker compose exec -T web black --check apps/ai/sourcing apps/ai/tests/test_sourcing_adapters.py
git add apps/ai/sourcing config/settings/base.py apps/ai/tests/test_sourcing_adapters.py
git commit -m "feat(sourcing): адаптеры web_search/marketplace за ключами + allowlist"
```

---

## Task 9: Ночной триггер sourcing для 1С-импорта (Celery-beat батч)

**Files:**
- Modify: `apps/ai/tasks.py` (стабильное `name` у `batch_source_task` для beat)
- Modify: `config/celery.py` (запись в `beat_schedule` + импорт `crontab`)
- Test: `apps/ai/tests/test_sourcing_schedule.py`

**Interfaces:**
- Consumes: `tasks.batch_source_task` (Task 5), `catalog.enrichment.pending_for_enrichment`, `services.source_content`.
- Produces: beat-запись `source-catalog-nightly` → `apps.ai.tasks.batch_source_task`.

**Почему батч, а не сигнал (грунт из кода):** импорт из 1С **намеренно не эмитит**
`product_created` — `apps/ai/receivers.py`: *«Импортёр 1С эмит не шлёт — 1С-товары идут батчем;
подписка обслуживает admin/API-создание товаров»*. Значит подписка на сигнал для 1С-товаров
не сработает. 1С-товары без описания/характеристик попадают в `catalog.pending_for_enrichment`
(уже используется в Task 5/7), и ночной `batch_source_task` их разгребает. Авто-публикации нет —
находки идут в очередь модерации (Task 6).

**Безопасность по умолчанию:** дневной `SourcingBudget` создаётся с `daily_cap=0` (Task 4,
`_reserve_and_open_call`), поэтому пока админ не задаст лимит — каждый резерв упирается в бюджет,
прогон `degraded`, трат нет. Sourcing «спит», пока бюджет не выставлен явно (это проверяет тест).

**Ветка:** `feature/sourcing-schedule` (от свежего dev). Только она — никаких git merge/pull/rebase/checkout.

- [ ] **Step 1: Падающий тест** — `apps/ai/tests/test_sourcing_schedule.py`

```python
import datetime as dt

import pytest

from apps.ai import services, tasks
from apps.ai.models import ContentFinding, SourcingBudget
from apps.catalog.models import Category, Product, ProductStatus


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(services, "_today", lambda: dt.date(2026, 6, 29))


def _flags(settings):
    settings.FEATURES = {**getattr(settings, "FEATURES", {}),
                         "ai": True, "ai_sourcing": True, "external_integrations": True}


def _imported_product(slug="hr2470"):
    cat = Category.objects.first() or Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(category=cat, name="", slug=slug, description="",
        original_name="Перфоратор Makita " + slug, status=ProductStatus.IMPORTED,
        is_active=False, price="1000", available_quantity=5)


def test_beat_schedule_has_nightly_sourcing():
    from config.celery import app
    entry = app.conf.beat_schedule.get("source-catalog-nightly")
    assert entry is not None
    assert entry["task"] == "apps.ai.tasks.batch_source_task"


@pytest.mark.django_db
def test_nightly_batch_sources_pending_1c_product(settings):
    _flags(settings)
    SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=100)
    _imported_product()
    n = tasks.batch_source_task()       # EAGER → source_product_task выполняется инлайн
    assert n >= 1
    assert ContentFinding.objects.exists()


@pytest.mark.django_db
def test_nightly_batch_safe_without_budget(settings):
    _flags(settings)                    # дневной лимит НЕ задан → daily_cap=0
    _imported_product(slug="x")
    tasks.batch_source_task()
    assert not ContentFinding.objects.exists()   # резерв > 0 при cap=0 → degraded, трат нет
```

> ⚠️ Грунт для имплементера: `pending_for_enrichment(category_slug=None, limit=...)` уже
> используется в Task 5/7 и возвращает товары, ждущие обогащения (`status=IMPORTED` /
> `enrich_status=pending`). Если на этом наборе товара тест `n >= 1` пуст — **STOP, NEEDS_CONTEXT**
> (уточнить фильтр `pending_for_enrichment`), не подменять реальный путь моками.

- [ ] **Step 2: Прогнать — упадёт**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_schedule.py -v`
Expected: FAIL (`source-catalog-nightly` ещё нет в `beat_schedule`).

- [ ] **Step 3: Стабильное имя задачи** — в `apps/ai/tasks.py` заменить декоратор `batch_source_task`:

```python
# было:
@shared_task
def batch_source_task(category_slug=None, limit=100):
# стало (тело без изменений — нужно стабильное имя, как у mark_stale_syncs):
@shared_task(name="apps.ai.tasks.batch_source_task")
def batch_source_task(category_slug=None, limit=100):
```

- [ ] **Step 4: Beat-запись** — в `config/celery.py`

Добавить импорт рядом с `from celery import Celery`:
```python
from celery.schedules import crontab
```
В `app.conf.beat_schedule` добавить запись после `"mark-stale-syncs"`:
```python
    "source-catalog-nightly": {
        "task": "apps.ai.tasks.batch_source_task",
        "schedule": crontab(hour=3, minute=30),  # ночью, после обмена с 1С
        "kwargs": {"limit": 200},
    },
```

- [ ] **Step 5: Прогнать — зелёные**

Run: `docker compose exec -T web pytest apps/ai/tests/test_sourcing_schedule.py -v`
Expected: PASS (3 теста). Затем `docker compose exec -T web pytest apps/ai -q` — пакет зелёный.

- [ ] **Step 6: Lint + commit**

```bash
docker compose exec -T web ruff check apps/ai/tasks.py config/celery.py apps/ai/tests/test_sourcing_schedule.py
docker compose exec -T web black --check apps/ai/tasks.py config/celery.py apps/ai/tests/test_sourcing_schedule.py
git add apps/ai/tasks.py config/celery.py apps/ai/tests/test_sourcing_schedule.py
git commit -m "feat(sourcing): ночной beat-триггер batch_source_task для 1С-импорта"
```

---

## Финальный DoD (после Task 9)
- [ ] `docker compose exec -T web pytest apps/ai apps/catalog -x` — зелёные.
- [ ] `ruff check` + `black --check` по `apps/ai apps/catalog` — чисто.
- [ ] Тест границ `apps/ai/tests/test_boundaries.py` (из EPIC-ENRICH) — зелёный: ядро `apps/ai` не лезет в `Product.objects`; каталог не импортирует `ai`.
- [ ] Полный цикл на dummy (dev): `source_product --id N` → находка+evidence → admin approve (по `selected_evidence`) → `apply_sourced_value` → `applied`; `content_field_sources` проставлен.
- [ ] Флаги `ai`/`ai_sourcing`/`external_integrations` гасят capability; без ключей и без DEBUG → `configuration_error`.
- [ ] Инварианты §7 спеки покрыты тестами (провенанс, baseline-конфликт, rollback+guarded apply_failed, идемпотентность, partial-claim, бюджет, allowlist).
- [ ] beat-запись `source-catalog-nightly` зарегистрирована; ночной `batch_source_task` запускает sourcing для 1С-товаров (которые `product_created` не шлют) по `pending_for_enrichment`; при `daily_cap=0` трат и находок нет.
