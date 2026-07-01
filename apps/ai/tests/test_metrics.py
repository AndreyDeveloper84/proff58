"""Тесты Prometheus-метрик sourcing pipeline (#374)."""

from __future__ import annotations

import datetime

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.ai.metrics import make_registry
from apps.ai.models import ExternalCall, SourcingBudget, SourcingRun

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_names(registry) -> set[str]:
    return {mf.name for mf in registry.collect()}


def _collect_samples(registry, metric_name: str) -> list:
    for mf in registry.collect():
        if mf.name == metric_name:
            return list(mf.samples)
    return []


def _label_value(samples, labels: dict) -> float | None:
    for s in samples:
        if s.labels == labels:
            return s.value
    return None


# ---------------------------------------------------------------------------
# Unit tests (without DB)
# ---------------------------------------------------------------------------


def test_make_registry_returns_isolated_registry():
    r1 = make_registry()
    r2 = make_registry()
    assert r1 is not r2


# ---------------------------------------------------------------------------
# Integration tests (DB required)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSourcingCollectorMetrics:
    def test_sourcing_collector_produces_expected_metric_families(self):
        registry = make_registry()
        names = _collect_names(registry)
        assert "sourcing_runs_total" in names
        assert "external_calls_total" in names
        assert "content_findings_total" in names

    def test_runs_gauge_counts_correctly(self):
        SourcingRun.objects.create(idempotency_key="m-ok-1", product_ref=10, status="ok")
        SourcingRun.objects.create(idempotency_key="m-ok-2", product_ref=11, status="ok")
        SourcingRun.objects.create(idempotency_key="m-err-1", product_ref=12, status="error")
        registry = make_registry()
        samples = _collect_samples(registry, "sourcing_runs_total")
        assert _label_value(samples, {"status": "ok"}) == 2.0
        assert _label_value(samples, {"status": "error"}) == 1.0
        assert _label_value(samples, {"status": "running"}) == 0.0

    def test_duration_gauge_zero_when_no_finished_runs(self):
        registry = make_registry()
        samples = _collect_samples(registry, "sourcing_run_duration_seconds_avg")
        assert samples[0].value == 0.0

    def test_duration_gauge_non_zero_when_finished_run_exists(self):
        now = timezone.now()
        run = SourcingRun.objects.create(idempotency_key="m-dur-1", product_ref=20, status="ok")
        SourcingRun.objects.filter(pk=run.pk).update(
            created_at=now - datetime.timedelta(seconds=30),
            finished_at=now,
        )
        registry = make_registry()
        samples = _collect_samples(registry, "sourcing_run_duration_seconds_avg")
        assert samples[0].value > 0.0

    def test_external_calls_gauge_by_adapter_and_status(self):
        run = SourcingRun.objects.create(idempotency_key="m-ec-1", product_ref=30, status="ok")
        ExternalCall.objects.create(run=run, adapter="web", status="ok", attempt_count=1)
        registry = make_registry()
        samples = _collect_samples(registry, "external_calls_total")
        assert _label_value(samples, {"adapter": "web", "status": "ok"}) == 1.0

    def test_attempts_gauge_sums_attempt_count(self):
        run = SourcingRun.objects.create(idempotency_key="m-att-1", product_ref=40, status="ok")
        ExternalCall.objects.create(run=run, adapter="marketplace", status="ok", attempt_count=3)
        registry = make_registry()
        samples = _collect_samples(registry, "external_calls_attempts_total")
        assert _label_value(samples, {"adapter": "marketplace"}) == 3.0

    def test_cost_gauge_sums_cost_per_adapter(self):
        run = SourcingRun.objects.create(idempotency_key="m-cost-1", product_ref=50, status="ok")
        ExternalCall.objects.create(
            run=run, adapter="web", status="ok", attempt_count=1, cost="1.5000"
        )
        registry = make_registry()
        samples = _collect_samples(registry, "external_calls_cost_usd_total")
        val = _label_value(samples, {"adapter": "web"})
        assert val is not None
        assert abs(val - 1.5) < 0.001

    def test_budget_gauges_reflect_todays_budget(self):
        today = timezone.localdate()
        SourcingBudget.objects.create(day=today, daily_cap="10.0000", spent="3.5000")
        registry = make_registry()

        cap_samples = _collect_samples(registry, "sourcing_budget_cap_today_usd")
        assert abs(cap_samples[0].value - 10.0) < 0.001

        spent_samples = _collect_samples(registry, "sourcing_budget_spent_today_usd")
        assert abs(spent_samples[0].value - 3.5) < 0.001

    def test_budget_gauges_zero_when_no_budget(self):
        registry = make_registry()
        cap = _collect_samples(registry, "sourcing_budget_cap_today_usd")
        assert cap[0].value == 0.0


# ---------------------------------------------------------------------------
# View tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMetricsView:
    def test_metrics_endpoint_returns_200(self, client):
        response = client.get("/metrics/")
        assert response.status_code == 200

    def test_metrics_endpoint_content_type_is_prometheus(self, client):
        response = client.get("/metrics/")
        assert "text/plain" in response["Content-Type"]

    def test_metrics_endpoint_contains_sourcing_metric(self, client):
        response = client.get("/metrics/")
        assert b"sourcing_runs_total" in response.content

    @override_settings(METRICS_TOKEN="secret123")
    def test_metrics_endpoint_requires_token_when_configured(self, client):
        response = client.get("/metrics/")
        assert response.status_code == 401

    @override_settings(METRICS_TOKEN="secret123")
    def test_metrics_endpoint_accepts_correct_token(self, client):
        response = client.get("/metrics/", HTTP_AUTHORIZATION="Bearer secret123")
        assert response.status_code == 200

    @override_settings(METRICS_TOKEN="secret123")
    def test_metrics_endpoint_rejects_wrong_token(self, client):
        response = client.get("/metrics/", HTTP_AUTHORIZATION="Bearer wrong")
        assert response.status_code == 401
