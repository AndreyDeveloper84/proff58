"""Мост orders → reviews (#573): отзывы не читают таблицу заказов напрямую.

Границы модулей (CLAUDE.md §4): бизнес-правила «чей заказ», «завершён ли»,
«какие товары внутри» инкапсулированы здесь — по прецеденту ``apps.orders.slots``
(#569, тот же приём для delivery). ``apps.reviews`` знает только эти функции.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.accounts.models import CustomerType

from .models import FulfillmentStatus, Order, OrderItem


@dataclass(frozen=True)
class ReviewableOrder:
    """Срез заказа для права на отзыв."""

    order_id: int
    order_number: str
    is_completed: bool
    is_b2b: bool
    product_ids: list[int]


def get_order_for_review(user, order_number: str) -> ReviewableOrder | None:
    """Заказ пользователя по номеру. None — не существует ИЛИ чужой.

    Причины не различаются сознательно (анти-перебор номеров заказов).
    Гостевые заказы (user=None) отзывов в Wave 1 не имеют — future scope.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    order = (
        Order.objects.filter(order_number=order_number, user=user)
        .only("id", "order_number", "fulfillment_status", "customer_type")
        .first()
    )
    if order is None:
        return None
    product_ids = list(
        OrderItem.objects.filter(order=order, product_id__isnull=False).values_list(
            "product_id", flat=True
        )
    )
    return ReviewableOrder(
        order_id=order.pk,
        order_number=order.order_number,
        is_completed=order.fulfillment_status == FulfillmentStatus.COMPLETED,
        is_b2b=order.customer_type == CustomerType.B2B,
        product_ids=product_ids,
    )


def order_ids_with_product(product_id: int):
    """Ленивый values-подзапрос «id заказов, содержащих товар» — для выборки
    approved-отзывов на PDP (``Review.objects.filter(order_id__in=...)``)."""
    return OrderItem.objects.filter(product_id=product_id).values("order_id")


def order_products_summary(order_id: int) -> list[str]:
    """Названия позиций заказа — readonly-контекст в админке отзыва."""
    return list(OrderItem.objects.filter(order_id=order_id).values_list("name", flat=True))
