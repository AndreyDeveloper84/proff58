"""Тесты сервисного слоя: place_order, корзина, снимки, события."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.catalog.models import ProductStatus
from apps.core.events import order_created
from apps.orders.models import (
    CartStatus,
    FulfillmentStatus,
    PaymentStatus,
    Sync1CStatus,
)
from apps.orders.services import (
    add_to_cart,
    get_cart_view,
    place_order,
    update_cart_item,
)
from apps.pricing.services import WHOLESALE

from .conftest import make_wholesale


# ---------------------------------------------------------------------------
# Стартовые статусы
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_place_order_initial_statuses(cart_with_item):
    order = place_order(cart_with_item, user=None, customer_data={"customer_name": "Гость"})
    assert order.fulfillment_status == FulfillmentStatus.NEW
    assert order.payment_status == PaymentStatus.PENDING
    assert order.sync_1c_status == Sync1CStatus.PENDING


@pytest.mark.django_db
def test_place_order_generates_unique_number(cart_with_item):
    order = place_order(cart_with_item, user=None, customer_data={"customer_name": "Гость"})
    assert order.order_number
    assert order.display_status == "Ожидает оплаты"


# ---------------------------------------------------------------------------
# Итоги
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_total_equals_sum_of_line_totals(cart, product, product2):
    add_to_cart(cart, product, 2)  # 1000 * 2 = 2000
    add_to_cart(cart, product2, 3)  # 500 * 3 = 1500
    order = place_order(cart, user=None, customer_data={"customer_name": "Гость"})
    line_sum = sum(i.line_total for i in order.items.all())
    assert order.total == line_sum == Decimal("3500.00")


# ---------------------------------------------------------------------------
# Жизненный цикл корзины + идемпотентность
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_cart_becomes_ordered(cart_with_item):
    place_order(cart_with_item, user=None, customer_data={"customer_name": "Гость"})
    cart_with_item.refresh_from_db()
    assert cart_with_item.status == CartStatus.ORDERED
    assert cart_with_item.ordered_at is not None
    # Строки физически не удалены
    assert cart_with_item.items.count() == 1


@pytest.mark.django_db
def test_place_order_on_ordered_cart_raises(cart_with_item):
    place_order(cart_with_item, user=None, customer_data={"customer_name": "Гость"})
    with pytest.raises(ValidationError):
        place_order(cart_with_item, user=None, customer_data={"customer_name": "Гость"})


@pytest.mark.django_db
def test_place_order_empty_cart_raises(cart):
    with pytest.raises(ValidationError):
        place_order(cart, user=None, customer_data={"customer_name": "Гость"})


# ---------------------------------------------------------------------------
# Снимок цены (snapshot-инвариант)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_snapshot_invariant_price_change(cart_with_item, product):
    order = place_order(cart_with_item, user=None, customer_data={"customer_name": "Гость"})
    item = order.items.first()
    assert item.price_final == Decimal("1000.00")

    # Меняем цену товара ПОСЛЕ заказа — снимок не должен поплыть.
    product.price = Decimal("9999.00")
    product.save(update_fields=["price"])
    item.refresh_from_db()
    assert item.price_final == Decimal("1000.00")
    assert item.line_total == Decimal("2000.00")


@pytest.mark.django_db
def test_snapshot_survives_product_delete(cart_with_item, product):
    order = place_order(cart_with_item, user=None, customer_data={"customer_name": "Гость"})
    product.delete()
    item = order.items.first()
    item.refresh_from_db()
    assert item.product_id is None  # SET_NULL
    assert item.name == "Дрель"
    assert item.price_final == Decimal("1000.00")


# ---------------------------------------------------------------------------
# B2B путь
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_b2b_uses_wholesale_and_snapshots_requisites(cart, product, b2b_user):
    make_wholesale(product, "800.00")
    add_to_cart(cart, product, 2)
    order = place_order(cart, user=b2b_user, customer_data={})

    item = order.items.first()
    assert item.price_type == WHOLESALE
    assert item.price_final == Decimal("800.00")
    assert order.total == Decimal("1600.00")

    # Снимок реквизитов из профиля
    assert order.customer_type == "b2b"
    assert order.inn == "7700000000"
    assert order.kpp == "770001001"
    assert order.legal_address == "г. Пенза, ул. Ленина, 1"
    assert order.company_name == "ООО Профи"


# ---------------------------------------------------------------------------
# Негативные сценарии checkout
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_checkout_hidden_product_raises(cart, product):
    add_to_cart(cart, product, 1)
    product.status = ProductStatus.DRAFT
    product.save(update_fields=["status"])
    with pytest.raises(ValidationError):
        place_order(cart, user=None, customer_data={"customer_name": "Гость"})


@pytest.mark.django_db
def test_checkout_product_without_price_raises(cart, product):
    add_to_cart(cart, product, 1)
    product.price = None
    product.save(update_fields=["price"])
    with pytest.raises(ValidationError):
        place_order(cart, user=None, customer_data={"customer_name": "Гость"})


@pytest.mark.django_db
def test_checkout_qty_over_available_raises(cart, product):
    add_to_cart(cart, product, 1)
    product.available_quantity = Decimal("0")
    product.save(update_fields=["available_quantity"])
    with pytest.raises(ValidationError):
        place_order(cart, user=None, customer_data={"customer_name": "Гость"})


# ---------------------------------------------------------------------------
# Корзина: валидация qty
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_add_to_cart_qty_below_one_raises(cart, product):
    with pytest.raises(ValidationError):
        add_to_cart(cart, product, 0)


@pytest.mark.django_db
def test_update_cart_item_qty_below_one_raises(cart_with_item):
    item = cart_with_item.items.first()
    with pytest.raises(ValidationError):
        update_cart_item(item, 0)


@pytest.mark.django_db
def test_get_cart_view_uses_live_price(cart, product, b2b_user):
    """Цена в корзине — серверная и актуальная (B2B видит опт)."""
    make_wholesale(product, "800.00")
    add_to_cart(cart, product, 2)
    view = get_cart_view(cart, b2b_user)
    assert view.lines[0].price_final == Decimal("800.00")
    assert view.total == Decimal("1600.00")


# ---------------------------------------------------------------------------
# Событие order_created — ровно один раз на commit
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_order_created_emitted_once(cart_with_item, django_capture_on_commit_callbacks):
    received: list[dict] = []

    def handler(sender, **kw):
        received.append(kw)

    order_created.connect(handler)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            order = place_order(cart_with_item, user=None, customer_data={"customer_name": "Гость"})
    finally:
        order_created.disconnect(handler)

    assert len(received) == 1
    assert received[0]["order_id"] == order.id
    # Контракт события не расширён — только order_id
    assert set(received[0].keys()) == {"order_id", "signal"}
