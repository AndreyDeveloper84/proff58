# PDP A — План 1: бэкенд заявок (`apps/leads`) + BFF

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Принимать заявки «Запросить цену» / «Уточнить поступление» с карточки товара: модель + DRF-эндпоинт (throttled, без auth) + модерация в админке + доменное событие + тонкий Next BFF-роут.

**Architecture:** Новое Django-приложение `apps/leads` (Слой 1, рядом с магазином). Создание заявки идёт через сервисный слой `services.create_inquiry`, который эмитит доменное событие `product_inquiry_created` через `transaction.on_commit`. Подписчик в `receivers.py` шлёт уведомление (под eventbus-флагом) и не влияет на успех создания. Фронт ходит через Next BFF `/api/inquiry` → Django `/api/leads/inquiries/`.

**Tech Stack:** Django 5.0, DRF 3.15, pytest-django, Next.js (BFF через `proxyToDjango`).

## Global Constraints

- **БД:** PostgreSQL 16 (SQLite не использовать даже в тестах).
- **Базовая модель:** наследовать `apps.core.models.TimeStampedModel` (поля `created_at`/`updated_at`).
- **События:** объявлять только в `apps/core/events.py`; эмит — из сервисного слоя через `transaction.on_commit(...)`, payload — идентификаторы/снапшоты, не ORM-инстансы.
- **Границы модулей:** не лезть в чужие таблицы; FK на `catalog.Product` допустим (это публичная модель каталога).
- **Качество перед коммитом:** `ruff check .`, `black .` (хук формата уже гоняет это на `.py`).
- **Общение/комментарии:** русский язык.

---

### Task 1: Каркас приложения + модель `ProductInquiry` + миграция

**Files:**
- Create: `apps/leads/__init__.py` (пустой)
- Create: `apps/leads/apps.py`
- Create: `apps/leads/models.py`
- Create: `apps/leads/tests/__init__.py` (пустой)
- Create: `apps/leads/tests/conftest.py`
- Create: `apps/leads/tests/test_models.py`
- Modify: `config/settings/base.py` (INSTALLED_APPS, блок «приложения проекта», после `"apps.orders",`)
- Create (генерируется): `apps/leads/migrations/__init__.py`, `apps/leads/migrations/0001_initial.py`

**Interfaces:**
- Produces: `apps.leads.models.ProductInquiry` с полями `kind` (`InquiryKind.PRICE_REQUEST`/`RESTOCK_NOTIFY`), `product` (FK→`catalog.Product`, `related_name="inquiries"`), `phone: str`, `name: str`, `message: str`, `status` (`InquiryStatus.NEW`/`PROCESSED`), `created_at`, `updated_at`. Менеджер по умолчанию.

- [ ] **Step 1: Зарегистрировать приложение в настройках**

В `config/settings/base.py`, в списке `INSTALLED_APPS`, в секции «# приложения проекта», добавить строку сразу после `"apps.orders",`:

```python
    "apps.orders",
    "apps.leads",
    "apps.ai",
```

- [ ] **Step 2: AppConfig**

Создать `apps/leads/apps.py`:

```python
from django.apps import AppConfig


class LeadsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.leads"
    verbose_name = "Заявки"
```

- [ ] **Step 3: Написать падающий тест модели**

Создать `apps/leads/tests/__init__.py` (пустой) и `apps/leads/tests/conftest.py`:

```python
"""Фикстуры тестов заявок."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductStatus


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def product(db):
    """Опубликованный товар в наличии с ценой."""
    return Product.objects.create(
        name="Дрель",
        code_1c="1c-lead-1",
        article="ART-LEAD-1",
        slug="drel-lead-1",
        unit="шт",
        price=Decimal("1000.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("10"),
    )
```

Создать `apps/leads/tests/test_models.py`:

```python
import pytest

from apps.leads.models import InquiryKind, InquiryStatus, ProductInquiry


@pytest.mark.django_db
def test_inquiry_defaults_to_new_status(product):
    inq = ProductInquiry.objects.create(
        kind=InquiryKind.PRICE_REQUEST, product=product, phone="+79990000001"
    )
    assert inq.status == InquiryStatus.NEW
    assert inq.created_at is not None
    assert inq.product.inquiries.count() == 1
```

- [ ] **Step 4: Запустить тест — убедиться, что падает**

