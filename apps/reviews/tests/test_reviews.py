"""Тесты отзывов (#573): мост, сервис, API, админка, обезличивание."""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import override_settings
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductStatus
from apps.orders.models import FulfillmentStatus, Order, OrderItem
from apps.orders.reviews_bridge import get_order_for_review
from apps.reviews import services
from apps.reviews.models import Review, ReviewStatus

User = get_user_model()


@pytest.fixture(autouse=True)
def _reviews_on(settings):
    settings.FEATURES = {**getattr(settings, "FEATURES", {}), "reviews": True}


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        phone="+79001112255", password="pass12345", full_name="Иван Петров"
    )


@pytest.fixture
def product(db):
    cat = Category.add_root(name="Инструмент", slug="instr-rev")
    return Product.objects.create(
        category=cat,
        name="Дрель",
        slug="drel-rev",
        unit="шт",
        price=Decimal("1000.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
    )


def _order(user, product, status=FulfillmentStatus.COMPLETED, number="П-REV-1"):
    order = Order.objects.create(
        order_number=number, user=user, fulfillment_status=status, customer_name="Иван"
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        name=product.name,
        price_final=product.price,
        quantity=1,
        line_total=product.price,
    )
    return order


def _create(user, number="П-REV-1", **kw):
    defaults = {"product_rating": 5, "delivery_rating": 4, "shop_rating": 5, "text": "Отлично"}
    defaults.update(kw)
    return services.create_review(user=user, order_number=number, **defaults)


# ═══════════ мост ═══════════


@pytest.mark.django_db
def test_bridge_own_completed(user, product):
    _order(user, product)
    ro = get_order_for_review(user, "П-REV-1")
    assert ro.is_completed and ro.product_ids == [product.pk]


@pytest.mark.django_db
def test_bridge_foreign_and_missing_are_none(user, product):
    stranger = User.objects.create_user(phone="+79001112266", password="x12345678")
    _order(stranger, product)
    assert get_order_for_review(user, "П-REV-1") is None  # чужой
    assert get_order_for_review(user, "НЕТ-ТАКОГО") is None
    assert get_order_for_review(None, "П-REV-1") is None  # гость — future scope


# ═══════════ сервис ═══════════


@pytest.mark.django_db
def test_create_review_ok(user, product):
    _order(user, product)
    review = _create(user)
    assert review.status == ReviewStatus.PENDING
    assert review.author_name == "Иван П."  # снапшот, не полное имя


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fstatus", [FulfillmentStatus.SHIPPED, FulfillmentStatus.CANCELLED, FulfillmentStatus.NEW]
)
def test_not_completed_rejected(user, product, fstatus):
    _order(user, product, status=fstatus)
    with pytest.raises(services.ReviewError) as e:
        _create(user)
    assert e.value.code == "order_not_completed"


@pytest.mark.django_db
def test_flag_off(user, product, settings):
    settings.FEATURES = {**settings.FEATURES, "reviews": False}
    _order(user, product)
    with pytest.raises(services.ReviewError) as e:
        _create(user)
    assert e.value.code == "reviews_disabled"


@pytest.mark.django_db
def test_duplicate_and_db_unique(user, product):
    _order(user, product)
    _create(user)
    with pytest.raises(services.ReviewError) as e:
        _create(user)
    assert e.value.code == "already_reviewed"
    # unique(order) на уровне БД (гонка double-submit).
    with pytest.raises(IntegrityError), transaction.atomic():
        Review.objects.create(
            order_id=Order.objects.get().pk, product_rating=1, delivery_rating=1, shop_rating=1
        )


@pytest.mark.django_db
def test_empty_text_ok_and_bad_rating_rejected(user, product):
    _order(user, product)
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):  # full_clean: оценка вне 1..5
        _create(user, product_rating=6)
    review = _create(user, text="")
    assert review.text == ""


@pytest.mark.django_db
def test_author_name_fallback(db):
    anon = User.objects.create_user(phone="+79001112277", password="x12345678")
    assert services.public_author_name(anon) == "Покупатель"


# ═══════════ публичная выборка ═══════════


