"""Тесты контракта персистентности цены (#152): apps.pricing.repositories."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.catalog.models import Product
from apps.pricing import repositories as repo
from apps.pricing.models import PriceRecord


@pytest.mark.django_db
def test_current_price_value_returns_current_only():
    PriceRecord.objects.create(
        code_1c="c1", price_type="retail", currency="RUB", value=Decimal("100"), is_current=False
    )
    PriceRecord.objects.create(
        code_1c="c1", price_type="retail", currency="RUB", value=Decimal("150"), is_current=True
    )
    assert repo.current_price_value("c1", "retail", "RUB") == Decimal("150")
    # Нет актуальной цены этого ключа → None.
    assert repo.current_price_value("c1", "wholesale", "RUB") is None
    assert repo.current_price_value("nope", "retail", "RUB") is None


@pytest.mark.django_db
def test_current_price_map_keys_and_id_value():
    r = PriceRecord.objects.create(
        code_1c="c1", price_type="retail", currency="RUB", value=Decimal("100"), is_current=True
    )
    PriceRecord.objects.create(
        code_1c="c1", price_type="retail", currency="RUB", value=Decimal("90"), is_current=False
    )
    m = repo.current_price_map(["c1", "", None])
    assert m == {("c1", "retail", "RUB"): (r.id, Decimal("100"))}
    assert repo.current_price_map([]) == {}


@pytest.mark.django_db
def test_write_current_price_flips_old_and_keeps_fk():
    product = Product.objects.create(name="Т", code_1c="c1", slug="c1")
    old = PriceRecord.objects.create(
        code_1c="c1", price_type="retail", currency="RUB", value=Decimal("100"), is_current=True
    )

    repo.write_current_price(
        code_1c="c1", product=product, value=Decimal("150"), price_type="retail", currency="RUB"
    )

    old.refresh_from_db()
    assert old.is_current is False
    current = PriceRecord.objects.get(code_1c="c1", is_current=True)
    assert current.value == Decimal("150")
    assert current.product_id == product.pk  # FK сохранён
    assert PriceRecord.objects.filter(code_1c="c1", is_current=True).count() == 1


@pytest.mark.django_db
def test_apply_prices_bulk_last_wins_dedup():
    product = Product.objects.create(name="Т", code_1c="c1", slug="c1")
    writes = [
        repo.PriceWrite(
            code_1c="c1", product=product, price_type="retail", currency="RUB", value=Decimal("100")
        ),
        repo.PriceWrite(
            code_1c="c1", product=product, price_type="retail", currency="RUB", value=Decimal("150")
        ),
    ]
    repo.apply_prices_bulk(writes, current_map={})
    # Дубль ключа схлопнут last-wins → ровно одна актуальная запись со значением 150.
    rows = PriceRecord.objects.filter(code_1c="c1", is_current=True)
    assert rows.count() == 1
    assert rows.first().value == Decimal("150")


@pytest.mark.django_db
def test_apply_prices_bulk_flips_old_by_current_map():
    product = Product.objects.create(name="Т", code_1c="c1", slug="c1")
    old = PriceRecord.objects.create(
        code_1c="c1", price_type="retail", currency="RUB", value=Decimal("100"), is_current=True
    )
    current_map = {("c1", "retail", "RUB"): (old.id, Decimal("100"))}
    writes = [
        repo.PriceWrite(
            code_1c="c1", product=product, price_type="retail", currency="RUB", value=Decimal("150")
        )
    ]
    repo.apply_prices_bulk(writes, current_map)

    old.refresh_from_db()
    assert old.is_current is False
    assert PriceRecord.objects.filter(code_1c="c1", is_current=True).count() == 1
    assert PriceRecord.objects.get(code_1c="c1", is_current=True).value == Decimal("150")


@pytest.mark.django_db
def test_apply_prices_bulk_skips_empty_code():
    product = Product.objects.create(name="Т", slug="nocode")
    writes = [
        repo.PriceWrite(
            code_1c="", product=product, price_type="retail", currency="RUB", value=Decimal("100")
        )
    ]
    repo.apply_prices_bulk(writes, current_map={})
    assert PriceRecord.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_partial_unique_forbids_two_current():
    """Инвариант: две актуальные цены на один ключ невозможны (partial-unique)."""
    PriceRecord.objects.create(
        code_1c="c1", price_type="retail", currency="RUB", value=Decimal("100"), is_current=True
    )
    with pytest.raises(IntegrityError):
        PriceRecord.objects.create(
            code_1c="c1", price_type="retail", currency="RUB", value=Decimal("150"), is_current=True
        )
