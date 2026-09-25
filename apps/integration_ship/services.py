"""Публичный контракт integration_ship (слой 4 — внешние перевозчики).

Включение: ``FEATURE_EXTERNAL_SHIP=on`` + ``SHIP_PROVIDER=<имя>``.
Реальных провайдеров пока нет (СДЭК/Boxberry — по мере появления договора и
API-доступа). Stub-провайдер (тариф 0 ₽, трек ``STUB-…``) допустим **только**
при явном ``SHIP_ALLOW_STUB=True`` (dev/тесты); в рабочем режиме он никогда не
подставляется, чтобы неизвестная стоимость не превращалась в «бесплатно».

Контракт:
    get_providers() → list[ShipProvider]         # пусто ⇒ авторасчёт недоступен
    get_rates(request) → list[RateResult]        # расчёт стоимости
    create_shipment(order_id, rate) → ShipmentResult  # создание отправления
"""

from __future__ import annotations

import logging

from django.conf import settings

from .ports import RateRequest, RateResult, ShipmentResult, ShipProvider
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
