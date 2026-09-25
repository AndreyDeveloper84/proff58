"""Тесты моделей заказа: display_status (производный статус) по
docs/order-lifecycle.md раздел 6.
"""

from __future__ import annotations

import pytest

from apps.orders.models import (
    FulfillmentStatus,
    Order,
    PaymentStatus,
    Sync1CStatus,
)


def _order(**kw) -> Order:
    return Order(order_number="X", **kw)


@pytest.mark.parametrize(
    ("fulfillment", "payment", "expected"),
    [
        (FulfillmentStatus.NEW, PaymentStatus.PENDING, "Ожидает оплаты"),
        (FulfillmentStatus.NEW, PaymentStatus.PAID, "Оплачен, передаётся в обработку"),
        (FulfillmentStatus.CONFIRMED, PaymentStatus.PAID, "Подтверждён"),
        (FulfillmentStatus.ASSEMBLING, PaymentStatus.PENDING, "Собирается"),
        (FulfillmentStatus.READY, PaymentStatus.PAID, "Готов к выдаче"),
        (FulfillmentStatus.SHIPPED, PaymentStatus.PAID, "В доставке"),
        (FulfillmentStatus.COMPLETED, PaymentStatus.PAID, "Выполнен"),
    ],
)
def test_display_status_basic(fulfillment, payment, expected):
    order = _order(fulfillment_status=fulfillment, payment_status=payment)
    assert order.display_status == expected


def test_display_status_cancelled():
    order = _order(
        fulfillment_status=FulfillmentStatus.CANCELLED, payment_status=PaymentStatus.PENDING
    )
    assert order.display_status == "Заказ отменён"


def test_display_status_refunded():
    """Возврат имеет приоритет над осью обработки."""
    order = _order(
        fulfillment_status=FulfillmentStatus.COMPLETED, payment_status=PaymentStatus.REFUNDED
    )
    assert order.display_status == "Возврат оформлен"


def test_display_status_expired():
    """Просроченная оплата — терминальное состояние с приоритетом."""
    order = _order(fulfillment_status=FulfillmentStatus.NEW, payment_status=PaymentStatus.EXPIRED)
    assert order.display_status == "Заказ отменён (не оплачен вовремя)"


def test_status_values_match_doc():
    """Имена и значения статусов строго из docs/order-lifecycle.md."""
    assert FulfillmentStatus.NEW.value == "new"
    assert FulfillmentStatus.CONFIRMED.value == "confirmed"
    assert FulfillmentStatus.ASSEMBLING.value == "assembling"
    assert FulfillmentStatus.READY.value == "ready"
    assert FulfillmentStatus.SHIPPED.value == "shipped"
    assert FulfillmentStatus.COMPLETED.value == "completed"
    assert FulfillmentStatus.CANCELLED.value == "cancelled"
    assert PaymentStatus.PENDING.value == "pending"
    assert PaymentStatus.PAID.value == "paid"
    assert PaymentStatus.EXPIRED.value == "expired"
    assert PaymentStatus.REFUNDED.value == "refunded"
    assert Sync1CStatus.PENDING.value == "pending"
    assert Sync1CStatus.EXPORTED.value == "exported"
    # Запрещённые значения не используются
    all_values = (
        set(FulfillmentStatus.values) | set(PaymentStatus.values) | set(Sync1CStatus.values)
    )
    assert "unpaid" not in all_values
    assert "not_synced" not in all_values
    assert "ready_for_pickup" not in all_values
