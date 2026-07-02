"""Тесты жизненного цикла резерва склада (#423, B-03).

Покрывает: reserve при оформлении (TTL + HELD), release, confirm, идемпотентность
(двойной release/confirm), janitor просрочки, приём событий оплаты.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Product, ProductStatus
from apps.core import events
from apps.orders.models import (
    Order,
    OrderItem,
    PaymentStatus,
    ReservationStatus,
)
from apps.orders.reservation import confirm_reservation, release_reservation
from apps.orders.services import add_to_cart, place_order
from apps.orders.tasks import release_expired_reservations


def _product(qty="10", reserved="0"):
    return Product.objects.create(
        name="Товар",
        code_1c="res-1",
        slug="res-1",
        unit="шт",
        price=Decimal("100.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal(qty),
        reserved_quantity=Decimal(reserved),
    )


def _order_with_item(product, qty=3, **order_kw):
    defaults = dict(
        order_number=f"RES-{timezone.now().timestamp()}",
        reservation_status=ReservationStatus.HELD,
        customer_phone="+79001112233",
    )
    defaults.update(order_kw)
    order = Order.objects.create(**defaults)
    OrderItem.objects.create(
        order=order,
        product=product,
        quantity=qty,
        price_final=Decimal("100.00"),
        line_total=Decimal("100.00") * qty,
    )
    return order


# ── reserve at checkout ────────────────────────────────────────────────


@pytest.mark.django_db
def test_place_order_sets_held_and_ttl(cart, product):
    product.available_quantity = Decimal("5")
    product.save(update_fields=["available_quantity"])
    add_to_cart(cart, product, 2)

    order = place_order(
        cart,
        user=None,
        customer_data={"customer_name": "Гость", "customer_phone": "+79990099099"},
    )
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.HELD
    assert order.reserved_until is not None
    assert order.reserved_until > timezone.now()


# ── release ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_release_returns_stock_and_marks_released():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    assert release_reservation(order.pk) is True
    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")  # 7 + 3
    assert p.reserved_quantity == Decimal("0")  # 3 - 3
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.RELEASED


@pytest.mark.django_db
def test_release_idempotent_no_double_restore():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    assert release_reservation(order.pk) is True
    assert release_reservation(order.pk) is False  # уже released
    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")  # без двойного возврата
    assert p.reserved_quantity == Decimal("0")


# ── confirm ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_confirm_drops_reserved_keeps_available():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    assert confirm_reservation(order.pk) is True
    p.refresh_from_db()
    assert p.available_quantity == Decimal("7")  # не меняется — товар уже ушёл из available
    assert p.reserved_quantity == Decimal("0")  # 3 - 3
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.CONFIRMED


@pytest.mark.django_db
def test_confirm_idempotent():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    assert confirm_reservation(order.pk) is True
    assert confirm_reservation(order.pk) is False
    p.refresh_from_db()
    assert p.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_confirmed_cannot_be_released():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)
    confirm_reservation(order.pk)

    assert release_reservation(order.pk) is False  # CONFIRMED терминален для release
    p.refresh_from_db()
    assert p.available_quantity == Decimal("7")  # не восстановился


# ── janitor ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_janitor_releases_expired_unpaid():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(
        p,
        qty=3,
        reserved_until=timezone.now() - timedelta(minutes=1),
        payment_status=PaymentStatus.PENDING,
    )

    assert release_expired_reservations() == 1
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.RELEASED
    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")


@pytest.mark.django_db
def test_janitor_skips_paid_orders():
    p = _product(qty="7", reserved="3")
    _order_with_item(
        p,
        qty=3,
        reserved_until=timezone.now() - timedelta(minutes=1),
        payment_status=PaymentStatus.PAID,
    )

    assert release_expired_reservations() == 0
    p.refresh_from_db()
    assert p.reserved_quantity == Decimal("3")  # не тронут


@pytest.mark.django_db
def test_janitor_skips_not_yet_expired():
    p = _product(qty="7", reserved="3")
    _order_with_item(
        p,
        qty=3,
        reserved_until=timezone.now() + timedelta(hours=1),
        payment_status=PaymentStatus.PENDING,
    )

    assert release_expired_reservations() == 0
    p.refresh_from_db()
    assert p.reserved_quantity == Decimal("3")


# ── payment events → confirm/release ───────────────────────────────────


@pytest.mark.django_db
def test_payment_succeeded_confirms_reservation():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    events.payment_succeeded.send(sender=None, order_id=order.pk, payment_id=1)
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.CONFIRMED


@pytest.mark.django_db
def test_payment_failed_releases_reservation():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    events.payment_failed.send(sender=None, order_id=order.pk, payment_id=1, reason="expired")
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.RELEASED
    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")


@pytest.mark.django_db
def test_repeat_payment_succeeded_is_idempotent():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    events.payment_succeeded.send(sender=None, order_id=order.pk, payment_id=1)
    events.payment_succeeded.send(sender=None, order_id=order.pk, payment_id=1)
    p.refresh_from_db()
    assert p.reserved_quantity == Decimal("0")  # без двойного списания
