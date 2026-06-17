"""Тесты реестра доменных событий (#70)."""

import pytest
from django.dispatch import Signal

from apps.accounts.models import User
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


@pytest.mark.django_db
def test_user_registered_emitted(django_capture_on_commit_callbacks):
    received = []

    def handler(sender, user, **kwargs):
        received.append(user)

    events.user_registered.connect(handler)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            user = User.objects.create_user(phone="+79990001122", password="pwd12345")
    finally:
        events.user_registered.disconnect(handler)
    assert received == [user]


@pytest.mark.django_db
def test_product_created_emitted_with_source(django_capture_on_commit_callbacks):
    got = []

    def handler(sender, product, source, **kwargs):
        got.append((product.code_1c, source))

    events.product_created.connect(handler)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            use_cases.import_products([{"external_id": "ev-1", "name": "Дрель", "price": "100"}])
    finally:
        events.product_created.disconnect(handler)
    assert ("ev-1", "1c") in got


@pytest.mark.django_db
def test_product_updated_only_on_real_change(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        use_cases.import_products([{"external_id": "ev-2", "name": "Пила", "price": "100"}])

    updates = []

    def handler(sender, product, source, changed_fields, **kwargs):
        updates.append(changed_fields)

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

    assert len(updates) == 1
    assert "price" in updates[0]