Run: `docker exec proff58-web-1 pytest apps/leads/tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError`/`ImportError: cannot import name 'ProductInquiry'`.

- [ ] **Step 5: Реализовать модель**

Создать `apps/leads/models.py`:

```python
"""Заявки с карточки товара (лиды): запрос цены и уведомление о поступлении."""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class InquiryKind(models.TextChoices):
    PRICE_REQUEST = "price_request", _("Запрос цены")
    RESTOCK_NOTIFY = "restock_notify", _("Уведомить о поступлении")


class InquiryStatus(models.TextChoices):
    NEW = "new", _("Новая")
    PROCESSED = "processed", _("Обработана")


class ProductInquiry(TimeStampedModel):
    """Заявка покупателя по конкретному товару (lead capture с PDP)."""

    kind = models.CharField(_("Тип"), max_length=20, choices=InquiryKind.choices)
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="inquiries",
        verbose_name=_("Товар"),
    )
    phone = models.CharField(_("Телефон"), max_length=20)
    name = models.CharField(_("Имя"), max_length=120, blank=True)
    message = models.TextField(_("Сообщение"), blank=True)
    status = models.CharField(
        _("Статус"), max_length=12, choices=InquiryStatus.choices, default=InquiryStatus.NEW
    )

    class Meta:
        verbose_name = _("Заявка по товару")
        verbose_name_plural = _("Заявки по товарам")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["status", "kind"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.phone} ({self.product_id})"
```

- [ ] **Step 6: Создать миграцию**

Run: `docker exec proff58-web-1 python manage.py makemigrations leads`
Expected: создан `apps/leads/migrations/0001_initial.py` с моделью `ProductInquiry`.

- [ ] **Step 7: Применить миграцию и прогнать тест**

Run: `docker exec proff58-web-1 python manage.py migrate leads && docker exec proff58-web-1 pytest apps/leads/tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 8: Проверки и коммит**

```bash
docker exec proff58-web-1 python manage.py check
git add apps/leads/__init__.py apps/leads/apps.py apps/leads/models.py apps/leads/tests/ apps/leads/migrations/ config/settings/base.py
git commit -m "feat(leads): модель ProductInquiry + регистрация приложения"
```

---

### Task 2: Доменное событие + сервис `create_inquiry`

**Files:**
- Modify: `apps/core/events.py` (добавить сигнал в секцию, новый блок `# --- leads ---`)
- Create: `apps/leads/services.py`
- Create: `apps/leads/tests/test_services.py`

**Interfaces:**
- Consumes: `apps.leads.models.ProductInquiry`, `InquiryKind`.
- Produces:
  - `apps.core.events.product_inquiry_created` (`Signal`; payload: `inquiry_id: int`, `kind: str`, `product_id: int`).
  - `apps.leads.services.create_inquiry(*, kind: str, product, phone: str, name: str = "", message: str = "") -> ProductInquiry` — создаёт заявку и эмитит событие через `transaction.on_commit`.

- [ ] **Step 1: Объявить сигнал события**

В `apps/core/events.py` после блока `# --- orders ---` (перед `# --- payments ...`) добавить:

```python
# --- leads ---
# product_inquiry_created — издатель apps.leads.services.create_inquiry.
# payload: inquiry_id, kind, product_id
product_inquiry_created = Signal()
```

- [ ] **Step 2: Написать падающий тест сервиса**

Создать `apps/leads/tests/test_services.py`:

```python
import pytest

from apps.leads.models import InquiryKind, ProductInquiry
from apps.leads.services import create_inquiry


@pytest.mark.django_db(transaction=True)
def test_create_inquiry_persists_and_emits_event(product):
    received = {}

    from apps.core.events import product_inquiry_created

    def handler(sender, **kwargs):
        received.update(kwargs)

    product_inquiry_created.connect(handler, weak=False)
    try:
        inq = create_inquiry(
            kind=InquiryKind.PRICE_REQUEST,
            product=product,
            phone="+79990000002",
            name="Пётр",
        )
    finally:
        product_inquiry_created.disconnect(handler)

    assert ProductInquiry.objects.filter(pk=inq.pk).exists()
    assert received["inquiry_id"] == inq.pk
    assert received["product_id"] == product.pk
    assert received["kind"] == InquiryKind.PRICE_REQUEST
```

- [ ] **Step 3: Запустить тест — убедиться, что падает**

