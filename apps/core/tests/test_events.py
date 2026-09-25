"""Тесты реестра доменных событий (#70) — payload на стабильных id."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.dispatch import Signal
from django.test import RequestFactory

from apps.accounts.models import User
from apps.catalog.admin import ProductAdmin
from apps.catalog.models import Category, Product, ProductStatus
from apps.core import events
from apps.sync_1c import use_cases

ALL_SIGNALS = [
    "user_registered",
    "b2b_verified",
    "product_created",
    "product_updated",
    "order_created",
    "order_paid",
    "order_status_changed",
    "payment_succeeded",
    "payment_failed",
    "price_changed",
]


def test_all_signals_declared():
    """Все 10 доменных сигналов объявлены в едином реестре core.events."""
    for name in ALL_SIGNALS:
        assert isinstance(getattr(events, name), Signal), name


def test_event_source_values():
    assert events.EventSource.ADMIN == "admin"
    assert events.EventSource.ONE_C == "1c"


@pytest.mark.django_db
def test_user_registered_emits_user_id(django_capture_on_commit_callbacks):
    received = []

    def handler(sender, user_id, **kwargs):
        received.append(user_id)

    events.user_registered.connect(handler)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            user = User.objects.create_user(phone="+79990001122", password="pwd12345")
    finally:
        events.user_registered.disconnect(handler)
    assert received == [user.pk]


@pytest.mark.django_db
def test_product_created_emits_id_and_source(django_capture_on_commit_callbacks):
    got = []

    def handler(sender, product_id, source, **kwargs):
        got.append((product_id, source))

    events.product_created.connect(handler)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            use_cases.import_products([{"external_id": "ev-1", "name": "Дрель", "price": "100"}])
    finally:
        events.product_created.disconnect(handler)

    pid = Product.objects.get(code_1c="ev-1").pk
    assert (pid, "1c") in got


@pytest.mark.django_db
def test_product_updated_only_on_real_change(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        use_cases.import_products([{"external_id": "ev-2", "name": "Пила", "price": "100"}])

    updates = []

    def handler(sender, product_id, source, changed_fields, **kwargs):
        updates.append((product_id, source, changed_fields))

    events.product_updated.connect(handler)
    try:
        # реальное изменение цены → одно событие с changed_fields
        with django_capture_on_commit_callbacks(execute=True):
            use_cases.update_products([{"external_id": "ev-2", "price": "200"}])
        # повтор без изменений → события быть не должно
        with django_capture_on_commit_callbacks(execute=True):
            use_cases.update_products([{"external_id": "ev-2", "price": "200"}])
    finally:
        events.product_updated.disconnect(handler)

    pid = Product.objects.get(code_1c="ev-2").pk
    assert len(updates) == 1
    assert updates[0][0] == pid
    assert updates[0][1] == "1c"
    assert "price" in updates[0][2]


def _admin_request():
    request = RequestFactory().post("/admin/")
    request.session = "s"
    request._messages = FallbackStorage(request)
    return request


@pytest.mark.django_db
def test_bulk_publish_emits_only_for_changed(django_capture_on_commit_callbacks):
    # Категория без обязательных характеристик → товары проходят правило публикации
    # (action_publish теперь валидирует категорию/обязательные характеристики, #18).
    cat = Category.add_root(name="Готовая категория", slug="ready-cat-events")
    draft1 = Product.objects.create(
        name="Черновик 1", status=ProductStatus.DRAFT, is_active=False, category=cat
    )
    draft2 = Product.objects.create(
        name="Черновик 2", status=ProductStatus.DRAFT, is_active=False, category=cat
    )
    # уже опубликован и активен — не должен порождать событие
    Product.objects.create(
        name="Готовый", status=ProductStatus.PUBLISHED, is_active=True, category=cat
    )

    events_got = []

    def handler(sender, product_id, source, changed_fields, **kwargs):
        events_got.append((product_id, source, tuple(changed_fields)))

    ma = ProductAdmin(Product, AdminSite())
    request = _admin_request()

    events.product_updated.connect(handler)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            ma.action_publish(request, Product.objects.all())
        # ровно по числу реально изменённых (2 черновика)
        assert len(events_got) == 2
        ids = {e[0] for e in events_got}
        assert ids == {draft1.pk, draft2.pk}
        for _pid, source, changed in events_got:
            assert source == "admin"
            assert changed == ("status", "is_active")

        # повторная публикация — все уже опубликованы → событий нет
        events_got.clear()
        with django_capture_on_commit_callbacks(execute=True):
            ma.action_publish(request, Product.objects.all())
        assert events_got == []
    finally:
        events.product_updated.disconnect(handler)
