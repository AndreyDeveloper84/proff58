"""Тесты гейта B2B-верификации (#340).

Неверифицированный B2B видит розничные цены, верифицированный — опт.
Верификация через admin-action эмитит событие b2b_verified.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings

from apps.accounts.models import CustomerType, Profile
from apps.catalog.models import Product, ProductStatus
from apps.pricing.models import PriceRecord
from apps.pricing.services import price_for

User = get_user_model()


@pytest.fixture
def product(db):
    return Product.objects.create(
        name="Молоток",
        code_1c="1c-b2b-gate",
        slug="molotok-b2b",
        price=Decimal("500.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
    )


@pytest.fixture
def wholesale_record(product):
    return PriceRecord.objects.create(
        code_1c=product.code_1c,
        price_type="wholesale",
        currency="RUB",
        value=Decimal("350.00"),
        is_current=True,
    )


@pytest.fixture
def unverified_b2b(db):
    user = User.objects.create_user(phone="+79991111101", customer_type="b2b")
    Profile.objects.create(user=user, is_b2b_verified=False)
    return user


@pytest.fixture
def verified_b2b(db):
    user = User.objects.create_user(phone="+79991111102", customer_type="b2b")
    Profile.objects.create(user=user, is_b2b_verified=True)
    return user


@override_settings(FEATURES={"b2b": True})
def test_unverified_b2b_sees_retail(product, unverified_b2b, wholesale_record):
    result = price_for(product, unverified_b2b)
    assert result.final == Decimal("500.00"), "Неверифицированный B2B должен видеть розничную цену"


@override_settings(FEATURES={"b2b": True})
def test_verified_b2b_sees_wholesale(product, verified_b2b, wholesale_record):
    result = price_for(product, verified_b2b)
    assert result.final == Decimal("350.00"), "Верифицированный B2B должен видеть оптовую цену"


def test_user_is_b2b_verified_property(db):
    user = User.objects.create_user(phone="+79991111103", customer_type="b2b")
    assert not user.is_b2b_verified, "Без профиля — не верифицирован"
    Profile.objects.create(user=user, is_b2b_verified=False)
    user.refresh_from_db()
    assert not user.is_b2b_verified, "Профиль без верификации — не верифицирован"
    user.profile.is_b2b_verified = True
    user.profile.save()
    user = User.objects.get(pk=user.pk)
    assert user.is_b2b_verified, "После верификации свойство должно вернуть True"


def test_b2c_user_is_not_b2b_verified(db):
    user = User.objects.create_user(phone="+79991111104", customer_type="b2c")
    Profile.objects.create(user=user, is_b2b_verified=True)
    assert not user.is_b2b_verified, "B2C не может быть is_b2b_verified"


def test_verify_b2b_admin_action_emits_event(db):
    from unittest.mock import MagicMock, patch

    from django.contrib.admin.sites import AdminSite

    from apps.accounts.admin import UserAdmin

    user = User.objects.create_user(phone="+79991111105", customer_type="b2b")
    Profile.objects.create(user=user, is_b2b_verified=False)

    ma = UserAdmin(User, AdminSite())
    request = MagicMock()

    with patch("apps.core.events.b2b_verified.send") as mock_send:
        ma.verify_b2b_action(request, User.objects.filter(pk=user.pk))
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs["user_id"] == user.pk

    user.profile.refresh_from_db()
    assert user.profile.is_b2b_verified


def test_verify_b2b_admin_action_idempotent(db):
    """Повторная верификация не вызывает событие второй раз."""
    from unittest.mock import MagicMock, patch

    from django.contrib.admin.sites import AdminSite

    from apps.accounts.admin import UserAdmin

    user = User.objects.create_user(phone="+79991111106", customer_type="b2b")
    Profile.objects.create(user=user, is_b2b_verified=True)

    ma = UserAdmin(User, AdminSite())
    request = MagicMock()

    with patch("apps.core.events.b2b_verified.send") as mock_send:
        ma.verify_b2b_action(request, User.objects.filter(pk=user.pk))
        mock_send.assert_not_called()
