"""Юнит-тесты compute_promotions (#571): правила совмещения, капы, ошибки кодов."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.promotions.models import DiscountType, PromoScope, Promotion
from apps.promotions.services import PromoLineInput, compute_promotions

D = Decimal


def _line(key, product, qty=1):
    unit = product.price
    return PromoLineInput(key=key, product_id=product.pk, quantity=qty, line_total=unit * qty)


def _promo(**kw):
    defaults = {
        "name": "Акция",
        "discount_type": DiscountType.PERCENT,
        "discount_value": D("10"),
        "scope": PromoScope.PRODUCT,
    }
    defaults.update(kw)
    products = defaults.pop("for_products", [])
    categories = defaults.pop("for_categories", [])
    promo = Promotion.objects.create(**defaults)
    if products:
        promo.products.set(products)
    if categories:
        promo.categories.set(categories)
    return promo


# ═══════════ строчные скидки ═══════════


@pytest.mark.django_db
def test_percent_on_product_quantized(drill):
    _promo(discount_value=D("7.5"), for_products=[drill])
    bd = compute_promotions([_line(1, drill)])  # 1000 × 7.5% = 75.00
    assert bd.line_discounts == {1: D("75.00")}
    assert bd.items_discount_total == D("75.00")
    assert len(bd.applied) == 1 and bd.applied[0].amount == D("75.00")


@pytest.mark.django_db
def test_percent_rounds_half_up(drill):
    drill.price = D("999.99")
    drill.save(update_fields=["price"])
    _promo(discount_value=D("7.5"), for_products=[drill])
    # 999.99 × 0.075 = 74.99925 → 75.00 (HALF_UP)
    bd = compute_promotions([_line(1, drill)])
    assert bd.line_discounts[1] == D("75.00")


@pytest.mark.django_db
def test_promotion_does_not_leak_to_other_products(drill, saw):
    _promo(for_products=[drill])
    bd = compute_promotions([_line(1, saw)])
    assert bd.line_discounts == {}
    assert bd.items_discount_total == D("0.00")
    assert bd.applied == []


@pytest.mark.django_db
def test_fixed_per_unit_capped_by_line_total(drill):
    _promo(
        discount_type=DiscountType.FIXED,
        discount_value=D("700"),
        for_products=[drill],
    )
    # 700 × 2 = 1400, но кап line_total (2×1000=2000) не достигнут.
    bd = compute_promotions([_line(1, drill, qty=2)])
    assert bd.line_discounts[1] == D("1400.00")
    # Кап: скидка 1500/шт × 1 > 1000 → срезается до line_total.
    Promotion.objects.all().delete()
    _promo(
        discount_type=DiscountType.FIXED,
        discount_value=D("1500"),
        for_products=[drill],
    )
    bd = compute_promotions([_line(1, drill)])
    assert bd.line_discounts[1] == D("1000.00")  # не глубже нуля


@pytest.mark.django_db
def test_category_promo_covers_subtree(tree, drill):
    """Акция на корневую категорию действует на товар в подкатегории."""
    _promo(
        scope=PromoScope.CATEGORY,
        discount_value=D("10"),
        for_categories=[tree["root"]],
    )
    bd = compute_promotions([_line(1, drill)])  # drill в child
    assert bd.line_discounts[1] == D("100.00")


@pytest.mark.django_db
def test_category_promo_child_does_not_cover_parent(tree, saw):
    """Обратное неверно: акция на подкатегорию не трогает товар в родителе."""
    _promo(
        scope=PromoScope.CATEGORY,
        discount_value=D("10"),
        for_categories=[tree["child"]],
    )
    bd = compute_promotions([_line(1, saw)])  # saw в root
    assert bd.line_discounts == {}


@pytest.mark.django_db
def test_best_of_deterministic(drill):
    """На строку — одна лучшая акция; тай-брейк: amount → priority → id."""
    _promo(name="10%", discount_value=D("10"), for_products=[drill])
    best = _promo(name="15%", discount_value=D("15"), for_products=[drill])
    bd = compute_promotions([_line(1, drill)])
    assert bd.line_discounts[1] == D("150.00")
    assert [a.promotion_id for a in bd.applied] == [best.pk]

    # Равная выгода → выигрывает больший priority.
    Promotion.objects.all().delete()
    _promo(name="A", discount_value=D("10"), for_products=[drill], priority=0)
    prio = _promo(name="B", discount_value=D("10"), for_products=[drill], priority=5)
    bd = compute_promotions([_line(1, drill)])
    assert [a.promotion_id for a in bd.applied] == [prio.pk]


# ═══════════ промокоды ═══════════


@pytest.mark.django_db
def test_code_applies_only_when_provided(drill):
    _promo(promo_code="SALE", discount_value=D("20"), for_products=[drill])
    assert compute_promotions([_line(1, drill)]).items_discount_total == D("0.00")
    bd = compute_promotions([_line(1, drill)], promo_code="sale")  # регистр не важен
    assert bd.items_discount_total == D("200.00")
    assert bd.code_error is None


@pytest.mark.django_db
def test_code_errors_actionable(drill):
    now = timezone.now()
    _promo(
        promo_code="OLD",
        for_products=[drill],
        ends_at=now - timezone.timedelta(days=1),
    )
    _promo(
        promo_code="SOON",
        for_products=[drill],
        starts_at=now + timezone.timedelta(days=1),
    )
    _promo(promo_code="OFF", for_products=[drill], is_active=False)

    lines = [_line(1, drill)]
    assert compute_promotions(lines, promo_code="NOPE").code_error.code == "not_found"
    assert compute_promotions(lines, promo_code="OLD").code_error.code == "expired"
    assert compute_promotions(lines, promo_code="SOON").code_error.code == "not_available"
    assert compute_promotions(lines, promo_code="OFF").code_error.code == "not_available"
    # Тексты — человеческие, из единого словаря.
    err = compute_promotions(lines, promo_code="OLD").code_error
    assert "истёк" in err.message


@pytest.mark.django_db
def test_code_not_applicable_to_cart_items(drill, saw):
    _promo(promo_code="DRILL", discount_value=D("20"), for_products=[drill])
    bd = compute_promotions([_line(1, saw)], promo_code="DRILL")
    assert bd.code_error.code == "not_applicable"
    assert bd.items_discount_total == D("0.00")


@pytest.mark.django_db
def test_cart_code_applies_over_line_discounts(drill):
    """Код scope=cart считается от остатка после строчных скидок."""
    _promo(discount_value=D("10"), for_products=[drill])  # авто −100
    _promo(
        promo_code="MINUS5",
        scope=PromoScope.CART,
        discount_value=D("5"),
        for_products=[],
    )
    bd = compute_promotions([_line(1, drill)], promo_code="MINUS5")
    # 1000 − 100 = 900; 5% от 900 = 45.
    assert bd.items_discount_total == D("145.00")
    assert {a.amount for a in bd.applied} == {D("100.00"), D("45.00")}


@pytest.mark.django_db
def test_cart_fixed_capped_by_remainder(drill):
    _promo(discount_value=D("90"), for_products=[drill])  # авто: 90% от 1000 = −900
    _promo(
        promo_code="BIG",
        scope=PromoScope.CART,
        discount_type=DiscountType.FIXED,
        discount_value=D("500"),
    )
    bd = compute_promotions([_line(1, drill)], promo_code="BIG")
    # Остаток после строчной: 1000 − 900 = 100 → фикс 500 капится до 100.
    assert bd.items_discount_total == D("1000.00")
    # Итог никогда не уходит ниже нуля.


@pytest.mark.django_db
def test_product_code_loses_to_better_auto_not_beneficial(drill):
    """Код проигрывает автоакции на всех строках → not_beneficial, без блокировки."""
    _promo(discount_value=D("20"), for_products=[drill])  # авто −200
    _promo(promo_code="WEAK", discount_value=D("5"), for_products=[drill])  # код −50
    bd = compute_promotions([_line(1, drill)], promo_code="WEAK")
    assert bd.items_discount_total == D("200.00")  # применена лучшая (авто)
    assert bd.code_error.code == "not_beneficial"


# ═══════════ free_delivery ═══════════


def _fd_code():
    return _promo(
        name="Бесплатная доставка",
        promo_code="FREEDEL",
        scope=PromoScope.CART,
        discount_type=DiscountType.FREE_DELIVERY,
        discount_value=D("0"),
    )


@pytest.mark.django_db
def test_free_delivery_discounts_calculated_cost(drill):
    _fd_code()
    bd = compute_promotions(
        [_line(1, drill)],
        promo_code="FREEDEL",
        delivery_cost=D("500.00"),
        delivery_status="calculated",
    )
    assert bd.delivery_discount == D("500.00")
    assert bd.items_discount_total == D("0.00")
    assert bd.code_error is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "cost,status",
    [
        (D("0.00"), "calculated"),  # уже бесплатно (free_from/самовывоз)
        (None, "manual_required"),  # стоимость неизвестна — нельзя дарить неизвестное
        (D("0.00"), "not_required"),
    ],
)
def test_free_delivery_no_benefit_cases(drill, cost, status):
    _fd_code()
    bd = compute_promotions(
        [_line(1, drill)], promo_code="FREEDEL", delivery_cost=cost, delivery_status=status
    )
    assert bd.delivery_discount == D("0.00")
    assert bd.code_error.code == "not_beneficial"


@pytest.mark.django_db
def test_free_delivery_not_for_b2b(drill):
    _fd_code()
    bd = compute_promotions(
        [_line(1, drill)],
        promo_code="FREEDEL",
        customer_type="b2b",
        delivery_cost=D("0.00"),
        delivery_status="not_required",
    )
    assert bd.delivery_discount == D("0.00")
    assert bd.code_error.code == "not_beneficial"


@pytest.mark.django_db
def test_free_delivery_in_cart_context_waits(drill):
    """В корзине доставка неизвестна: код применён (amount 0), ошибки нет."""
    _fd_code()
    bd = compute_promotions([_line(1, drill)], promo_code="FREEDEL")
    assert bd.code_error is None
    assert bd.delivery_discount == D("0.00")
    assert [a.discount_type for a in bd.applied] == [DiscountType.FREE_DELIVERY]


# ═══════════ края ═══════════


@pytest.mark.django_db
def test_empty_lines(db):
    bd = compute_promotions([])
    assert bd.items_discount_total == D("0.00") and bd.applied == []


@pytest.mark.django_db
def test_total_never_negative(drill):
    """percent 100 на строку + фикс-код поверх → итог ровно 0, не минус."""
    _promo(discount_value=D("100"), for_products=[drill])
    _promo(
        promo_code="EXTRA",
        scope=PromoScope.CART,
        discount_type=DiscountType.FIXED,
        discount_value=D("999"),
    )
    line = _line(1, drill)
    bd = compute_promotions([line], promo_code="EXTRA")
    assert bd.items_discount_total == line.line_total  # ровно 100%, кап сработал
