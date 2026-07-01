"""Тесты модуля отзывов: модерация и видимость (#72)."""

from __future__ import annotations

import pytest

from .models import Review, ReviewStatus, SubjectType


@pytest.fixture
def approved_review(db):
    return Review.objects.create(
        subject_type=SubjectType.PRODUCT,
        subject_id=1,
        rating=5,
        body="Отличный товар",
        author_name="Иван",
        status=ReviewStatus.APPROVED,
    )


@pytest.fixture
def pending_review(db):
    return Review.objects.create(
        subject_type=SubjectType.PRODUCT,
        subject_id=1,
        rating=4,
        body="Хороший товар",
        author_name="Пётр",
        status=ReviewStatus.PENDING,
    )


@pytest.fixture
def rejected_review(db):
    return Review.objects.create(
        subject_type=SubjectType.PRODUCT,
        subject_id=1,
        rating=1,
        body="Плохой",
        author_name="Сидор",
        status=ReviewStatus.REJECTED,
    )


# ── Модерация ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_new_review_is_pending(db):
    r = Review.objects.create(subject_id=1, rating=3, author_name="Аноним")
    assert r.status == ReviewStatus.PENDING


@pytest.mark.django_db
def test_approved_review_is_approved(approved_review):
    assert approved_review.is_approved is True


@pytest.mark.django_db
def test_pending_review_not_approved(pending_review):
    assert pending_review.is_approved is False


@pytest.mark.django_db
def test_rejected_review_not_approved(rejected_review):
    assert rejected_review.is_approved is False


# ── Видимость на витрине ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_approved_qs_excludes_pending(approved_review, pending_review, rejected_review):
    approved = Review.objects.approved()
    assert approved_review in approved
    assert pending_review not in approved
    assert rejected_review not in approved


@pytest.mark.django_db
def test_for_product_qs(approved_review, db):
    other_product = Review.objects.create(
        subject_type=SubjectType.PRODUCT,
        subject_id=99,
        rating=3,
        status=ReviewStatus.APPROVED,
    )
    product_reviews = Review.objects.for_product(1)
    assert approved_review in product_reviews
    assert other_product not in product_reviews


@pytest.mark.django_db
def test_approved_for_product_combined(approved_review, pending_review):
    qs = Review.objects.for_product(1).approved()
    assert approved_review in qs
    assert pending_review not in qs


# ── Расширяемость (subject_type) ──────────────────────────────────────────────


@pytest.mark.django_db
def test_order_review_same_model(db):
    r = Review.objects.create(
        subject_type=SubjectType.ORDER,
        subject_id=42,
        rating=5,
        author_name="Клиент",
    )
    assert r.subject_type == SubjectType.ORDER
    assert r.subject_id == 42


# ── __str__ ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_str_with_author_name(approved_review):
    assert "Иван" in str(approved_review)
    assert "5★" in str(approved_review)
