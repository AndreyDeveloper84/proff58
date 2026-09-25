"""Тесты модели/сервисов подписки «Сообщить о поступлении» (#517)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.integration_max.models import MaxAccount

from .availability_subscriptions import (
    MaxConnectionRequired,
    ProductAvailabilitySubscription,
    ProductInStock,
    ProductNotEligible,
    SubscriptionStatus,
    cancel_active_for_user,
    claim_active_subscriptions,
    get_eligible_product,
    get_status,
    mark_notified,
    subscribe,
    unsubscribe,
)
from .models import Product, ProductStatus

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+79001234567", password="pass")


def _link_max(user, chat_id=555):
    return MaxAccount.objects.create(
        user=user,
        max_user_id=42,
        chat_id=chat_id,
        phone=user.phone,
        phone_verified_at=timezone.now(),
    )


def _out_of_stock_product(**kwargs):
    defaults = dict(
        name="Дрель",
        slug="drel-517",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("0"),
    )
    defaults.update(kwargs)
    return Product.objects.create(**defaults)


# ═══════════════════════════════════════════════════════════════════════
# Модель — uniqueness
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_unique_active_subscription_per_user_product_channel(user):
    product = _out_of_stock_product()
    ProductAvailabilitySubscription.objects.create(user=user, product=product)
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductAvailabilitySubscription.objects.create(user=user, product=product)


@pytest.mark.django_db
def test_terminal_status_does_not_conflict_with_new_active(user):
    """История (notified/cancelled) не мешает завести новую активную подписку —
    новый цикл «в наличии → нет → снова в наличии» (#517)."""
    product = _out_of_stock_product()
    ProductAvailabilitySubscription.objects.create(
        user=user, product=product, status=SubscriptionStatus.NOTIFIED
    )
    # Не должно упасть — второй активной строки на терминальный фон нет.
    ProductAvailabilitySubscription.objects.create(user=user, product=product)


# ═══════════════════════════════════════════════════════════════════════
# get_eligible_product
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_get_eligible_product_found():
    product = _out_of_stock_product()
    assert get_eligible_product(product.slug).pk == product.pk


@pytest.mark.django_db
def test_get_eligible_product_unpublished_raises():
    _out_of_stock_product(slug="hidden-517", status=ProductStatus.IMPORTED)
    with pytest.raises(ProductNotEligible):
        get_eligible_product("hidden-517")


@pytest.mark.django_db
def test_get_eligible_product_inactive_raises():
    _out_of_stock_product(slug="inactive-517", is_active=False)
    with pytest.raises(ProductNotEligible):
        get_eligible_product("inactive-517")


@pytest.mark.django_db
def test_get_eligible_product_missing_raises():
    with pytest.raises(ProductNotEligible):
        get_eligible_product("does-not-exist")


# ═══════════════════════════════════════════════════════════════════════
# subscribe — rules + idempotency
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_subscribe_success(user):
    _link_max(user)
    product = _out_of_stock_product()
    sub = subscribe(user, product)
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.user_id == user.pk


@pytest.mark.django_db
def test_subscribe_idempotent_returns_existing(user):
    """AC #517: повторный subscribe возвращает existing active без дубля."""
    _link_max(user)
    product = _out_of_stock_product()
    first = subscribe(user, product)
    second = subscribe(user, product)
    assert first.pk == second.pk
    assert ProductAvailabilitySubscription.objects.filter(user=user, product=product).count() == 1


@pytest.mark.django_db
def test_subscribe_in_stock_product_rejected(user):
    _link_max(user)
    product = _out_of_stock_product(slug="in-stock-517", available_quantity=Decimal("5"))
    with pytest.raises(ProductInStock):
        subscribe(user, product)


@pytest.mark.django_db
def test_subscribe_without_max_rejected(user):
    """Не доверяем frontend — canonical MaxAccount, не легаси max_chat_id (#514)."""
    User.objects.filter(pk=user.pk).update(max_chat_id=999)  # легаси не считается
    product = _out_of_stock_product()
    with pytest.raises(MaxConnectionRequired):
        subscribe(user, product)


# ═══════════════════════════════════════════════════════════════════════
# get_status / unsubscribe
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_get_status_none_when_no_subscription(user):
    product = _out_of_stock_product()
    assert get_status(user, product) is None


@pytest.mark.django_db
def test_unsubscribe_idempotent(user):
    """AC #517: DELETE повторяем и безопасен."""
    _link_max(user)
    product = _out_of_stock_product()
    subscribe(user, product)

    assert unsubscribe(user, product) is True
    assert unsubscribe(user, product) is False  # уже отменена — не ошибка

    sub = ProductAvailabilitySubscription.objects.get(user=user, product=product)
    assert sub.status == SubscriptionStatus.CANCELLED
    assert sub.cancelled_at is not None


@pytest.mark.django_db
def test_unsubscribe_without_subscription_is_noop(user):
    product = _out_of_stock_product()
    assert unsubscribe(user, product) is False


# ═══════════════════════════════════════════════════════════════════════
# cancel_active_for_user (unlink MAX, #517 AC: сохраняет историю)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_cancel_active_for_user_keeps_terminal_history(user):
    p1 = _out_of_stock_product(slug="cancel-1")
    p2 = _out_of_stock_product(slug="cancel-2")
    ProductAvailabilitySubscription.objects.create(user=user, product=p1)
    notified = ProductAvailabilitySubscription.objects.create(
        user=user, product=p2, status=SubscriptionStatus.NOTIFIED
    )

    count = cancel_active_for_user(user)

    assert count == 1
    p1_sub = ProductAvailabilitySubscription.objects.get(user=user, product=p1)
    assert p1_sub.status == SubscriptionStatus.CANCELLED
    notified.refresh_from_db()
    assert notified.status == SubscriptionStatus.NOTIFIED  # история не тронута


@pytest.mark.django_db
def test_unlink_max_cancels_active_subscriptions(user):
    """Регрессия #517: unlink_max() отменяет активные MAX-подписки пользователя."""
    from apps.integration_max.services import unlink_max

    _link_max(user)
    product = _out_of_stock_product()
    subscribe(user, product)

    unlink_max(user)

    sub = ProductAvailabilitySubscription.objects.get(user=user, product=product)
    assert sub.status == SubscriptionStatus.CANCELLED


# ═══════════════════════════════════════════════════════════════════════
# claim_active_subscriptions / mark_notified (#518)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_claim_active_subscriptions_moves_to_queued(user):
    _link_max(user)
    product = _out_of_stock_product()
    subscribe(user, product)

    claimed = claim_active_subscriptions(product.pk)

    assert len(claimed) == 1
    assert claimed[0].user_id == user.pk  # select_related — доступ без доп. запроса
    sub = ProductAvailabilitySubscription.objects.get(user=user, product=product)
    assert sub.status == SubscriptionStatus.QUEUED
    assert sub.queued_at is not None


@pytest.mark.django_db
def test_claim_active_subscriptions_second_call_finds_nothing(user):
    """AC #518: конкурентный/повторный claim не берёт уже claimed строки."""
    _link_max(user)
    product = _out_of_stock_product()
    subscribe(user, product)

    first = claim_active_subscriptions(product.pk)
    second = claim_active_subscriptions(product.pk)

    assert len(first) == 1
    assert len(second) == 0


@pytest.mark.django_db
def test_mark_notified_transitions_status(user):
    _link_max(user)
    product = _out_of_stock_product()
    sub = subscribe(user, product)
    claim_active_subscriptions(product.pk)

    mark_notified(sub.pk)

    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.NOTIFIED
    assert sub.notified_at is not None
