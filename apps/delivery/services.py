"""Сервисный слой доставки.

Два контракта:
- ``calculate(*, zone_slug, cart_total)`` — витринная подсказка (список зон+цен);
- ``quote_for_order(*, zone_slug, goods_total, items)`` — СЕРВЕРНЫЙ расчёт для
  checkout (#429/M-05): единственный источник правды по стоимости доставки,
  считается по серверной корзине внутри транзакции заказа.

Контракт ADR #444 (Wave 1):
- самовывоз — 0 ₽;
- своя доставка по Пензе — <7000 ₽ → 500 ₽, ≥7000 ₽ → бесплатно (порог по
  стоимости товаров после скидок, без доставки);
- СДЭК (область, ``is_external``) — всегда по API перевозчика, порог не
  применяется; авторасчёт только при заполненных весе/габаритах у всех товаров,
  иначе ``manual_required`` (стоимость определит менеджер).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .models import DeliveryType, DeliveryZone, PickupPoint

# Статусы серверного расчёта доставки (#429/M-05).
CALCULATED = "calculated"
MANUAL_REQUIRED = "manual_required"
NOT_REQUIRED = "not_required"


@dataclass(frozen=True)
class DeliveryQuote:
    """Результат серверного расчёта доставки для заказа.

    ``cost is None`` ⇔ ``status == manual_required``: стоимость неизвестна,
    заказ создаётся, но итог предварительный и финальный счёт не выпускается.
    """

    zone_slug: str
    method: str
    status: str
    cost: Decimal | None
    free_delivery: bool = False
    snapshot: dict = field(default_factory=dict)
    reason: str = ""


def _items_have_dimensions(items) -> bool:
    """У всех строк заполнены вес и габариты (для авторасчёта СДЭК).

    Товар может не иметь этих полей в каталоге (задел под весогабариты) —
    тогда авторасчёт невозможен → ручной расчёт менеджером.
    """
    for it in items:
        product = getattr(it, "product", None)
        if product is None:
            return False
        for f in ("weight_kg", "length_cm", "width_cm", "height_cm"):
            if not getattr(product, f, None):
                return False
    return True


def quote_for_order(*, zone_slug: str, goods_total: Decimal, items) -> DeliveryQuote:
    """Серверный расчёт доставки для заказа. Единый источник правды.

    ``zone_slug`` — выбранная зона; ``goods_total`` — сумма товаров (после скидок,
    без доставки); ``items`` — строки заказа/корзины (для проверки весогабаритов
    при СДЭК). Пустой ``zone_slug`` → NOT_REQUIRED (доставка не выбрана).
    """
    if not zone_slug:
        return DeliveryQuote(zone_slug="", method="", status=NOT_REQUIRED, cost=Decimal("0.00"))

    zone = DeliveryZone.objects.filter(slug=zone_slug, is_active=True).first()
    if zone is None:
        return DeliveryQuote(
            zone_slug=zone_slug, method="", status=MANUAL_REQUIRED, cost=None, reason="unknown_zone"
        )

    # Самовывоз — всегда 0.
    if zone.delivery_type == DeliveryType.PICKUP:
        return DeliveryQuote(
            zone_slug=zone.slug,
            method=zone.delivery_type,
            status=CALCULATED,
            cost=Decimal("0.00"),
            free_delivery=True,
        )

    # СДЭК (внешний перевозчик) — по API; авторасчёт только с весогабаритами.
    if zone.is_external:
        return _external_quote(zone, items)

    # Своя доставка по Пензе — порог бесплатной доставки.
    if zone.free_from is not None and goods_total >= zone.free_from:
        return DeliveryQuote(
            zone_slug=zone.slug,
            method=zone.delivery_type,
            status=CALCULATED,
            cost=Decimal("0.00"),
            free_delivery=True,
            snapshot={"free_from": str(zone.free_from), "price": str(zone.price)},
        )
    return DeliveryQuote(
        zone_slug=zone.slug,
        method=zone.delivery_type,
        status=CALCULATED,
        cost=zone.price,
        snapshot={
            "free_from": str(zone.free_from) if zone.free_from else None,
            "price": str(zone.price),
        },
    )


def _external_quote(zone, items) -> DeliveryQuote:
    """Внешний перевозчик (СДЭК). Без весогабаритов → manual_required."""
    if not _items_have_dimensions(items):
        return DeliveryQuote(
            zone_slug=zone.slug,
            method=zone.delivery_type,
            status=MANUAL_REQUIRED,
            cost=None,
            reason="missing_dimensions",
        )
    from apps.integration_ship import services as ship
    from apps.integration_ship.ports import RateRequest

    total_weight = sum((getattr(getattr(it, "product", None), "weight_kg", 0) or 0) for it in items)
    req = RateRequest(from_city="Пенза", to_city=zone.name, weight_kg=Decimal(str(total_weight)))
    rates = ship.get_rates(req)
    if not rates:
        return DeliveryQuote(
            zone_slug=zone.slug,
            method=zone.delivery_type,
            status=MANUAL_REQUIRED,
            cost=None,
            reason="no_available_tariff",
        )
    best = min(rates, key=lambda r: r.cost)
    return DeliveryQuote(
        zone_slug=zone.slug,
        method=zone.delivery_type,
        status=CALCULATED,
        cost=best.cost,
        snapshot={
            "provider": best.provider,
            "tariff": best.name,
            "cost": str(best.cost),
            "days_min": best.days_min,
            "days_max": best.days_max,
        },
    )


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
