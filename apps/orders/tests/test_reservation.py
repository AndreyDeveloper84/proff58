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


# ── TTL по типу покупателя (#568) ──────────────────────────────────────


def _ttl_window(before, after, delta: timedelta):
    """Интервал допустимых значений reserved_until для TTL, взятого до/после вызова."""
    return before + delta, after + delta


B2B_DATA = {
    "customer_name": "Иван Петров",
    "customer_phone": "+79001234567",
    "customer_email": "buh@romashka.ru",
    "customer_type": "b2b",
    "company_name": "ООО «Ромашка»",
    "inn": "7700000000",
    "kpp": "770001001",
    "legal_address": "г. Пенза, ул. Ленина, 1",
}


@pytest.mark.django_db
def test_b2c_reservation_ttl_is_30_minutes(cart, product):
    add_to_cart(cart, product, 1)
    before = timezone.now()
    order = place_order(
        cart,
        user=None,
        customer_data={"customer_name": "Гость", "customer_phone": "+79990099099"},
    )
    after = timezone.now()
    lo, hi = _ttl_window(before, after, timedelta(minutes=30))
    assert lo <= order.reserved_until <= hi


@pytest.mark.django_db
def test_b2c_ttl_configurable(cart, product, settings):
    settings.RESERVATION_TTL_B2C_MINUTES = 5
    add_to_cart(cart, product, 1)
    before = timezone.now()
    order = place_order(
        cart,
        user=None,
        customer_data={"customer_name": "Гость", "customer_phone": "+79990099099"},
    )
    after = timezone.now()
    lo, hi = _ttl_window(before, after, timedelta(minutes=5))
    assert lo <= order.reserved_until <= hi


@pytest.mark.django_db
def test_authenticated_b2c_ttl_is_30_minutes(cart, product, b2c_user):
    add_to_cart(cart, product, 1)
    before = timezone.now()
    order = place_order(cart, user=b2c_user, customer_data={})
    after = timezone.now()
    lo, hi = _ttl_window(before, after, timedelta(minutes=30))
    assert lo <= order.reserved_until <= hi


@pytest.mark.django_db
def test_b2b_reservation_ttl_stays_24_hours(cart, product, b2b_user):
    add_to_cart(cart, product, 1)
    before = timezone.now()
    order = place_order(cart, user=b2b_user, customer_data={})
    after = timezone.now()
    lo, hi = _ttl_window(before, after, timedelta(hours=24))
    assert lo <= order.reserved_until <= hi
    # Инвариант #559: счёт и резерв истекают вместе.
    assert order.b2b_invoice.valid_until == order.reserved_until


@pytest.mark.django_db
def test_guest_b2b_ttl_stays_24_hours(cart, product):
    """Гостевой B2B (customer_type из тела) тоже получает 24ч, а не 30 мин."""
    add_to_cart(cart, product, 1)
    before = timezone.now()
    order = place_order(cart, user=None, customer_data=dict(B2B_DATA))
    after = timezone.now()
    lo, hi = _ttl_window(before, after, timedelta(hours=24))
    assert lo <= order.reserved_until <= hi


# ── удаление заказа мимо release_reservation (DRF-1002) ────────────────


@pytest.mark.django_db
def test_delete_order_instance_returns_stock():
    """Удаление объекта (админка вызывает именно его) снимает резерв."""
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    order.delete()

    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")  # 7 + 3
    assert p.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_delete_order_via_queryset_returns_stock():
    """Массовое удаление тоже снимает резерв: сигнал отключает fast-delete."""
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    Order.objects.filter(pk=order.pk).delete()

    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")
    assert p.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_delete_after_release_does_not_restore_twice():
    """Штатный путь не ломается: резерв уже возвращён, удаление ничего не добавляет."""
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)
    assert release_reservation(order.pk) is True

    order.delete()

    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")  # ровно один возврат
    assert p.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_delete_confirmed_order_keeps_stock():
    """CONFIRMED — товар уже ушёл; удаление заказа не возвращает его на склад."""
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)
    assert confirm_reservation(order.pk) is True

    order.delete()

    p.refresh_from_db()
    assert p.available_quantity == Decimal("7")
    assert p.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_delete_product_then_order_does_not_break():
    """Удалили товар — возвращать остаток некуда; строка заказа переживает (SET_NULL)."""
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    p.delete()
    item = OrderItem.objects.get(order=order)
    assert item.product_id is None

    order.delete()  # не падает: строки без товара пропускаются

    assert not Order.objects.filter(pk=order.pk).exists()
