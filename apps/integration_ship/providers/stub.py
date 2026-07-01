"""Stub-провайдер перевозчика: реализует ShipProvider без реальных вызовов.

Используется при отключённых внешних интеграциях (FEATURE_EXTERNAL_SHIP=off)
и в тестах — поведение предсказуемо и не требует внешних API-ключей.
"""

from __future__ import annotations

from decimal import Decimal

from ..ports import RateRequest, RateResult, ShipmentResult


class StubShipProvider:
    """Stub-провайдер: всегда возвращает нулевую цену и фиктивный трек-номер."""

    name = "stub"

    def get_rates(self, request: RateRequest) -> list[RateResult]:
        return [
            RateResult(
                provider=self.name,
                name="Тестовая доставка",
                cost=Decimal("0"),
                days_min=1,
                days_max=3,
            )
        ]

    def create_shipment(self, order_id: int, rate: RateResult) -> ShipmentResult:
        return ShipmentResult(
            provider=self.name,
            tracking_number=f"STUB-{order_id:08d}",
        )