@pytest.mark.django_db
def test_public_only_approved_and_only_orders_with_product(user, product):
    other_product = Product.objects.create(
        category=product.category,
        name="Пила",
        slug="pila-rev",
        unit="шт",
        price=Decimal("500.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
    )
    _order(user, product, number="П-REV-1")
    r1 = _create(user, number="П-REV-1")
    stranger = User.objects.create_user(phone="+79001112288", password="x12345678")
    _order(stranger, other_product, number="П-REV-2")
    _create(stranger, number="П-REV-2")  # другой товар — не должен попасть

    qs = services.public_reviews_for_product(product.pk)
    assert list(qs) == []  # pending не виден
    Review.objects.filter(pk=r1.pk).update(status=ReviewStatus.APPROVED)
    qs = services.public_reviews_for_product(product.pk)
    assert [r.pk for r in qs] == [r1.pk]
    summary = services.product_rating_summary(qs)
    assert summary == {"product_rating_avg": 5.0, "count": 1}


# ═══════════ API ═══════════


@pytest.mark.django_db
def test_api_create_and_mine(api, user, product):
    _order(user, product)
    api.force_authenticate(user=user)
    resp = api.post(
        "/api/account/reviews/",
        {"order_number": "П-REV-1", "product_rating": 5, "delivery_rating": 4, "shop_rating": 5},
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["status"] == "pending"

    mine = api.get("/api/account/reviews/?order=П-REV-1").json()
    assert mine["count"] == 1 and mine["results"][0]["order_number"] == "П-REV-1"

    # повтор → 409
    resp = api.post(
        "/api/account/reviews/",
        {"order_number": "П-REV-1", "product_rating": 5, "delivery_rating": 4, "shop_rating": 5},
        format="json",
    )
    assert resp.status_code == 409 and resp.json()["code"] == "already_reviewed"


@pytest.mark.django_db
def test_api_guards(api, user, product, settings):
    _order(user, product, status=FulfillmentStatus.SHIPPED)
    assert api.get("/api/account/reviews/").status_code in (401, 403)  # аноним

    api.force_authenticate(user=user)
    body = {"order_number": "П-REV-1", "product_rating": 5, "delivery_rating": 5, "shop_rating": 5}
    assert api.post("/api/account/reviews/", body, format="json").status_code == 400  # shipped
    body["order_number"] = "ЧУЖОЙ"
    assert api.post("/api/account/reviews/", body, format="json").status_code == 404

    settings.FEATURES = {**settings.FEATURES, "reviews": False}
    assert api.get("/api/account/reviews/").status_code == 404
    assert api.post("/api/account/reviews/", body, format="json").status_code == 404


@pytest.mark.django_db
def test_api_public_payload_has_no_pii(api, user, product):
    _order(user, product)
    review = _create(user)
    Review.objects.filter(pk=review.pk).update(status=ReviewStatus.APPROVED)

    data = api.get("/api/reviews/product/drel-rev/").json()
    assert data["summary"]["count"] == 1
    item = data["results"][0]
    # Явный контракт ключей: никакого телефона/полного имени/автора.
    assert set(item.keys()) == {"author_name", "product_rating", "text", "created_at"}
    assert item["author_name"] == "Иван П."
    assert api.get("/api/reviews/product/net-takogo/").status_code == 404


@pytest.mark.django_db
def test_api_create_throttled(api, user, product):
    _order(user, product)
    api.force_authenticate(user=user)
    body = {"order_number": "П-REV-1", "product_rating": 5, "delivery_rating": 5, "shop_rating": 5}
    with override_settings(
        REST_FRAMEWORK={
            **__import__("django.conf", fromlist=["settings"]).settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {"reviews": "1/min"},
        }
    ):
        assert api.post("/api/account/reviews/", body, format="json").status_code == 201
        assert api.post("/api/account/reviews/", body, format="json").status_code == 429


# ═══════════ админка ═══════════


@pytest.mark.django_db
def test_admin_actions_and_reason(user, product):
    from apps.reviews.admin import ReviewAdmin, ReviewAdminForm

    _order(user, product)
    review = _create(user)
    admin_obj = ReviewAdmin(Review, admin_site=mock.Mock())
    admin_obj.message_user = mock.Mock()

    admin_obj.approve_selected(mock.Mock(), Review.objects.filter(pk=review.pk))
    review.refresh_from_db()
    assert review.status == ReviewStatus.APPROVED and review.moderated_at is not None

    admin_obj.reject_selected(mock.Mock(), Review.objects.filter(pk=review.pk))
    review.refresh_from_db()
    assert review.status == ReviewStatus.REJECTED and review.rejection_reason

    form = ReviewAdminForm(data={"status": "rejected", "rejection_reason": " "}, instance=review)
    assert not form.is_valid() and "rejection_reason" in form.errors


# ═══════════ обезличивание (#344/M-02) ═══════════


@pytest.mark.django_db
def test_delete_account_anonymizes_reviews(api, user, product):
    _order(user, product)
    review = _create(user)
    api.force_authenticate(user=user)
    assert api.post("/api/account/delete/").status_code == 200
    review.refresh_from_db()
    assert review.author_name == "Покупатель"
    # Аккаунт обезличивается, не удаляется (#344): FK остаётся, но сам user
    # уже без ПДн; SET_NULL сработает при физическом удалении строки.
