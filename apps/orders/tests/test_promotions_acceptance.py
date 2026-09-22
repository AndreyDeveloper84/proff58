"""Приёмка акций и промокодов перед включением модуля (DRF-2294).

Контрольная таблица расчётов: одна и та же корзина даёт одну сумму на витрине
(get_cart_view), в заказе (place_order) и в чеке кассы (build_positions) — до
копейки. Плюс неизменность истории: правка акции не трогает уже оформленные
заказы и их счёт. Отдельные правила расчёта покрыты в apps/promotions/tests и
test_promotions_checkout.py; здесь — именно связка витрина = заказ = чек.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.delivery.models import DeliveryZone
from apps.orders.invoice import prepare_invoice
from apps.orders.services import add_to_cart, get_cart_view, place_order
from apps.payments.atolpay.receipt import build_positions
from apps.promotions.models import DiscountType, PromoScope, Promotion

D = Decimal


@pytest.fixture(autouse=True)
def _promos_on(settings):
    settings.FEATURES = {**getattr(settings, "FEATURES", {}), "promotions": True}


@pytest.fixture
def зона(db):
    return DeliveryZone.objects.create(
        slug="penza", name="Пенза (курьер)", price=D("500"), free_from=D("7000")
    )


ГОСТЬ = {"customer_name": "Гость", "customer_phone": "+79001234567"}


def _promo(name, dtype, value, scope, code="", products=()):
    promo = Promotion.objects.create(
        name=name,
        discount_type=dtype,
        discount_value=D(value),
        scope=scope,
        promo_code=code,
    )
    if products:
        promo.products.set(products)
    return promo


def _копейки(positions) -> int:
    return sum(p["price"] * p["quantity"] // 1000 for p in positions)


def _сверка(view, order, ожидаемый_итог, ожидаемая_скидка):
    """Витрина, заказ и чек показывают одну сумму.

    ``grand_total`` корзины — товары после скидок без доставки (доставка появляется
    при оформлении), поэтому формула: корзина + доставка − скидка на доставку = заказ = чек.
    """
    assert order.items_discount_total == D(ожидаемая_скидка)
    assert order.total == D(ожидаемый_итог)
    assert view.items_discount_total == order.items_discount_total
    assert view.grand_total + (order.delivery_cost or 0) - (order.delivery_discount or 0) == (
        order.total
    )
    positions = build_positions(order)
    assert _копейки(positions) == int(D(ожидаемый_итог) * 100)
    return positions


# ═══════════ контрольная таблица ═══════════


@pytest.mark.django_db
def test_A_автоакция_процент_на_товар(cart, product):
    _promo("Авто −10%", DiscountType.PERCENT, "10", PromoScope.PRODUCT, products=[product])
    add_to_cart(cart, product, 2)  # 2 × 1000

    view = get_cart_view(cart)
    assert (view.total, view.items_discount_total, view.grand_total) == (
        D("2000.00"),
        D("200.00"),
        D("1800.00"),
    )
    order = place_order(cart, customer_data=ГОСТЬ)
    _сверка(view, order, "1800.00", "200.00")


@pytest.mark.django_db
def test_B_код_на_корзину_поверх_строчной_скидки(cart, product):
    _promo("Авто −10%", DiscountType.PERCENT, "10", PromoScope.PRODUCT, products=[product])
    _promo("Код −5%", DiscountType.PERCENT, "5", PromoScope.CART, code="MINUS5")
    add_to_cart(cart, product, 2)
    cart.promo_code = "MINUS5"
    cart.save(update_fields=["promo_code"])

    view = get_cart_view(cart)
    # 2000 − 200 (строка) = 1800; −5 % от 1800 = 90 → 1710
    assert view.items_discount_total == D("290.00")
    assert view.grand_total == D("1710.00")
    assert view.promo_code_error is None
    order = place_order(cart, customer_data=ГОСТЬ)
    _сверка(view, order, "1710.00", "290.00")
    assert order.promo_code == "MINUS5"
    assert {a["name"] for a in order.promo_snapshot["applied"]} == {
        "Авто −10%",
        "Код −5%",
    }


@pytest.mark.django_db
def test_C_фиксированная_скидка_за_штуку(cart, product):
    _promo("−100 ₽/шт", DiscountType.FIXED, "100", PromoScope.PRODUCT, products=[product])
    add_to_cart(cart, product, 2)

    view = get_cart_view(cart)
    assert view.grand_total == D("1800.00")
    order = place_order(cart, customer_data=ГОСТЬ)
    _сверка(view, order, "1800.00", "200.00")


@pytest.mark.django_db
def test_D_код_бесплатной_доставки(cart, product, зона):
    _promo(
        "Бесплатная доставка",
        DiscountType.FREE_DELIVERY,
        "0",
        PromoScope.CART,
        code="FREEDEL",
    )
    add_to_cart(cart, product, 1)  # 1000 < 7000 → доставка 500
    cart.promo_code = "FREEDEL"
    cart.save(update_fields=["promo_code"])

    view = get_cart_view(cart)
    assert view.grand_total == D("1000.00")  # доставки в корзине ещё нет
    assert view.promo_code_error is None  # код ждёт оформления, не «бесполезен»
    order = place_order(cart, customer_data=ГОСТЬ, delivery={"delivery_zone": "penza"})
    assert order.delivery_cost == D("500.00")
    assert order.delivery_discount == D("500.00")
    positions = _сверка(view, order, "1000.00", "0.00")
    assert all(p["name"] != "Доставка" for p in positions)  # нулевую доставку в чек не кладём


@pytest.mark.django_db
@pytest.mark.parametrize(
    "код,ошибка_корзины,текст_отказа",
    [
        ("SHUR", "not_applicable", "не подходит к товарам"),
        ("SOON", "not_available", "не действует"),
    ],
)
def test_E_негодный_код_виден_в_корзине_и_блокирует_оформление(
    cart, product, product2, код, ошибка_корзины, текст_отказа
):
    _promo(
        "Код на шуруповёрт",
        DiscountType.PERCENT,
        "20",
        PromoScope.PRODUCT,
        code="SHUR",
        products=[product2],
    )
    ещё_не_начался = _promo("Скоро", DiscountType.PERCENT, "20", PromoScope.CART, code="SOON")
    Promotion.objects.filter(pk=ещё_не_начался.pk).update(
        starts_at=timezone.now() + timezone.timedelta(days=1)
    )
    add_to_cart(cart, product, 1)  # в корзине только дрель
    cart.promo_code = код
    cart.save(update_fields=["promo_code"])

    view = get_cart_view(cart)
    assert view.promo_code_error["code"] == ошибка_корзины
    assert view.grand_total == D("1000.00")  # скидки нет, итог честный
    # Оформление с негодным кодом — отказ с той же причиной, не тихий заказ без скидки.
    with pytest.raises(ValidationError, match=текст_отказа):
        place_order(cart, customer_data=ГОСТЬ)
    from apps.orders.models import Order

    assert not Order.objects.exists()


@pytest.mark.django_db
def test_F_при_выключенном_модуле_скидки_нет_нигде(cart, product, settings):
    settings.FEATURES = {**settings.FEATURES, "promotions": False}
    _promo("Авто −10%", DiscountType.PERCENT, "10", PromoScope.PRODUCT, products=[product])
    add_to_cart(cart, product, 2)
    cart.promo_code = "ЛЮБОЙ"
    cart.save(update_fields=["promo_code"])

    view = get_cart_view(cart)
    assert view.promotions_enabled is False
    assert view.grand_total == D("2000.00") and view.promo_code == ""
    order = place_order(cart, customer_data=ГОСТЬ)
    _сверка(view, order, "2000.00", "0.00")
    assert order.promo_code == "" and order.promo_snapshot == {}


@pytest.mark.django_db
def test_G_платная_доставка_без_кода_доставки(cart, product, зона):
    _promo("Авто −10%", DiscountType.PERCENT, "10", PromoScope.PRODUCT, products=[product])
    add_to_cart(cart, product, 1)  # 900 после скидки < 7000 → доставка 500

    view = get_cart_view(cart)
    assert view.grand_total == D("900.00")
    order = place_order(cart, customer_data=ГОСТЬ, delivery={"delivery_zone": "penza"})
    assert (order.delivery_cost, order.delivery_discount) == (D("500.00"), D("0.00"))
    positions = _сверка(view, order, "1400.00", "100.00")
    доставка = [p for p in positions if p["name"] == "Доставка"]
    assert доставка and доставка[0]["price"] == 50_000  # цена в копейках, 500 ₽


@pytest.mark.django_db
def test_H_b2b_счёт_сходится_с_заказом(cart, product, settings):
    settings.VAT_RATE_PERCENT = 22
    _promo("Авто −10%", DiscountType.PERCENT, "10", PromoScope.PRODUCT, products=[product])
    add_to_cart(cart, product, 2)
    b2b = {
        **ГОСТЬ,
        "customer_name": "Иван Петров",
        "customer_email": "buh@romashka.ru",
        "customer_type": "b2b",
        "company_name": "ООО «Ромашка»",
        "inn": "7700000000",
        "kpp": "770001001",
        "legal_address": "г. Пенза, ул. Ленина, 1",
    }
    view = get_cart_view(cart)
    order = place_order(cart, customer_data=b2b)
    _сверка(view, order, "1800.00", "200.00")
    счёт = prepare_invoice(order)
    assert счёт.total == order.total
    assert sum(i.total for i in счёт.items) - счёт.items_discount_total == счёт.total


# ═══════════ история не пересчитывается ═══════════


@pytest.mark.django_db
def test_правка_акции_не_меняет_оформленный_заказ(cart, product):
    promo = _promo("Авто −10%", DiscountType.PERCENT, "10", PromoScope.PRODUCT, products=[product])
    add_to_cart(cart, product, 2)
    order = place_order(cart, customer_data=ГОСТЬ)
    снимок = dict(order.promo_snapshot)
    счёт_до = prepare_invoice(order)

    # акцию усилили, потом выключили
    Promotion.objects.filter(pk=promo.pk).update(discount_value=D("50"))
    order.refresh_from_db()
    assert order.total == D("1800.00") and order.items_discount_total == D("200.00")
    Promotion.objects.filter(pk=promo.pk).update(
        is_active=False, ends_at=timezone.now() - timezone.timedelta(days=1)
    )
    order.refresh_from_db()
    assert order.total == D("1800.00")
    assert order.promo_snapshot == снимок
    assert order.items.get().promo_discount == D("200.00")
    счёт_после = prepare_invoice(order)
    assert (счёт_после.total, счёт_после.items_discount_total) == (
        счёт_до.total,
        счёт_до.items_discount_total,
    )
    assert _копейки(build_positions(order)) == 180000

    # новая корзина считает уже по текущему состоянию акции (она выключена)
    from apps.orders.models import Cart

    новая = Cart.objects.create(session_key="sess-after-edit")
    add_to_cart(новая, product, 2)
    assert get_cart_view(новая).grand_total == D("2000.00")


@pytest.mark.django_db
def test_автоакция_изменённая_между_корзиной_и_оформлением(cart, product):
    """Известное поведение: цена серверная на момент оформления, предупреждения нет.

    Покупатель видел в корзине 1800, акцию выключили, заказ оформился на 2000 без
    ошибки. Для промокодов иначе — истёкший код блокирует оформление.
    """
    promo = _promo("Авто −10%", DiscountType.PERCENT, "10", PromoScope.PRODUCT, products=[product])
    add_to_cart(cart, product, 2)
    assert get_cart_view(cart).grand_total == D("1800.00")

    Promotion.objects.filter(pk=promo.pk).update(is_active=False)
    order = place_order(cart, customer_data=ГОСТЬ)
    assert order.total == D("2000.00")
    assert order.items_discount_total == D("0.00")
