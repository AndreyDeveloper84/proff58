"""Промо в оформлении заказа (#571): снимки, доставка, НДС, счёт, 1С-payload."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.delivery.models import DeliveryZone
from apps.orders.services import add_to_cart, place_order
from apps.promotions.models import DiscountType, PromoScope, Promotion

D = Decimal


@pytest.fixture(autouse=True)
def _promos_on(settings):
    settings.FEATURES = {**getattr(settings, "FEATURES", {}), "promotions": True}


@pytest.fixture
def penza_zone(db):
    return DeliveryZone.objects.create(
        slug="penza", name="Пенза (курьер)", price=D("500"), free_from=D("7000")
    )


def _guest():
    return {"customer_name": "Гость", "customer_phone": "+79001234567"}


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


def _auto_percent(product, value="10"):
    promo = Promotion.objects.create(
        name=f"Авто −{value}%",
        discount_type=DiscountType.PERCENT,
        discount_value=D(value),
        scope=PromoScope.PRODUCT,
    )
    promo.products.set([product])
    return promo


def _fd_code(code="FREEDEL"):
    return Promotion.objects.create(
        name="Бесплатная доставка",
        discount_type=DiscountType.FREE_DELIVERY,
        discount_value=D("0"),
        scope=PromoScope.CART,
        promo_code=code,
    )


# ═══════════ снимки и суммы ═══════════


@pytest.mark.django_db
def test_auto_promo_snapshotted_into_order(cart, product):
    _auto_percent(product)  # −10% от 1000
    add_to_cart(cart, product, 2)
    order = place_order(cart, customer_data=_guest())

    assert order.items_discount_total == D("200.00")
    assert order.total == D("1800.00")  # 2000 − 200, доставки нет
    item = order.items.get()
    assert item.line_total == D("2000.00")  # снимок строки — ДО промо
    assert item.promo_discount == D("200.00")
    assert order.promo_snapshot["applied"][0]["name"] == "Авто −10%"
    # Инвариант нового мира: total == Σ line_total − items_discount + доставка − скидка дост.
    assert order.total == item.line_total - order.items_discount_total


@pytest.mark.django_db
def test_promo_code_from_cart_snapshotted(cart, product):
    promo = Promotion.objects.create(
        name="Код −5%",
        discount_type=DiscountType.PERCENT,
        discount_value=D("5"),
        scope=PromoScope.CART,
        promo_code="MINUS5",
    )
    add_to_cart(cart, product, 1)
    cart.promo_code = "MINUS5"
    cart.save(update_fields=["promo_code"])
    order = place_order(cart, customer_data=_guest())

    assert order.promo_code == "MINUS5"
    assert order.items_discount_total == D("50.00")
    assert order.total == D("950.00")
    assert order.promo_snapshot["applied"][0]["id"] == promo.pk


@pytest.mark.django_db
def test_invalid_code_at_checkout_blocks(cart, product):
    promo = Promotion.objects.create(
        name="Истёкший",
        discount_type=DiscountType.PERCENT,
        discount_value=D("5"),
        scope=PromoScope.CART,
        promo_code="DEAD",
    )
    add_to_cart(cart, product, 1)
    cart.promo_code = "DEAD"
    cart.save(update_fields=["promo_code"])
    Promotion.objects.filter(pk=promo.pk).update(
        ends_at=timezone.now() - timezone.timedelta(minutes=1)
    )
    with pytest.raises(ValidationError, match="истёк"):
        place_order(cart, customer_data=_guest())


@pytest.mark.django_db
def test_flag_off_keeps_legacy_totals(cart, product, settings):
    """Выключенный флаг: суммы и снимки как раньше, промо-поля нулевые."""
    settings.FEATURES = {**settings.FEATURES, "promotions": False}
    _auto_percent(product)
    add_to_cart(cart, product, 2)
    order = place_order(cart, customer_data=_guest())
    assert order.total == D("2000.00")
    assert order.items_discount_total == D("0.00")
    assert order.promo_snapshot == {}
    assert order.items.get().promo_discount is None


# ═══════════ доставка ═══════════


@pytest.mark.django_db
def test_free_delivery_code_discounts_delivery(cart, product, penza_zone):
    _fd_code()
    add_to_cart(cart, product, 1)  # 1000 < 7000 → доставка 500
    cart.promo_code = "FREEDEL"
    cart.save(update_fields=["promo_code"])
    order = place_order(cart, customer_data=_guest(), delivery={"delivery_zone": "penza"})
    # Quote не меняется — скидка отдельной строкой.
    assert order.delivery_cost == D("500.00")
    assert order.delivery_discount == D("500.00")
    assert order.total == D("1000.00")  # товары + 500 − 500
    fd = [a for a in order.promo_snapshot["applied"] if a["discount_type"] == "free_delivery"]
    assert fd and fd[0]["amount"] == "500.00"


@pytest.mark.django_db
def test_discount_can_flip_free_from_threshold(cart, product, penza_zone):
    """Скидка опускает товары ниже free_from → доставка становится платной."""
    product.price = D("7000.00")
    product.save(update_fields=["price"])
    _auto_percent(product)  # −10% → товары 6300 < 7000
    add_to_cart(cart, product, 1)
    order = place_order(cart, customer_data=_guest(), delivery={"delivery_zone": "penza"})
    assert order.items_discount_total == D("700.00")
    assert order.delivery_cost == D("500.00")  # порог считался от суммы ПОСЛЕ скидки
    assert order.total == D("6800.00")  # 6300 + 500


# ═══════════ B2B (решение: промо действует и для юрлиц) ═══════════


@pytest.mark.django_db
def test_b2b_gets_item_discounts_and_vat_after_discount(cart, product, settings):
    settings.VAT_RATE_PERCENT = 22
    _auto_percent(product)  # −10%
    add_to_cart(cart, product, 1)
    order = place_order(cart, customer_data=_b2b())

    from apps.pricing.vat import vat_breakdown

    assert order.total == D("900.00")
    net, vat = vat_breakdown(D("900.00"), 22)
    assert order.vat_amount == vat and order.amount_without_vat == net

    # Счёт юрлица сходится арифметически: Σ строк − скидка == итог.
    from apps.orders.invoice import prepare_invoice

    inv = prepare_invoice(order)
    assert sum(i.total for i in inv.items) - inv.items_discount_total == inv.total
    assert inv.items_discount_total == D("100.00")


@pytest.mark.django_db
def test_b2b_free_delivery_code_not_beneficial_but_not_blocking(cart, product, penza_zone):
    """У юрлиц доставки нет: free_delivery-код не даёт выгоды, заказ не блокируется."""
    _fd_code()
    add_to_cart(cart, product, 1)
    cart.promo_code = "FREEDEL"
    cart.save(update_fields=["promo_code"])
    order = place_order(cart, customer_data=_b2b())
    assert order.delivery_discount == D("0.00")
    assert order.promo_snapshot["code_error"]["code"] == "not_beneficial"


# ═══════════ 1С-payload ═══════════


@pytest.mark.django_db
def test_1c_export_carries_promo_fields(cart, product):
    _auto_percent(product)
    add_to_cart(cart, product, 2)
    order = place_order(cart, customer_data=_guest())

    from apps.sync_1c.use_cases import _serialize_order_for_export

    payload = _serialize_order_for_export(order)
    assert payload["items"][0]["promo_discount"] == "200.00"
    assert payload["items"][0]["total"] == "2000.00"  # строка ДО скидки
    assert payload["totals"]["items_discount_total"] == "200.00"
    assert payload["totals"]["total"] == "1800.00"
    # Товарная часть для 1С: Σ items.total − items_discount_total == totals.total.
    assert D(payload["items"][0]["total"]) - D("200.00") == D(payload["totals"]["total"])
