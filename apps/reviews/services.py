"""Сервисный слой отзывов (#573): правила создания и публичные выборки.

Правила создания (порядок проверок фиксирован тестами):
1. фичефлаг ``reviews`` включён;
2. заказ существует И принадлежит пользователю (чужой/несуществующий не
   различаются — анти-перебор номеров);
3. заказ строго завершён (``fulfillment_status == completed``; shipped — ещё нет);
4. отзыв по заказу ещё не оставлен (unique на уровне БД закрывает гонку).
"""

from __future__ import annotations

from django.db import IntegrityError, transaction

from apps.core.features import is_enabled
from apps.orders.reviews_bridge import get_order_for_review, order_ids_with_product

from .models import Review, ReviewStatus

# Человеческие тексты ошибок — по коду их же отдаёт API.
ERROR_MESSAGES = {
    "reviews_disabled": "Отзывы временно недоступны.",
    "order_not_found": "Заказ не найден.",
    "order_not_completed": "Отзыв можно оставить после получения заказа.",
    "already_reviewed": "Вы уже оставили отзыв по этому заказу.",
}


class ReviewError(Exception):
    """Ошибка бизнес-правила с машиночитаемым кодом."""

    def __init__(self, code: str):
        self.code = code
        self.message = ERROR_MESSAGES[code]
        super().__init__(self.message)


def public_author_name(user) -> str:
    """Публичный снапшот имени: «Имя И.» либо «Покупатель» (ПДн наружу не отдаём)."""
    full = (getattr(user, "full_name", "") or "").strip()
    if not full:
        return "Покупатель"
    parts = full.split()
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0]}."


def create_review(
    *,
    user,
    order_number: str,
    product_rating: int,
    delivery_rating: int,
    shop_rating: int,
    text: str = "",
) -> Review:
    if not is_enabled("reviews"):
        raise ReviewError("reviews_disabled")

    order = get_order_for_review(user, order_number)
    if order is None:
        raise ReviewError("order_not_found")
    if not order.is_completed:
        raise ReviewError("order_not_completed")
    if Review.objects.filter(order_id=order.order_id).exists():
        raise ReviewError("already_reviewed")

    review = Review(
        order_id=order.order_id,
        author=user,
        author_name=public_author_name(user),
        product_rating=product_rating,
        delivery_rating=delivery_rating,
        shop_rating=shop_rating,
        text=(text or "").strip(),
        status=ReviewStatus.PENDING,
    )
    review.full_clean()
    try:
        with transaction.atomic():
            review.save()
    except IntegrityError:
        # Гонка double-submit: unique(order) в БД — повтор трактуем как «уже есть».
        raise ReviewError("already_reviewed") from None
    return review


def public_reviews_for_product(product_id: int):
    """Approved-отзывы заказов, содержащих товар (отзыв — на заказ целиком).

    Один автор может встретиться несколько раз (товар в нескольких его
    завершённых заказах) — by design.
    """
    return (
        Review.objects.approved()
        .filter(order_id__in=order_ids_with_product(product_id))
        .order_by("-created_at")
    )


def product_rating_summary(queryset) -> dict:
    """Средняя товарная оценка + количество ПО ВСЕМУ queryset (не по странице)."""
    from django.db.models import Avg, Count

    agg = queryset.aggregate(avg=Avg("product_rating"), count=Count("id"))
    avg = agg["avg"]
    return {
        "product_rating_avg": round(float(avg), 1) if avg is not None else None,
        "count": agg["count"],
    }


__all__ = [
    "ReviewError",
    "create_review",
    "product_rating_summary",
    "public_author_name",
    "public_reviews_for_product",
]
