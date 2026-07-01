"""Публичный контракт integration_ship (слой 4 — внешние перевозчики).

Включение: ``FEATURE_EXTERNAL_SHIP=on`` + ``SHIP_PROVIDER=stub|cdek|boxberry``.
По умолчанию используется stub-провайдер (никаких внешних вызовов).

Контракт:
    get_providers() → list[ShipProvider]
    get_rates(request) → list[RateResult]        # расчёт стоимости
    create_shipment(order_id, rate) → ShipmentResult  # создание отправления
"""

from __future__ import annotations

from django.conf import settings

from .ports import RateRequest, RateResult, ShipmentResult, ShipProvider
from .providers.stub import StubShipProvider


def _ship_enabled() -> bool:
    from apps.core.features import is_enabled

    return is_enabled("external_ship")


def _build_provider() -> ShipProvider:
    name = getattr(settings, "SHIP_PROVIDER", "stub")
    if name == "stub" or not _ship_enabled():
        return StubShipProvider()
    raise ValueError(f"Неизвестный SHIP_PROVIDER: {name!r}. Доступен только 'stub' (V1).")


def get_providers() -> list[ShipProvider]:
    """Вернуть список активных провайдеров перевозчиков."""
    return [_build_provider()]


def get_rates(request: RateRequest) -> list[RateResult]:
    """Получить варианты доставки от всех активных провайдеров."""
    results: list[RateResult] = []
    for provider in get_providers():
        try:
            results.extend(provider.get_rates(request))
        except Exception:  # noqa: BLE001 — деградация: сбой провайдера не валит весь расчёт
            pass
    return results


def create_shipment(order_id: int, rate: RateResult) -> ShipmentResult:
    """Создать отправление у провайдера с указанным тарифом."""
    provider = _build_provider()
    return provider.create_shipment(order_id, rate)
