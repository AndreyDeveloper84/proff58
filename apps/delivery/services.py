"""Сервисный слой доставки.

Два контракта:
- ``calculate(*, zone_slug, cart_total)`` — витринная подсказка (список зон+цен);
- ``quote_for_order(*, zone_slug, goods_total, items)`` — СЕРВЕРНЫЙ расчёт для
  checkout (#429/M-05): единственный источник правды по стоимости доставки,
  считается по серверной корзине внутри транзакции заказа.

Контракт ADR-0013 (#444, Wave 1) — ``docs/adr/ADR-0013-b2b-vat-delivery-contract.md``:
- самовывоз — 0 ₽;
- своя доставка по Пензе — <7000 ₽ → 500 ₽, ≥7000 ₽ → бесплатно (порог по
  стоимости товаров после скидок, без доставки);
- СДЭК (область, ``is_external``) — всегда по API перевозчика, порог не
  применяется; авторасчёт только при заполненных весе/габаритах у всех товаров,
  иначе ``manual_required`` (стоимость определит менеджер).

СДЭК по России (DRF-2299) считается в два шага, чтобы HTTP-вызовы перевозчика не
шли внутри транзакции заказа, где держатся замки корзины и товаров:
1. ``quote_carrier`` — по запросу чекаута: город, пункт выдачи или адрес, посылки
   из упаковки товаров, цена СДЭК. Результат кладётся в кеш под ``quote_id``.
2. ``quote_for_order(..., carrier_quote_id=...)`` внутри ``place_order`` только
   читает этот расчёт и сверяет, что корзина та же. Расчёт истёк или корзина
   изменилась — ``DeliveryQuoteError``: покупатель пересчитывает доставку.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import DeliveryType, DeliveryZone, PickupPoint

logger = logging.getLogger(__name__)

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
    is_external: bool = False


# DRF-2299: способы получения через СДЭК → режим расчёта у перевозчика.
CARRIER_METHODS = {"cdek_pvz": "pvz", "cdek_courier": "courier"}

QUOTE_EXPIRED = "delivery_quote_expired"
QUOTE_STALE = "delivery_quote_stale"
_QUOTE_KEY = "delivery:carrier-quote:{}"


class DeliveryQuoteError(Exception):
    """Расчёт доставки для заказа нельзя использовать — нужно пересчитать."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class DeliveryInputError(ValueError):
    """Неверные данные получателя для расчёта доставки."""

    def __init__(self, field_name: str, message: str):
        super().__init__(message)
        self.field = field_name
        self.message = message


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


