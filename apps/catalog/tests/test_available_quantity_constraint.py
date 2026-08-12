"""DB-инвариант DRF-1003: available_quantity не уходит в минус.

Минус означает, что одну единицу товара продали дважды: причиной может быть
зависший резерв (DRF-1002), гонка при оформлении, кривая выгрузка или ручная
правка. Constraint ловит их все — тихая порча данных становится ошибкой.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.catalog.models import Product


def _product(**kw):
    defaults = dict(
        name="Товар",
        code_1c="neg-1",
        slug="neg-1",
        unit="шт",
        price=Decimal("100.00"),
        currency="RUB",
    )
    defaults.update(kw)
    return Product.objects.create(**defaults)


@pytest.mark.django_db
def test_negative_available_rejected_on_create():
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _product(available_quantity=Decimal("-1"))


@pytest.mark.django_db
def test_negative_available_rejected_on_update():
    p = _product(available_quantity=Decimal("1"))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Product.objects.filter(pk=p.pk).update(available_quantity=Decimal("-3"))

    p.refresh_from_db()
    assert p.available_quantity == Decimal("1")


@pytest.mark.django_db
def test_zero_and_positive_allowed():
    _product(code_1c="neg-2", slug="neg-2", available_quantity=Decimal("0"))
    _product(code_1c="neg-3", slug="neg-3", available_quantity=Decimal("42.500"))


@pytest.mark.django_db
def test_full_clean_reports_negative_before_db():
    """Валидатор поля — чтобы форма админки показала ошибку, а не 500 от БД."""
    p = _product(available_quantity=Decimal("0"))
    p.available_quantity = Decimal("-1")

    with pytest.raises(ValidationError) as exc:
        p.full_clean()

    assert "available_quantity" in exc.value.error_dict
