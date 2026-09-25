"""Тесты контракта integration_ship (#75): интерфейс провайдера + stub + services."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import override_settings

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
    @pytest.fixture(autouse=True)
    def _stub_env(self, settings):
        settings.FEATURES = {"external_ship": True}
        settings.SHIP_PROVIDER = "stub"
        settings.SHIP_ALLOW_STUB = True

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


class _BrokenProvider:
    name = "broken"

    def get_rates(self, request):
        raise TimeoutError("connect timeout")

    def create_shipment(self, order_id, rate):
        raise TimeoutError("connect timeout")


@pytest.mark.django_db
class TestProductionSafety:
    """T1: stub-тариф 0 ₽ никогда не попадает в рабочий режим."""

    @override_settings(
        FEATURES={"external_ship": False}, SHIP_PROVIDER="stub", SHIP_ALLOW_STUB=True
    )
    def test_feature_off_no_providers(self):
        assert services.get_providers() == []

    @override_settings(
        FEATURES={"external_ship": True}, SHIP_PROVIDER="stub", SHIP_ALLOW_STUB=False
    )
    def test_stub_forbidden_without_explicit_allow(self, caplog):
        with caplog.at_level("WARNING"):
            assert services.get_providers() == []
        assert "SHIP_ALLOW_STUB" in caplog.text

    @override_settings(FEATURES={"external_ship": True}, SHIP_PROVIDER="cdek", SHIP_ALLOW_STUB=True)
    def test_unknown_provider_logged_not_raised(self, caplog):
        with caplog.at_level("ERROR"):
            assert services.get_providers() == []
        assert "cdek" in caplog.text
        req = RateRequest(from_city="Пенза", to_city="Кузнецк", weight_kg=Decimal("1"))
        assert services.get_rates(req) == []

    @override_settings(FEATURES={"external_ship": True}, SHIP_PROVIDER="cdek")
    def test_create_shipment_without_provider_raises(self):
        rate = RateResult(provider="cdek", name="Т", cost=Decimal("10"))
        with pytest.raises(services.ShipProviderUnavailable):
            services.create_shipment(order_id=1, rate=rate)

    def test_provider_error_logged_without_pii(self, monkeypatch, caplog):
        monkeypatch.setattr(services, "get_providers", lambda: [_BrokenProvider()])
        req = RateRequest(from_city="Пенза", to_city="ул. Ленина 1, Иванов", weight_kg=Decimal("1"))
        with caplog.at_level("WARNING"):
            assert services.get_rates(req) == []
        assert "broken" in caplog.text
        assert "TimeoutError" in caplog.text
        assert "Иванов" not in caplog.text
