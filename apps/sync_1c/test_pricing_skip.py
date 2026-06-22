"""Тесты skip-unchanged-price (reliability PR-1): не плодить PriceRecord."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.models import Product
from apps.core.events import price_changed
from apps.pricing.models import PriceRecord
from apps.sync_1c import use_cases


@pytest.mark.django_db
def test_unchanged_price_is_skipped():
    """Повторная та же цена → skipped, история PriceRecord не растёт."""
    Product.objects.create(name="Т", code_1c="1c-skip", slug="skip")

    _, r1 = use_cases.update_prices([{"external_id": "1c-skip", "price": "100"}])
    assert (r1.updated, r1.skipped) == (1, 0)
    assert PriceRecord.objects.filter(code_1c="1c-skip").count() == 1

    _, r2 = use_cases.update_prices([{"external_id": "1c-skip", "price": "100"}])
    assert (r2.updated, r2.skipped) == (0, 1)
    assert PriceRecord.objects.filter(code_1c="1c-skip").count() == 1
    assert PriceRecord.objects.filter(code_1c="1c-skip", is_current=True).count() == 1


@pytest.mark.django_db
def test_changed_price_creates_new_record():
    """Изменение цены → новая актуальная запись, старая снята с актуальности."""
    p = Product.objects.create(name="Т", code_1c="1c-chg", slug="chg")
    use_cases.update_prices([{"external_id": "1c-chg", "price": "100"}])
    _, r = use_cases.update_prices([{"external_id": "1c-chg", "price": "150"}])

    assert (r.updated, r.skipped) == (1, 0)
    assert PriceRecord.objects.filter(code_1c="1c-chg").count() == 2
    current = PriceRecord.objects.get(code_1c="1c-chg", is_current=True)
    assert current.value == Decimal("150")
    p.refresh_from_db()
    assert p.price == Decimal("150")


@pytest.mark.django_db
def test_only_old_price_change_updates():
    """Та же price, но изменился old_price → это значимое изменение (скидка)."""
    p = Product.objects.create(name="Т", code_1c="1c-op", slug="op")
    use_cases.update_prices([{"external_id": "1c-op", "price": "100"}])
    _, r = use_cases.update_prices([{"external_id": "1c-op", "price": "100", "old_price": "120"}])

    assert (r.updated, r.skipped) == (1, 0)
    p.refresh_from_db()
    assert p.old_price == Decimal("120")


@pytest.mark.django_db
def test_price_update_emits_price_changed(django_capture_on_commit_callbacks):
    """1С-обновление цены публикует price_changed (через transaction.on_commit)."""
    Product.objects.create(name="Т", code_1c="1c-emit", slug="emit", price=Decimal("100.00"))
    received: list[dict] = []

    def handler(sender, **kw):
        received.append(kw)

    price_changed.connect(handler)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            use_cases.update_prices([{"external_id": "1c-emit", "price": "150"}])
    finally:
        price_changed.disconnect(handler)

    assert len(received) == 1
    assert received[0]["new_price"] == Decimal("150")
    assert received[0]["old_price"] == Decimal("100.00")
    assert received[0]["currency"] == "RUB"
    assert received[0]["source"] == "1c"


@pytest.mark.django_db
def test_unchanged_price_does_not_emit_price_changed(django_capture_on_commit_callbacks):
    """При неизменной цене price_changed НЕ эмитится."""
    Product.objects.create(name="Т", code_1c="1c-ev", slug="ev")
    use_cases.update_prices([{"external_id": "1c-ev", "price": "100"}])  # стартовая

    received: list[dict] = []

    def handler(sender, **kw):
        received.append(kw)

    price_changed.connect(handler)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            use_cases.update_prices([{"external_id": "1c-ev", "price": "100"}])  # без изменений
    finally:
        price_changed.disconnect(handler)

    assert received == []
