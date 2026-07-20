"""#559 (эпик #557): lifecycle B2B-счёта — 24ч, отмена заказа, снятие резерва.

Инварианты: счёт выставляется при оформлении B2B-заказа и живёт ровно до
``reserved_until``; истечение атомарно отменяет заказ и возвращает резерв
(двойной возврат невозможен); оплата списывает резерв, а не освобождает.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.orders.invoice_lifecycle import expire_due_invoices, mark_invoice_paid
from apps.orders.models import (
    B2BInvoice,
    FulfillmentStatus,
    InvoiceStatus,
    PaymentStatus,
    ReservationStatus,
)
from apps.orders.services import add_to_cart, place_order
from apps.orders.tasks import expire_b2b_invoices, release_expired_reservations


def _b2b():
    return {
        "customer_name": "Иван Петров",
        "customer_phone": "+79001234567",
        "customer_email": "buh@romashka.ru",
        "customer_type": "b2b",
        "company_name": "ООО «Ромашка»",
        "inn": "7700000000",
        "kpp": "770001001",
        "legal_address": "г. Пенза, ул. Ленина, 1",
    }


def _b2b_order(cart, product, qty: int = 2):
    add_to_cart(cart, product, qty)
    return place_order(cart, customer_data=_b2b())


def _make_overdue(order):
    """Сдвинуть срок счёта и резерва в прошлое (симуляция истечения 24ч)."""
    past = timezone.now() - timezone.timedelta(minutes=1)
    B2BInvoice.objects.filter(order=order).update(valid_until=past)
    type(order).objects.filter(pk=order.pk).update(reserved_until=past)


# ═══════════ Выставление ═══════════


@pytest.mark.django_db
def test_invoice_issued_on_b2b_order(cart, product):
    order = _b2b_order(cart, product)
    invoice = order.b2b_invoice
    assert invoice.status == InvoiceStatus.ISSUED
    assert invoice.number == f"СЧ-{order.order_number}"
    # Счёт и резерв истекают в один момент (24ч).
    assert invoice.valid_until == order.reserved_until
    assert invoice.paid_at is None


@pytest.mark.django_db
def test_no_invoice_for_b2c(cart, product):
    add_to_cart(cart, product, 1)
    order = place_order(
        cart, customer_data={"customer_name": "Гость", "customer_phone": "+79001234567"}
    )
    assert not B2BInvoice.objects.filter(order=order).exists()


# ═══════════ Истечение ═══════════


@pytest.mark.django_db
def test_expiry_cancels_order_and_releases_reservation(cart, product):
    order = _b2b_order(cart, product, qty=2)
    product.refresh_from_db()
    assert product.available_quantity == Decimal("8")  # 10 - 2 в резерве
    _make_overdue(order)

    assert expire_due_invoices() == 1

    order.refresh_from_db()
    invoice = order.b2b_invoice
    assert invoice.status == InvoiceStatus.EXPIRED
    assert order.payment_status == PaymentStatus.EXPIRED
    assert order.fulfillment_status == FulfillmentStatus.CANCELLED
    assert order.reservation_status == ReservationStatus.RELEASED
    product.refresh_from_db()
    assert product.available_quantity == Decimal("10")  # резерв вернулся
    assert product.reserved_quantity == Decimal("0")
    assert order.display_status == "Заказ отменён (не оплачен вовремя)"


@pytest.mark.django_db
def test_expiry_idempotent_no_double_release(cart, product):
    """Повторный janitor и старый release-janitor не возвращают остаток дважды."""
    order = _b2b_order(cart, product, qty=2)
    _make_overdue(order)

    assert expire_due_invoices() == 1
    assert expire_due_invoices() == 0  # повтор — no-op
    release_expired_reservations()  # старый janitor поверх — тоже no-op

    product.refresh_from_db()
    assert product.available_quantity == Decimal("10")
    assert product.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_expiry_skips_paid_order(cart, product):
    """Оплату отметили мимо счёта → счёт выравнивается в PAID, заказ не отменяется."""
    order = _b2b_order(cart, product)
    type(order).objects.filter(pk=order.pk).update(payment_status=PaymentStatus.PAID)
    _make_overdue(order)

    assert expire_due_invoices() == 0

    order.refresh_from_db()
    assert order.b2b_invoice.status == InvoiceStatus.PAID
    assert order.fulfillment_status != FulfillmentStatus.CANCELLED
    assert order.payment_status == PaymentStatus.PAID


@pytest.mark.django_db
def test_active_invoice_not_expired(cart, product):
    order = _b2b_order(cart, product)
    assert expire_due_invoices() == 0
    assert order.b2b_invoice.status == InvoiceStatus.ISSUED


@pytest.mark.django_db
def test_celery_task_wrapper(cart, product):
    order = _b2b_order(cart, product)
    _make_overdue(order)
    assert expire_b2b_invoices() == 1


# ═══════════ Оплата ═══════════


@pytest.mark.django_db
def test_mark_paid_confirms_reservation(cart, product):
    order = _b2b_order(cart, product, qty=2)
    invoice = mark_invoice_paid(order.b2b_invoice.pk)

    order.refresh_from_db()
    assert invoice.status == InvoiceStatus.PAID
    assert invoice.paid_at is not None
    assert order.payment_status == PaymentStatus.PAID
    # Резерв СПИСАН (товар уходит), а не возвращён в свободный остаток.
    assert order.reservation_status == ReservationStatus.CONFIRMED
    product.refresh_from_db()
    assert product.available_quantity == Decimal("8")
    assert product.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_mark_paid_idempotent(cart, product):
    order = _b2b_order(cart, product)
    mark_invoice_paid(order.b2b_invoice.pk)
    invoice = mark_invoice_paid(order.b2b_invoice.pk)  # повтор — no-op
    assert invoice.status == InvoiceStatus.PAID


@pytest.mark.django_db
def test_mark_paid_rejects_expired(cart, product):
    """После истечения заказ отменён и резерв возвращён — «оживление» запрещено."""
    order = _b2b_order(cart, product)
    _make_overdue(order)
    expire_due_invoices()
    with pytest.raises(ValidationError, match="нельзя отметить оплаченным"):
        mark_invoice_paid(order.b2b_invoice.pk)


@pytest.mark.django_db
def test_paid_invoice_survives_reservation_janitor(cart, product):
    """Оплаченный заказ не трогается ни одним janitor'ом."""
    order = _b2b_order(cart, product)
    mark_invoice_paid(order.b2b_invoice.pk)
    _make_overdue(order)  # даже если сроки в прошлом

    assert expire_due_invoices() == 0
    release_expired_reservations()

    order.refresh_from_db()
    assert order.payment_status == PaymentStatus.PAID
    assert order.reservation_status == ReservationStatus.CONFIRMED
    assert order.b2b_invoice.status == InvoiceStatus.PAID