Run: `docker exec proff58-web-1 pytest apps/leads/tests/test_services.py -v`
Expected: FAIL — `ImportError: cannot import name 'create_inquiry'`.

- [ ] **Step 4: Реализовать сервис**

Создать `apps/leads/services.py`:

```python
"""Сервисный слой заявок: единая точка создания + эмит доменного события."""

from __future__ import annotations

from django.db import transaction

from apps.core.events import product_inquiry_created

from .models import ProductInquiry


def create_inquiry(*, kind, product, phone, name="", message=""):
    """Создать заявку по товару и опубликовать факт `product_inquiry_created`.

    Событие эмитится через on_commit — подписчик видит уже закоммиченную запись.
    """
    inquiry = ProductInquiry.objects.create(
        kind=kind, product=product, phone=phone, name=name, message=message
    )

    def _emit():
        product_inquiry_created.send(
            sender=ProductInquiry,
            inquiry_id=inquiry.pk,
            kind=inquiry.kind,
            product_id=inquiry.product_id,
        )

    transaction.on_commit(_emit)
    return inquiry
```

- [ ] **Step 5: Запустить тест — убедиться, что проходит**

Run: `docker exec proff58-web-1 pytest apps/leads/tests/test_services.py -v`
Expected: PASS (тест с `transaction=True`, поэтому `on_commit` срабатывает).

- [ ] **Step 6: Коммит**

```bash
git add apps/core/events.py apps/leads/services.py apps/leads/tests/test_services.py
git commit -m "feat(leads): событие product_inquiry_created + сервис create_inquiry"
```

---

### Task 3: Сериализатор с валидацией телефона

**Files:**
- Create: `apps/leads/api/__init__.py` (пустой)
- Create: `apps/leads/api/serializers.py`
- Create: `apps/leads/tests/test_serializers.py`

**Interfaces:**
- Consumes: `ProductInquiry`, `InquiryKind`, `apps.leads.services.create_inquiry`.
- Produces: `apps.leads.api.serializers.ProductInquirySerializer` — поля ввода `kind`, `product` (PK), `phone`, `name`, `message`; вывод `id`, `kind`, `status`. Метод `validate_phone` нормализует RU-номер к `+7XXXXXXXXXX`. `create()` делегирует в `services.create_inquiry`.

- [ ] **Step 1: Написать падающий тест сериализатора**

Создать `apps/leads/tests/test_serializers.py`:

```python
import pytest

from apps.leads.api.serializers import ProductInquirySerializer
from apps.leads.models import InquiryKind


@pytest.mark.django_db
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+7 (999) 000-00-03", "+79990000003"),
        ("8 999 000 00 03", "+79990000003"),
        ("79990000003", "+79990000003"),
    ],
)
def test_phone_is_normalized(product, raw, expected):
    s = ProductInquirySerializer(
        data={"kind": InquiryKind.PRICE_REQUEST, "product": product.pk, "phone": raw}
    )
    assert s.is_valid(), s.errors
    assert s.validated_data["phone"] == expected


@pytest.mark.django_db
def test_invalid_phone_rejected(product):
    s = ProductInquirySerializer(
        data={"kind": InquiryKind.PRICE_REQUEST, "product": product.pk, "phone": "123"}
    )
    assert not s.is_valid()
    assert "phone" in s.errors
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `docker exec proff58-web-1 pytest apps/leads/tests/test_serializers.py -v`
Expected: FAIL — `ModuleNotFoundError: apps.leads.api`.

- [ ] **Step 3: Реализовать сериализатор**

Создать `apps/leads/api/__init__.py` (пустой) и `apps/leads/api/serializers.py`:

```python
"""Сериализатор приёма заявок по товару."""

from __future__ import annotations

import re

from rest_framework import serializers

from apps.leads.models import ProductInquiry
from apps.leads.services import create_inquiry


class ProductInquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductInquiry
        fields = ["id", "kind", "product", "phone", "name", "message", "status"]
        read_only_fields = ["id", "status"]

    def validate_phone(self, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) == 11 and digits[0] in {"7", "8"}:
            return "+7" + digits[1:]
        if len(digits) == 10:
            return "+7" + digits
        raise serializers.ValidationError("Укажите корректный номер телефона.")

    def create(self, validated_data):
        return create_inquiry(**validated_data)
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `docker exec proff58-web-1 pytest apps/leads/tests/test_serializers.py -v`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add apps/leads/api/__init__.py apps/leads/api/serializers.py apps/leads/tests/test_serializers.py
git commit -m "feat(leads): сериализатор заявок с нормализацией телефона"
```

---

### Task 4: Эндпоинт (create-only, throttled) + URL-маршрутизация

**Files:**
- Create: `apps/leads/api/views.py`
- Create: `apps/leads/api/urls.py`
- Modify: `config/settings/base.py` (в `REST_FRAMEWORK` добавить `DEFAULT_THROTTLE_RATES`)
- Modify: `config/urls.py` (подключить `api/leads/`)
- Create: `apps/leads/tests/test_api.py`

**Interfaces:**
- Consumes: `ProductInquirySerializer`.
- Produces: `POST /api/leads/inquiries/` → `201` с `{id, kind, status}`; невалидные данные → `400`; превышение лимита → `429`. Throttle scope `"inquiry"`.

- [ ] **Step 1: Написать падающий тест API**

Создать `apps/leads/tests/test_api.py`:

```python
import pytest

from apps.leads.models import InquiryKind, ProductInquiry


