"""Сервисный слой доставки.

Контракт: ``calculate(*, zone_slug, cart_total) -> list[dict]``
Возвращает доступные способы доставки с рассчитанной стоимостью.

Зоны и тарифы читаются из БД (DeliveryZone) — бизнес-логика не зависит
от конкретных значений, администратор меняет их через админку.
"""

from __future__ import annotations

from decimal import Decimal

from .models import DeliveryType, DeliveryZone, PickupPoint


def calculate(
    *,
    zone_slug: str | None = None,
    cart_total: Decimal = Decimal("0"),
) -> list[dict]:
    """Рассчитать доступные способы доставки.

    Параметры:
        zone_slug: слаг конкретной зоны (если передан — возвращается только она).
        cart_total: сумма корзины для расчёта бесплатной доставки.

    Возвращает:
        Список словарей::

            {
                "zone": str,          # slug зоны
                "name": str,          # название зоны
                "type": str,          # "courier" | "pickup"
                "cost": Decimal,      # итоговая стоимость
                "free_delivery": bool # бесплатна ли доставка
            }
    """
    qs = DeliveryZone.objects.filter(is_active=True)
    if zone_slug is not None:
        qs = qs.filter(slug=zone_slug)
    zones = qs.order_by("sort_order", "name")

    result: list[dict] = []
    for zone in zones:
        cost = _calculate_zone_cost(zone, cart_total)
        entry = {
            "zone": zone.slug,
            "name": zone.name,
            "type": zone.delivery_type,
            "cost": cost,
            "free_delivery": cost == Decimal("0"),
            "pickup_points": [],
        }
        if zone.delivery_type == DeliveryType.PICKUP:
            entry["pickup_points"] = list(
                PickupPoint.objects.filter(is_active=True).values(
                    "name", "address", "working_hours"
                )
            )
        result.append(entry)
    return result


def _calculate_zone_cost(zone: DeliveryZone, cart_total: Decimal) -> Decimal:
    """Рассчитать стоимость доставки для зоны.

    Самовывоз всегда 0 ₽. Для курьерской доставки: если сумма корзины
    достигает порога бесплатной доставки — стоимость 0 ₽.
    """
    if zone.delivery_type == DeliveryType.PICKUP:
        return Decimal("0")

    if zone.free_from is not None and cart_total >= zone.free_from:
        return Decimal("0")

    return zone.price
