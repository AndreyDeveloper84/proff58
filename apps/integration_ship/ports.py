"""Контракт провайдера перевозчика (порт слоя integration_ship).

Все провайдеры реализуют ``ShipProvider``. Публичный API — в ``services.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RateRequest:
    """Запрос расчёта стоимости доставки."""

    from_city: str
    to_city: str
    weight_kg: Decimal
    order_total: Decimal = Decimal("0")


@dataclass(frozen=True)
class RateResult:
    """Один вариант доставки с рассчитанной стоимостью."""

    provider: str
    name: str
    cost: Decimal
    days_min: int = 0
    days_max: int = 0


@dataclass(frozen=True)
class ShipmentResult:
    """Итог создания отправления у перевозчика."""

    provider: str
    tracking_number: str
    external_id: str = ""
    label_url: str = ""


@runtime_checkable
class ShipProvider(Protocol):
    """Интерфейс провайдера перевозчика (расчёт + создание отправления)."""

    name: str

    def get_rates(self, request: RateRequest) -> list[RateResult]:
        """Получить доступные варианты доставки с ценой."""
        ...

    def create_shipment(self, order_id: int, rate: RateResult) -> ShipmentResult:
        """Создать отправление у перевозчика и вернуть трек-номер."""
        ...