@pytest.mark.django_db
def test_post_inquiry_creates_201(api, product):
    resp = api.post(
        "/api/leads/inquiries/",
        {"kind": InquiryKind.PRICE_REQUEST, "product": product.pk, "phone": "8 999 000 00 04"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.data["status"] == "new"
    inq = ProductInquiry.objects.get(pk=resp.data["id"])
    assert inq.phone == "+79990000004"


@pytest.mark.django_db
def test_post_inquiry_invalid_phone_400(api, product):
    resp = api.post(
        "/api/leads/inquiries/",
        {"kind": InquiryKind.PRICE_REQUEST, "product": product.pk, "phone": "x"},
        format="json",
    )
    assert resp.status_code == 400
    assert "phone" in resp.data
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `docker exec proff58-web-1 pytest apps/leads/tests/test_api.py -v`
Expected: FAIL — `404` (маршрут ещё не подключён).

- [ ] **Step 3: Реализовать view**

Создать `apps/leads/api/views.py`:

```python
"""Публичный эндпоинт приёма заявок по товару (create-only, без auth, throttled)."""

from __future__ import annotations

from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from .serializers import ProductInquirySerializer


class ProductInquiryCreateView(generics.CreateAPIView):
    serializer_class = ProductInquirySerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "inquiry"
```

- [ ] **Step 4: Подключить URL приложения**

Создать `apps/leads/api/urls.py`:

```python
from django.urls import path

from .views import ProductInquiryCreateView

app_name = "leads"

urlpatterns = [
    path("inquiries/", ProductInquiryCreateView.as_view(), name="inquiry-create"),
]
```

- [ ] **Step 5: Подключить в корневых URL**

В `config/urls.py` в списке `urlpatterns` добавить строку после `path("api/catalog/", ...)`:

```python
    path("api/catalog/", include("apps.catalog.api.urls")),
    path("api/leads/", include("apps.leads.api.urls")),
```

- [ ] **Step 6: Задать лимит throttle**

В `config/settings/base.py` в словаре `REST_FRAMEWORK` добавить ключ (рядом с существующими):

```python
    "DEFAULT_THROTTLE_RATES": {"inquiry": "20/hour"},
```

- [ ] **Step 7: Запустить тест — убедиться, что проходит**

Run: `docker exec proff58-web-1 pytest apps/leads/tests/test_api.py -v`
Expected: PASS (оба теста).

- [ ] **Step 8: Проверки и коммит**

```bash
docker exec proff58-web-1 python manage.py check
git add apps/leads/api/views.py apps/leads/api/urls.py config/settings/base.py config/urls.py apps/leads/tests/test_api.py
git commit -m "feat(leads): POST /api/leads/inquiries/ (create-only, throttled)"
```

---

### Task 5: Админка (модерация заявок)

**Files:**
- Create: `apps/leads/admin.py`
- Create: `apps/leads/tests/test_admin.py`

**Interfaces:**
- Consumes: `ProductInquiry`, `InquiryStatus`.
- Produces: регистрация `ProductInquiry` в админке с действием `mark_processed`.

- [ ] **Step 1: Написать падающий тест админ-действия**

Создать `apps/leads/tests/test_admin.py`:

```python
import pytest
from django.contrib.admin.sites import AdminSite

from apps.leads.admin import ProductInquiryAdmin
from apps.leads.models import InquiryKind, InquiryStatus, ProductInquiry


@pytest.mark.django_db
def test_mark_processed_action(product):
    inq = ProductInquiry.objects.create(
        kind=InquiryKind.PRICE_REQUEST, product=product, phone="+79990000005"
    )
    admin = ProductInquiryAdmin(ProductInquiry, AdminSite())
    admin.mark_processed(request=None, queryset=ProductInquiry.objects.all())
    inq.refresh_from_db()
    assert inq.status == InquiryStatus.PROCESSED
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `docker exec proff58-web-1 pytest apps/leads/tests/test_admin.py -v`
Expected: FAIL — `ImportError: cannot import name 'ProductInquiryAdmin'`.

- [ ] **Step 3: Реализовать админку**

Создать `apps/leads/admin.py`:

```python
"""Админка заявок по товарам — модерация."""

from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import InquiryStatus, ProductInquiry


@admin.register(ProductInquiry)
class ProductInquiryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "phone", "product", "status")
    list_filter = ("status", "kind")
    search_fields = ("phone", "name", "product__name")
    raw_id_fields = ("product",)
    readonly_fields = ("created_at", "updated_at")
    actions = ("mark_processed",)

    @admin.action(description=_("Отметить обработанными"))
    def mark_processed(self, request, queryset):
        queryset.update(status=InquiryStatus.PROCESSED)
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `docker exec proff58-web-1 pytest apps/leads/tests/test_admin.py -v`
Expected: PASS.

> Примечание: использован `raw_id_fields` (а не `autocomplete_fields`) — он не
> требует `search_fields` у `ProductAdmin` и потому не порождает ошибок
> `manage.py check` независимо от конфигурации админки каталога.

- [ ] **Step 5: Проверки и коммит**

```bash
docker exec proff58-web-1 python manage.py check
git add apps/leads/admin.py apps/leads/tests/test_admin.py
git commit -m "feat(leads): админка заявок + действие «обработана»"
```

---

### Task 6: Подписчик-уведомление под eventbus-флагом

**Files:**
- Create: `apps/leads/receivers.py`
- Modify: `apps/leads/apps.py` (метод `ready()`)
- Create: `apps/leads/tests/test_receivers.py`

**Interfaces:**
- Consumes: `apps.core.events.product_inquiry_created`, `apps.core.features.is_enabled`.
- Produces: подписчик `notify_new_inquiry(sender, inquiry_id, kind, product_id, **kwargs)`, подключаемый в `LeadsConfig.ready()`. Логирует факт; сбой канала не пробрасывается.

- [ ] **Step 1: Написать падающий тест подписчика**

Создать `apps/leads/tests/test_receivers.py`:

```python
import logging

import pytest

from apps.leads.receivers import notify_new_inquiry


@pytest.mark.django_db
def test_notify_logs_inquiry(product, caplog):
    with caplog.at_level(logging.INFO, logger="apps.leads"):
        notify_new_inquiry(
            sender=None, inquiry_id=1, kind="price_request", product_id=product.pk
        )
    assert any("price_request" in r.getMessage() for r in caplog.records)
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `docker exec proff58-web-1 pytest apps/leads/tests/test_receivers.py -v`
Expected: FAIL — `ModuleNotFoundError: apps.leads.receivers`.

- [ ] **Step 3: Реализовать подписчик**

Создать `apps/leads/receivers.py`:

```python
"""Подписчики событий заявок. Сбой канала уведомления не валит создание заявки."""

from __future__ import annotations

import logging

logger = logging.getLogger("apps.leads")


def notify_new_inquiry(sender, inquiry_id, kind, product_id, **kwargs):
    """Реакция на product_inquiry_created: уведомить менеджеров.

    Пока — лог (канал email/Telegram подключим отдельной задачей). Исключения
    глушим: заявка уже сохранена, потеря уведомления не должна ломать ответ API.
    """
    try:
        logger.info(
            "Новая заявка #%s (%s) по товару %s", inquiry_id, kind, product_id
        )
    except Exception:  # noqa: BLE001 — уведомление не критично
        logger.exception("Сбой обработки product_inquiry_created")
```

- [ ] **Step 4: Подключить подписчик в AppConfig.ready под флагом**

Заменить `apps/leads/apps.py` целиком:

```python
from django.apps import AppConfig


class LeadsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.leads"
    verbose_name = "Заявки"

    def ready(self):
        from apps.core.features import is_enabled
        from apps.core.events import product_inquiry_created
        from . import receivers

        if is_enabled("eventbus"):
            product_inquiry_created.connect(
                receivers.notify_new_inquiry, dispatch_uid="leads.notify_new_inquiry"
            )
```

- [ ] **Step 5: Запустить тест и общую проверку**

Run: `docker exec proff58-web-1 pytest apps/leads/tests/test_receivers.py -v && docker exec proff58-web-1 python manage.py check`
Expected: PASS, check без ошибок.

- [ ] **Step 6: Коммит**

```bash
git add apps/leads/receivers.py apps/leads/apps.py apps/leads/tests/test_receivers.py
git commit -m "feat(leads): подписчик-уведомление о новой заявке (под eventbus)"
```

---

### Task 7: Next BFF-роут `/api/inquiry`

**Files:**
- Create: `frontend/app/api/inquiry/route.ts`

**Interfaces:**
- Consumes: `proxyToDjango` из `@/lib/bff`; Django `POST /api/leads/inquiries/`.
- Produces: `POST /api/inquiry` — проксирует тело на Django, возвращает его статус/ответ.

- [ ] **Step 1: Реализовать BFF-роут (паттерн как у orders)**

Создать `frontend/app/api/inquiry/route.ts`:

```typescript
// BFF: POST /api/inquiry → Django /api/leads/inquiries/ (заявка с карточки товара).
// Тело валидируется на стороне Django (ProductInquirySerializer); здесь — тонкий прокси.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/leads/inquiries/", { method: "POST", body });
}
```

- [ ] **Step 2: Проверка вручную (стек поднят, данные staging залиты)**

Взять реальный id товара:

```bash
docker exec proff58-db-1 psql -U proff -d proff58 -t -c "SELECT id, slug FROM catalog_product LIMIT 1;"
```

Отправить заявку напрямую в Django (подставить id из вывода):

```bash
curl -s -X POST http://localhost:8000/api/leads/inquiries/ \
  -H 'Content-Type: application/json' \
  -d '{"kind":"price_request","product":<ID>,"phone":"89990000009"}' -w '\n%{http_code}\n'
