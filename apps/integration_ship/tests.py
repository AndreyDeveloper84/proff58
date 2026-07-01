"""Тесты контракта integration_ship (#75): интерфейс провайдера + stub + services."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.integration_ship import services
from apps.integration_ship.ports import RateRequest, RateResult, ShipProvider
from apps.integration_ship.providers.stub import StubShipProvider


class TestStubProvider:
    def test_implements_ship_provider_protocol(self):
        assert isinstance(StubShipProvider(), ShipProvider)

    def test_get_rates_returns_non_empty_list(self):
        provider = StubShipProvider()
        req = RateRequest(from_city="Пенза", to_city="Москва", weight_kg=Decimal("1.5"))
        rates = provider.get_rates(req)
        assert isinstance(rates, list)
        assert len(rates) > 0

    def test_rate_has_required_fields(self):
        provider = StubShipProvider()
        req = RateRequest(from_city="Пенза", to_city="Москва", weight_kg=Decimal("1.0"))
        rate = provider.get_rates(req)[0]
        assert isinstance(rate, RateResult)
        assert rate.provider == "stub"
        assert isinstance(rate.cost, Decimal)

    def test_create_shipment_returns_tracking(self):
        provider = StubShipProvider()
        rate = RateResult(provider="stub", name="Тест", cost=Decimal("0"))
        result = provider.create_shipment(order_id=42, rate=rate)
        assert result.provider == "stub"
        assert "42" in result.tracking_number


@pytest.mark.django_db
class TestServices:
    def test_get_providers_returns_list(self):
        providers = services.get_providers()
        assert isinstance(providers, list)
        assert len(providers) > 0

    def test_get_rates_returns_list(self):
        req = RateRequest(from_city="Пенза", to_city="Москва", weight_kg=Decimal("2.0"))
        rates = services.get_rates(req)
        assert isinstance(rates, list)

    def test_create_shipment_returns_result(self):
        rate = RateResult(provider="stub", name="Тест", cost=Decimal("0"))
        result = services.create_shipment(order_id=1, rate=rate)
        assert result.tracking_number

    def test_stub_is_default_provider(self):
        providers = services.get_providers()
        assert providers[0].name == "stub"
