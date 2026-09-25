"""Тесты API «Сообщить о поступлении» (#517)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.integration_max.models import MaxAccount

from ..availability_subscriptions import ProductAvailabilitySubscription, SubscriptionStatus
from ..models import Product, ProductStatus

User = get_user_model()

_URL = "/api/catalog/products/{slug}/availability-subscription/"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+79001234567", password="pass")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(phone="+79009999999", password="pass")


def _link_max(user, chat_id=555):
    return MaxAccount.objects.create(
        user=user,
        max_user_id=42,
        chat_id=chat_id,
        phone=user.phone,
        phone_verified_at=timezone.now(),
    )


@pytest.fixture
def product(db):
    return Product.objects.create(
        name="Дрель",
        slug="drel-api-517",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("0"),
    )


# ═══════════════════════════════════════════════════════════════════════
# Auth
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_get_requires_auth(client, product):
    resp = client.get(_URL.format(slug=product.slug))
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_post_requires_auth(client, product):
    resp = client.post(_URL.format(slug=product.slug))
    assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════
# GET status
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_get_status_none_when_not_subscribed(client, user, product):
    client.force_authenticate(user=user)
    resp = client.get(_URL.format(slug=product.slug))
    assert resp.status_code == 200
    assert resp.data["status"] is None


@pytest.mark.django_db
def test_get_status_after_subscribe(client, user, product):
    _link_max(user)
    client.force_authenticate(user=user)
    client.post(_URL.format(slug=product.slug))
    resp = client.get(_URL.format(slug=product.slug))
    assert resp.data["status"] == SubscriptionStatus.ACTIVE


@pytest.mark.django_db
def test_get_unpublished_product_404(client, user):
    Product.objects.create(
        name="Скрытый", slug="hidden-api-517", status=ProductStatus.IMPORTED, is_active=True
    )
    client.force_authenticate(user=user)
    resp = client.get(_URL.format(slug="hidden-api-517"))
    assert resp.status_code == 404


@pytest.mark.django_db
def test_get_missing_product_404(client, user):
    client.force_authenticate(user=user)
    resp = client.get(_URL.format(slug="does-not-exist"))
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# POST subscribe
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_post_subscribe_success(client, user, product):
    _link_max(user)
    client.force_authenticate(user=user)
    resp = client.post(_URL.format(slug=product.slug))
    assert resp.status_code == 201
    assert resp.data["status"] == SubscriptionStatus.ACTIVE
    assert ProductAvailabilitySubscription.objects.filter(user=user, product=product).count() == 1


@pytest.mark.django_db
def test_post_subscribe_idempotent_no_duplicate(client, user, product):
    """AC #517: повторный POST возвращает existing active без дубля."""
    _link_max(user)
    client.force_authenticate(user=user)
    r1 = client.post(_URL.format(slug=product.slug))
    r2 = client.post(_URL.format(slug=product.slug))
    assert r1.status_code == r2.status_code == 201
    assert ProductAvailabilitySubscription.objects.filter(user=user, product=product).count() == 1


@pytest.mark.django_db
def test_post_subscribe_in_stock_rejected(client, user, product):
    _link_max(user)
    product.available_quantity = Decimal("5")
    product.save(update_fields=["available_quantity"])
    client.force_authenticate(user=user)
    resp = client.post(_URL.format(slug=product.slug))
    assert resp.status_code == 400
    assert resp.data["code"] == "already_in_stock"


@pytest.mark.django_db
def test_post_subscribe_without_max_actionable_error(client, user, product):
    """AC #517: actionable error max_connection_required (не generic 400)."""
    client.force_authenticate(user=user)
    resp = client.post(_URL.format(slug=product.slug))
    assert resp.status_code == 400
    assert resp.data["code"] == "max_connection_required"


@pytest.mark.django_db
def test_post_subscribe_stock_not_trusted_from_frontend(client, user, product):
    """AC #517: endpoint не доверяет stock state с фронта — игнорирует любые
    поля тела запроса и читает available_quantity из БД."""
    _link_max(user)
    client.force_authenticate(user=user)
    resp = client.post(_URL.format(slug=product.slug), {"available_quantity": 0, "force": True})
    assert resp.status_code == 201  # успех определяется реальным БД-состоянием, не телом


@pytest.mark.django_db
def test_post_subscribe_unpublished_product_404(client, user):
    Product.objects.create(
        name="Скрытый", slug="hidden-post-517", status=ProductStatus.IMPORTED, is_active=True
    )
    _link_max(user)
    client.force_authenticate(user=user)
    resp = client.post(_URL.format(slug="hidden-post-517"))
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# DELETE unsubscribe
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_delete_unsubscribe_success(client, user, product):
    _link_max(user)
    client.force_authenticate(user=user)
    client.post(_URL.format(slug=product.slug))

    resp = client.delete(_URL.format(slug=product.slug))
    assert resp.status_code == 204
    sub = ProductAvailabilitySubscription.objects.get(user=user, product=product)
    assert sub.status == SubscriptionStatus.CANCELLED


@pytest.mark.django_db
def test_delete_idempotent_when_nothing_to_cancel(client, user, product):
    """AC #517: DELETE повторяем и безопасен."""
    client.force_authenticate(user=user)
    resp = client.delete(_URL.format(slug=product.slug))
    assert resp.status_code == 204


# ═══════════════════════════════════════════════════════════════════════
# Ownership: чужой пользователь не видит/не трогает подписку другого
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_ownership_status_is_per_user(client, user, other_user, product):
    _link_max(user)
    client.force_authenticate(user=user)
    client.post(_URL.format(slug=product.slug))

    client.force_authenticate(user=other_user)
    resp = client.get(_URL.format(slug=product.slug))
    assert resp.data["status"] is None  # у other_user своей подписки нет


@pytest.mark.django_db
def test_ownership_delete_does_not_affect_other_user(client, user, other_user, product):
    _link_max(user)
    client.force_authenticate(user=user)
    client.post(_URL.format(slug=product.slug))

    client.force_authenticate(user=other_user)
    client.delete(_URL.format(slug=product.slug))

    sub = ProductAvailabilitySubscription.objects.get(user=user, product=product)
    assert sub.status == SubscriptionStatus.ACTIVE  # чужой DELETE не отменил


# ═══════════════════════════════════════════════════════════════════════
# Rate limit — throttle_classes подключены (сама ставка — settings, #9-стиль)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_view_has_explicit_throttle_class():
    from apps.catalog.api.views import ProductAvailabilitySubscriptionView
    from apps.core.throttling import SubscriptionRateThrottle

    assert SubscriptionRateThrottle in ProductAvailabilitySubscriptionView.throttle_classes