```

Expected: тело с `"status":"new"` и HTTP `201`.
> BFF `/api/inquiry` проверяется так же на `http://localhost:3000`, если поднят
> фронт-контейнер (в dev-compose витрина не поднимается — тогда достаточно
> проверки Django выше; BFF покрывается при работе над планом 2).

- [ ] **Step 3: Коммит**

```bash
git add frontend/app/api/inquiry/route.ts
git commit -m "feat(frontend): BFF-роут /api/inquiry → leads"
```

---

## Финальная проверка плана 1

- [ ] Весь набор тестов приложения зелёный:
  `docker exec proff58-web-1 pytest apps/leads -v`
- [ ] Нет неприменённых/недостающих миграций:
  `docker exec proff58-web-1 python manage.py makemigrations --check --dry-run`
- [ ] `ruff check apps/leads && black --check apps/leads`
- [ ] `docker exec proff58-web-1 python manage.py check`

## Self-review (соответствие спеку)

- Модель `ProductInquiry` (kind/product/phone/name/message/status) — Task 1. ✓
- Throttle, без auth, create-only `201/400/429` — Task 4. ✓
- Доменное событие через on_commit — Task 2; подписчик под eventbus, сбой не валит — Task 6. ✓
- Админ-модерация — Task 5. ✓
- BFF-роут — Task 7. ✓
- Размещение в новом `apps/leads` — Task 1. ✓
- Поля времени `created_at/updated_at` (из TimeStampedModel) — соответствует Global Constraints (в спеке были названы created/modified — здесь приведено к фактическим именам базовой модели). ✓

## Дальше (отдельные планы того же куска A)

- **План 2:** блок покупки (QuantityStepper, OrderCta qty/order, InquiryDialog → `/api/inquiry`, StickyBuyBar).
- **План 3:** галерея (клавиатура/свайп/lightbox/lazy).
- **План 4:** контент/SEO (Product JSON-LD, Collapsible, Share) + a11y-аудит и регрессия.
