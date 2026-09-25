"""Занятость слотов доставки (#569) — единственная точка подсчёта.

Занятость считается по «живым» заказам слота (fulfillment != cancelled), а не
счётчиком на слоте: отмена заказа автоматически освобождает место, дрейф
счётчика невозможен. Неоплаченный заказ место держит (неоплаченный ≠ мёртвый:
есть оплата при получении); истечение 30-минутного резерва товара (#568) слот
не освобождает — освобождает только отмена заказа менеджером/1С.

Модуль живёт в orders: другим приложениям (delivery, админке) нельзя читать
таблицу заказов напрямую (CLAUDE.md §4) — только через эти функции.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.db.models import Count

from .models import FulfillmentStatus, Order


def occupied_counts(slot_ids: Iterable[int]) -> dict[int, int]:
    """Число живых заказов по каждому слоту одним агрегирующим запросом."""
    ids = [pk for pk in slot_ids if pk]
    if not ids:
        return {}
    rows = (
        Order.objects.filter(delivery_slot_id__in=ids)
        .exclude(fulfillment_status=FulfillmentStatus.CANCELLED)
        .values("delivery_slot_id")
        .annotate(n=Count("id"))
    )
    return {row["delivery_slot_id"]: row["n"] for row in rows}


def occupied_count(slot_id: int) -> int:
    return occupied_counts([slot_id]).get(slot_id, 0)