def quote_for_order(
    *,
    zone_slug: str,
    goods_total: Decimal,
    items,
    method: str = "",
    carrier_quote_id: str = "",
) -> DeliveryQuote:
    """Серверный расчёт доставки для заказа. Единый источник правды.

    ``zone_slug`` — выбранная зона; ``goods_total`` — сумма товаров (после скидок,
    без доставки); ``items`` — строки заказа/корзины (для проверки весогабаритов
    при СДЭК). Пустой ``zone_slug`` → NOT_REQUIRED (доставка не выбрана).
    ``method`` и ``carrier_quote_id`` — способ получения и расчёт СДЭК из
    ``quote_carrier``; HTTP к перевозчику отсюда не уходит.
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
        return _carrier_quote_for_order(zone, items, method, carrier_quote_id)

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
            is_external=True,
        )
    from apps.integration_ship import services as ship
    from apps.integration_ship.ports import RateRequest

    if not ship.get_providers():
        # Реального провайдера нет (stub запрещён вне тестов, интеграция не
        # подключена) — стоимость неизвестна, считает менеджер, а не 0 ₽.
        return DeliveryQuote(
            zone_slug=zone.slug,
            method=zone.delivery_type,
            status=MANUAL_REQUIRED,
            cost=None,
            reason="provider_unavailable",
            is_external=True,
        )

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
            is_external=True,
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
        is_external=True,
    )


# ── СДЭК по России (DRF-2299) ─────────────────────────────────────────────


def cart_fingerprint(lines) -> str:
    """Отпечаток состава корзины: пары (товар, количество) без учёта порядка."""
    pairs = sorted((int(pid), int(qty)) for pid, qty in lines)
    return hashlib.sha256(json.dumps(pairs).encode()).hexdigest()[:32]


def _manual(zone, method: str, reason: str, snapshot: dict) -> DeliveryQuote:
    return DeliveryQuote(
        zone_slug=zone.slug,
        method=method,
        status=MANUAL_REQUIRED,
        cost=None,
        snapshot={**snapshot, "reason": reason},
        reason=reason,
        is_external=True,
    )


def _carrier_quote_for_order(zone, items, method: str, carrier_quote_id: str) -> DeliveryQuote:
    from apps.integration_ship import services as ship

    if not carrier_quote_id:
        if method in CARRIER_METHODS or ship.cdek_enabled():
            # Получатель не выбран или чекаут старый — стоимость считает менеджер.
            reason = "no_carrier_quote" if ship.cdek_enabled() else ship.PROVIDER_DISABLED
            return _manual(zone, method or zone.delivery_type, reason, {"provider": "cdek"})
        return _external_quote(zone, items)

    try:
        stored = cache.get(_QUOTE_KEY.format(carrier_quote_id))
    except Exception:  # noqa: BLE001 — кеш недоступен: считаем расчёт потерянным
        logger.warning("delivery: кеш расчётов доставки недоступен")
        stored = None
    if stored is None:
        raise DeliveryQuoteError(
            QUOTE_EXPIRED, "Расчёт доставки устарел — выберите доставку ещё раз."
        )
    fingerprint = cart_fingerprint((it.product_id, it.quantity) for it in items)
    if (
        stored["zone_slug"] != zone.slug
        or stored["method"] != method
        or stored["fingerprint"] != fingerprint
    ):
        raise DeliveryQuoteError(
            QUOTE_STALE, "Корзина или способ доставки изменились — пересчитайте доставку."
        )
    cost = Decimal(stored["cost"]) if stored["cost"] is not None else None
    return DeliveryQuote(
        zone_slug=zone.slug,
        method=method,
        status=stored["status"],
        cost=cost,
        snapshot=stored["snapshot"],
        reason=stored["reason"],
        is_external=True,
    )


def _destination(method: str, destination: dict) -> tuple[dict, object | None]:
    """Проверить получателя и собрать его часть снимка.

    Название города берётся у СДЭК по коду, а не из браузера: цена считается по коду,
    и в заказ должен попасть тот же город. Пункт выдачи сверяется со справочником
    города. Возвращает снимок и точку (для пункта выдачи). СДЭК не ответил —
    в снимке ``unavailable``: тариф тогда не запрашиваем, считает менеджер.
    """
    from apps.integration_ship import services as ship
    from apps.integration_ship.providers.cdek import CdekError

    try:
        city_code = int(destination.get("city_code") or 0)
    except (TypeError, ValueError):
        city_code = 0
    if city_code <= 0:
        raise DeliveryInputError("city_code", "Выберите город из списка.")
    snapshot = {
        "provider": "cdek",
        "mode": CARRIER_METHODS[method],
        "city_code": city_code,
        "city_name": "",
        "pvz_code": "",
        "address": "",
    }
    if method == "cdek_courier":
        address = str(destination.get("address") or "").strip()
        if not address:
            raise DeliveryInputError("address", "Укажите адрес доставки.")
        if len(address) > 300:
            raise DeliveryInputError("address", "Адрес слишком длинный.")
        snapshot["address"] = address
    else:
        pvz_code = str(destination.get("pvz_code") or "").strip()[:64]
        if not pvz_code:
            raise DeliveryInputError("pvz_code", "Выберите пункт выдачи.")
        snapshot["pvz_code"] = pvz_code

    try:
        city_name = ship.cdek_city_name(city_code)
        points = ship.cdek_points(city_code) if method == "cdek_pvz" else []
    except CdekError:
        # Название из браузера — только чтобы менеджер видел, что выбрал покупатель.
        snapshot["city_name"] = str(destination.get("city_name") or "").strip()[:200]
        snapshot["unavailable"] = True
        return snapshot, None
    if not city_name:
        raise DeliveryInputError("city_code", "Выберите город из списка.")
    snapshot["city_name"] = city_name
    if method == "cdek_courier":
        return snapshot, None
    point = next((p for p in points if p.code == snapshot["pvz_code"]), None)
    if point is None:
        raise DeliveryInputError("pvz_code", "Пункт выдачи не найден в выбранном городе.")
    snapshot["pvz_name"] = point.name
    snapshot["address"] = point.address
    return snapshot, point


def quote_carrier(
    *, zone_slug: str, method: str, lines, goods_total: Decimal, destination: dict
) -> tuple[DeliveryQuote, str]:
    """Расчёт доставки СДЭК для корзины (вне транзакции заказа).

    ``lines`` — пары (product_id, количество) серверной корзины; ``goods_total`` —
    объявленная стоимость для страховки. Возвращает расчёт и ``quote_id``, по
    которому ``place_order`` его найдёт. Ручной расчёт тоже сохраняется: менеджер
    увидит в заказе город и пункт выдачи.
    """
    from apps.catalog.packaging import package_for
    from apps.integration_ship import services as ship

    from .packaging import OVERWEIGHT, build_parcels

    if method not in CARRIER_METHODS:
        raise DeliveryInputError("method", "Неизвестный способ доставки СДЭК.")
    zone = DeliveryZone.objects.filter(slug=zone_slug, is_active=True, is_external=True).first()
    if zone is None:
        raise DeliveryInputError("zone", "Доставка СДЭК сейчас недоступна.")
    lines = [(int(pid), int(qty)) for pid, qty in lines]
    if not lines:
        raise DeliveryInputError("cart", "Корзина пуста.")

    snapshot: dict = {"provider": "cdek"}
    if not ship.cdek_enabled():
        quote = _manual(zone, method, ship.PROVIDER_DISABLED, snapshot)
    else:
        snapshot, point = _destination(method, destination)
        packages = package_for([pid for pid, _ in lines])
        max_weight_g = int(getattr(settings, "CDEK_MAX_PARCEL_WEIGHT_G", 30000))
        point_limit_g = (point.weight_max_kg or 0) * 1000 if point is not None else 0
        point_is_stricter = 0 < point_limit_g < max_weight_g
        if point_is_stricter:
            # Посылки не тяжелее того, что принимает выбранный пункт выдачи.
            max_weight_g = point_limit_g
        plan = build_parcels(
            [(packages.get(pid), qty) for pid, qty in lines], max_weight_g=max_weight_g
        )
        if plan.reason == OVERWEIGHT and point_is_stricter:
            raise DeliveryInputError(
                "pvz_code",
                f"Пункт выдачи принимает посылки до {point.weight_max_kg} кг — "
                "выберите другой пункт или доставку курьером.",
            )
        if snapshot.get("unavailable"):
            quote = _manual(zone, method, ship.PROVIDER_UNAVAILABLE, snapshot)
        elif plan.reason:
            quote = _manual(zone, method, plan.reason, snapshot)
        else:
            snapshot["parcels"] = [
                {
                    "weight_g": p.weight_g,
                    "length_cm": p.length_cm,
                    "width_cm": p.width_cm,
                    "height_cm": p.height_cm,
                }
                for p in plan.parcels
            ]
            snapshot["declared_value"] = str(goods_total)
            result = ship.cdek_quote(
                to_city_code=snapshot["city_code"],
                mode=snapshot["mode"],
                parcels=list(plan.parcels),
                declared_value=goods_total,
            )
            if result.cost is None:
                quote = _manual(zone, method, result.reason, snapshot)
            else:
                snapshot.update(
                    tariff_code=result.tariff_code,
                    cost=str(result.cost),
                    period_min=result.period_min,
                    period_max=result.period_max,
                )
                quote = DeliveryQuote(
                    zone_slug=zone.slug,
                    method=method,
                    status=CALCULATED,
                    cost=result.cost,
                    snapshot=snapshot,
                    is_external=True,
                )

    snapshot = {**quote.snapshot, "calculated_at": timezone.now().isoformat()}
    stored = {
        "fingerprint": cart_fingerprint(lines),
        "zone_slug": zone.slug,
        "method": method,
        "status": quote.status,
        "cost": str(quote.cost) if quote.cost is not None else None,
        "reason": quote.reason,
        "snapshot": snapshot,
    }
    quote_id = hashlib.sha256(
        json.dumps(stored, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:32]
    stored["snapshot"]["quote_id"] = quote_id
    cache.set(_QUOTE_KEY.format(quote_id), stored, int(getattr(settings, "CDEK_QUOTE_TTL", 1800)))
    return quote, quote_id


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
                "cost": Decimal|None, # итоговая стоимость; None — уточняется после оформления
                "free_delivery": bool # бесплатна ли доставка
            }
    """
    qs = DeliveryZone.objects.filter(is_active=True)
    if zone_slug is not None:
        qs = qs.filter(slug=zone_slug)
    zones = qs.order_by("sort_order", "name")

    result: list[dict] = []
    for zone in zones:
        # Внешний перевозчик (СДЭК): на витрине стоимость неизвестна — её даёт API
        # перевозчика по весогабаритам при оформлении либо менеджер вручную.
        # Раньше сюда попадала price зоны (0) и чекаут показывал «бесплатно»
        # (DRF-2299): нулевая цена вместо «неизвестно» — ложное обещание.
        cost = None if zone.is_external else _calculate_zone_cost(zone, cart_total)
        entry = {
            "zone": zone.slug,
            "name": zone.name,
            "type": zone.delivery_type,
            "cost": cost,  # None ⇔ стоимость уточняется (как DeliveryQuote.cost)
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
