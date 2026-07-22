"""Валидации Promotion (#571)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.promotions.models import DiscountType, PromoScope, Promotion


def _promo(**kw):
    defaults = {
        "name": "A",
        "discount_type": DiscountType.PERCENT,
        "discount_value": Decimal("10"),
        "scope": PromoScope.CART,
    }
    defaults.update(kw)
    return Promotion(**defaults)


@pytest.mark.django_db
def test_percent_range_validated():
    with pytest.raises(ValidationError):
        _promo(discount_value=Decimal("0")).clean()
    with pytest.raises(ValidationError):
        _promo(discount_value=Decimal("101")).clean()
    _promo(discount_value=Decimal("100")).clean()  # верхняя граница валидна


@pytest.mark.django_db
def test_fixed_positive_validated():
    with pytest.raises(ValidationError):
        _promo(discount_type=DiscountType.FIXED, discount_value=Decimal("0")).clean()


@pytest.mark.django_db
def test_free_delivery_requires_code_and_cart_scope():
    with pytest.raises(ValidationError) as e:
        _promo(
            discount_type=DiscountType.FREE_DELIVERY,
            discount_value=Decimal("0"),
            scope=PromoScope.PRODUCT,
        ).clean()
    assert "promo_code" in e.value.message_dict and "scope" in e.value.message_dict
    _promo(
        discount_type=DiscountType.FREE_DELIVERY,
        discount_value=Decimal("0"),
        promo_code="FREE",
    ).clean()


@pytest.mark.django_db
def test_dates_order_validated():
    from django.utils import timezone

    now = timezone.now()
    with pytest.raises(ValidationError):
        _promo(starts_at=now, ends_at=now).clean()


@pytest.mark.django_db
def test_promo_code_unique_case_insensitive():
    _promo(promo_code="SALE").save()
    with pytest.raises(IntegrityError):
        _promo(promo_code="sale").save()
