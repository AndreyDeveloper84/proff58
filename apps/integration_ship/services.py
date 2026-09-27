"""Публичный контракт integration_ship (слой 4 — внешние перевозчики).

Включение: ``FEATURE_EXTERNAL_SHIP=on`` + ``SHIP_PROVIDER=<имя>``.
СДЭК (``SHIP_PROVIDER=cdek``, DRF-2299) считается отдельным контрактом
``cdek_quote``/``cdek_cities``/``cdek_points`` в конце модуля, а не через
``get_rates``: ему нужны код города, режим, посылки и объявленная стоимость.
Stub-провайдер (тариф 0 ₽, трек ``STUB-…``) допустим **только**
при явном ``SHIP_ALLOW_STUB=True`` (dev/тесты); в рабочем режиме он никогда не
подставляется, чтобы неизвестная стоимость не превращалась в «бесплатно».

Контракт:
    get_providers() → list[ShipProvider]         # пусто ⇒ авторасчёт недоступен
    get_rates(request) → list[RateResult]        # расчёт стоимости
    create_shipment(order_id, rate) → ShipmentResult  # создание отправления
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache

from .ports import Parcel, RateRequest, RateResult, ShipmentResult, ShipProvider
from .providers.stub import StubShipProvider

logger = logging.getLogger(__name__)


class ShipProviderUnavailable(RuntimeError):
    """Провайдер перевозчика не сконфигурирован или недоступен."""


def _ship_enabled() -> bool:
    from apps.core.features import is_enabled

    return is_enabled("external_ship")


def _build_provider() -> ShipProvider | None:
    """Собрать провайдера по настройкам; ``None`` — авторасчёт недоступен."""
    if not _ship_enabled():
        return None
    name = getattr(settings, "SHIP_PROVIDER", "stub")
    if name == "stub":
        if getattr(settings, "SHIP_ALLOW_STUB", False):
            return StubShipProvider()
        logger.warning(
            "integration_ship: SHIP_PROVIDER=stub запрещён вне тестового окружения "
            "(SHIP_ALLOW_STUB=False) — авторасчёт доставки недоступен"
        )
        return None
    logger.error(
        "integration_ship: неизвестный SHIP_PROVIDER=%r — авторасчёт доставки недоступен", name
    )
    return None


def get_providers() -> list[ShipProvider]:
    """Вернуть список активных провайдеров перевозчиков (может быть пустым)."""
    provider = _build_provider()
    return [provider] if provider is not None else []


def get_rates(request: RateRequest) -> list[RateResult]:
    """Получить варианты доставки от всех активных провайдеров.

    Сбой провайдера (ошибка, таймаут) логируется без персональных данных и
    не валит расчёт: вызывающий получает пустой список ⇒ ручной расчёт.
    """
    results: list[RateResult] = []
    for provider in get_providers():
        try:
            results.extend(provider.get_rates(request))
        except Exception as exc:  # noqa: BLE001 — деградация: сбой провайдера не валит весь расчёт
            logger.warning(
                "integration_ship: провайдер %s не рассчитал тариф (%s: %s)",
                provider.name,
                type(exc).__name__,
                exc,
            )
    return results


def create_shipment(order_id: int, rate: RateResult) -> ShipmentResult:
    """Создать отправление у провайдера с указанным тарифом."""
    provider = _build_provider()
    if provider is None:
        raise ShipProviderUnavailable("Провайдер перевозчика не сконфигурирован")
    return provider.create_shipment(order_id, rate)


# ── СДЭК (DRF-2299) ───────────────────────────────────────────────────────
#
# Расчёт идёт мимо общего ``get_rates``: там тариф ищется по названию города и весу,
# а СДЭК нужны код города, режим (пункт выдачи / курьер), посылки с габаритами и
# объявленная стоимость. И вызывающему важно отличать «СДЭК не ответил» от «такой
# доставки нет» — ``get_rates`` глушит оба в пустой список.

CDEK_PVZ = "pvz"
CDEK_COURIER = "courier"
CDEK_MODES = (CDEK_PVZ, CDEK_COURIER)

# Причины, по которым цену СДЭК получить не удалось (→ ручной расчёт менеджером).
PROVIDER_DISABLED = "provider_disabled"
PROVIDER_UNAVAILABLE = "provider_unavailable"
NO_TARIFF = "no_tariff"

# Тарифы «Посылка» и режимы доставки СДЭК: (пункт выдачи, курьер).
# warehouse — магазин сдаёт посылки в пункт СДЭК, door — СДЭК забирает у магазина.
_TARIFFS = {"warehouse": (136, 137), "door": (138, 139)}
_DELIVERY_MODES = {"warehouse": (4, 3), "door": (2, 1)}

_CITIES_TTL = 3600
_POINTS_TTL = 1800
_TARIFFS_TTL = 600


@dataclass(frozen=True)
class CarrierQuote:
    """Цена доставки СДЭК или причина, по которой её нет (``cost is None``)."""

    cost: Decimal | None
    reason: str = ""
    tariff_code: int = 0
    period_min: int = 0
    period_max: int = 0


def cdek_enabled() -> bool:
    """Включён ли расчёт СДЭК: флаг, провайдер cdek и заданные ключи."""
    from .providers import cdek

    return (
        _ship_enabled()
        and getattr(settings, "SHIP_PROVIDER", "") == "cdek"
        and cdek.is_configured()
    )


def _ship_from() -> str:
    value = getattr(settings, "CDEK_SHIP_FROM", "warehouse")
    return value if value in _TARIFFS else "warehouse"


def _configured_tariff(mode: str) -> int:
    idx = CDEK_MODES.index(mode)
    explicit = getattr(
        settings, "CDEK_TARIFF_PVZ" if mode == CDEK_PVZ else "CDEK_TARIFF_COURIER", 0
    )
    return int(explicit or _TARIFFS[_ship_from()][idx])


def _cache_key(prefix: str, *parts) -> str:
    raw = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return f"cdek:{prefix}:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


def _cached(key: str, ttl: int, compute):
    """Кеш поверх ``compute``; недоступный кеш не мешает расчёту. Пустой ответ не
    кешируется: пустой список городов или пунктов может быть случайным сбоем."""
    try:
        hit = cache.get(key)
    except Exception:  # noqa: BLE001 — кеш вспомогательный
        hit = None
    if hit is not None:
        return hit
    value = compute()
    if value is None or value == []:
        return value
    try:
        cache.set(key, value, ttl)
    except Exception:  # noqa: BLE001
        pass
    return value


def cdek_cities(query: str):
    """Подсказки городов России по началу названия (кеш — час)."""
    from .providers import cdek

    query = " ".join((query or "").split())
    if len(query) < 2:
        return []
    return _cached(
        _cache_key("cities", query.lower()), _CITIES_TTL, lambda: cdek.suggest_cities(query)
    )


def cdek_city_name(city_code: int) -> str:
    """Название города по коду СДЭК (кеш — час); «» — такого кода нет."""
    from .providers import cdek

    return _cached(
        _cache_key("city", int(city_code)), _CITIES_TTL, lambda: cdek.city_name(int(city_code))
    )


def cdek_points(city_code: int):
    """Пункты выдачи СДЭК в городе (кеш — 30 минут)."""
    from .providers import cdek

    return _cached(
        _cache_key("points", int(city_code)),
        _POINTS_TTL,
        lambda: cdek.delivery_points(int(city_code)),
    )


def cdek_quote(
    *, to_city_code: int, mode: str, parcels: list[Parcel], declared_value: Decimal
) -> CarrierQuote:
    """Цена доставки СДЭК с НДС и страховкой на стоимость товаров.

    Сначала настроенный тариф режима. Если СДЭК его на этом маршруте не даёт —
    самый дешёвый тариф того же режима из списка маршрута. Сеть, таймаут, 5xx,
    отвергнутые ключи — ``provider_unavailable``; подходящего тарифа нет — ``no_tariff``.
    """
    from .providers import cdek

    if not cdek_enabled():
        return CarrierQuote(cost=None, reason=PROVIDER_DISABLED)
    if mode not in CDEK_MODES:
        raise ValueError(f"Неизвестный режим доставки СДЭК: {mode!r}")
    from_code = int(getattr(settings, "CDEK_FROM_CITY_CODE", 504))
    route = {"from_code": from_code, "to_code": int(to_city_code), "parcels": parcels}

    def price(code: int) -> CarrierQuote:
        t = _cached(
            _cache_key("tariff", code, route, declared_value),
            _TARIFFS_TTL,
            lambda: cdek.tariff(code, declared_value=declared_value, **route),
        )
        return CarrierQuote(
            cost=t.cost, tariff_code=code, period_min=t.period_min, period_max=t.period_max
        )

    def fatal(exc: cdek.CdekError) -> bool:
        # «Этот тариф не подходит» — пробуем другой; остальное — СДЭК недоступен.
        return exc.retryable or exc.auth

    configured = _configured_tariff(mode)
    try:
        try:
            return price(configured)
        except cdek.CdekError as exc:
            if fatal(exc):
                raise
        wanted_mode = _DELIVERY_MODES[_ship_from()][CDEK_MODES.index(mode)]
        tariffs = _cached(
            _cache_key("tarifflist", route),
            _TARIFFS_TTL,
            lambda: cdek.tariff_list(**route),
        )
        candidates = sorted(
            (t for t in tariffs if t.delivery_mode == wanted_mode and t.code != configured),
            key=lambda t: t.cost,
        )
        for candidate in candidates[:3]:
            try:
                return price(candidate.code)
            except cdek.CdekError as exc:
                if fatal(exc):
                    raise
        return CarrierQuote(cost=None, reason=NO_TARIFF)
    except cdek.CdekError as exc:
        if exc.auth:
            # Отозванные или неверные ключи: все заказы молча ушли бы в ручной расчёт.
            logger.error("integration_ship: СДЭК отверг ключи (%s) — проверьте CDEK_*", exc)
        else:
            logger.warning("integration_ship: СДЭК не рассчитал доставку (%s)", exc)
        return CarrierQuote(cost=None, reason=PROVIDER_UNAVAILABLE)
