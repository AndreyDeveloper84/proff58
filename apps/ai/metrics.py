"""Prometheus-экспортёр метрик sourcing pipeline (#374).

Собирает агрегаты из SourcingRun / ExternalCall / ContentFinding / SourcingBudget
на каждый запрос Prometheus-скрейпера. Stateless: данные уже есть в моделях.
"""

from __future__ import annotations

import datetime

from django.db.models import Avg, Count, F, Sum
from django.utils import timezone
from prometheus_client import CollectorRegistry
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector


class SourcingCollector(Collector):
    """Кастомный коллектор: агрегирует таблицы AI при каждом collect()."""

    def collect(self):
        from apps.ai.models import ContentFinding, ExternalCall, SourcingBudget, SourcingRun

        # SourcingRun по статусам
        runs_gauge = GaugeMetricFamily(
            "sourcing_runs_total",
            "Количество SourcingRun по статусу",
            labels=["status"],
        )
        counts = dict(SourcingRun.objects.values_list("status").annotate(cnt=Count("pk")))
        for status, _ in SourcingRun.Status.choices:
            runs_gauge.add_metric([status], counts.get(status, 0))
        yield runs_gauge

        # Средняя длительность завершённых прогонов (секунды)
        duration_gauge = GaugeMetricFamily(
            "sourcing_run_duration_seconds_avg",
            "Средняя длительность завершённых прогонов (секунды)",
        )
        avg_dur = (
            SourcingRun.objects.filter(finished_at__isnull=False)
            .annotate(dur=F("finished_at") - F("created_at"))
            .aggregate(avg=Avg("dur"))["avg"]
        )
        if isinstance(avg_dur, datetime.timedelta):
            duration_gauge.add_metric([], avg_dur.total_seconds())
        else:
            duration_gauge.add_metric([], 0.0)
        yield duration_gauge

        # ExternalCall по адаптеру + статусу
        calls_gauge = GaugeMetricFamily(
            "external_calls_total",
            "Количество ExternalCall по адаптеру и статусу",
            labels=["adapter", "status"],
        )
        for row in ExternalCall.objects.values("adapter", "status").annotate(cnt=Count("pk")):
            calls_gauge.add_metric([row["adapter"], row["status"]], row["cnt"])
        yield calls_gauge

        # Суммарные попытки (attempt_count) по адаптеру
        retries_gauge = GaugeMetricFamily(
            "external_calls_attempts_total",
            "Суммарное количество попыток (attempt_count) по адаптеру",
            labels=["adapter"],
        )
        for row in ExternalCall.objects.values("adapter").annotate(total=Sum("attempt_count")):
            retries_gauge.add_metric([row["adapter"]], row["total"] or 0)
        yield retries_gauge

        # Стоимость по адаптеру (USD)
        cost_gauge = GaugeMetricFamily(
            "external_calls_cost_usd_total",
            "Суммарная стоимость вызовов по адаптеру (USD)",
            labels=["adapter"],
        )
        for row in ExternalCall.objects.values("adapter").annotate(total=Sum("cost")):
            cost_gauge.add_metric([row["adapter"]], float(row["total"] or 0))
        yield cost_gauge

        # ContentFinding по статусам
        findings_gauge = GaugeMetricFamily(
            "content_findings_total",
            "Количество ContentFinding по статусу",
            labels=["status"],
        )
        for row in ContentFinding.objects.values("status").annotate(cnt=Count("pk")):
            findings_gauge.add_metric([row["status"]], row["cnt"])
        yield findings_gauge

        # Дневной бюджет (сегодня)
        today = timezone.localdate()
        budget = SourcingBudget.objects.filter(day=today).first()

        cap_gauge = GaugeMetricFamily(
            "sourcing_budget_cap_today_usd",
            "Лимит дневного бюджета (USD, сегодня)",
        )
        cap_gauge.add_metric([], float(budget.daily_cap) if budget else 0.0)
        yield cap_gauge

        spent_gauge = GaugeMetricFamily(
            "sourcing_budget_spent_today_usd",
            "Израсходовано дневного бюджета (USD, сегодня)",
        )
        spent_gauge.add_metric([], float(budget.spent) if budget else 0.0)
        yield spent_gauge


def make_registry() -> CollectorRegistry:
    """Изолированный реестр с SourcingCollector (без глобальных метрик Python/process)."""
    registry = CollectorRegistry(auto_describe=False)
    registry.register(SourcingCollector())
    return registry


REGISTRY = make_registry()


def metrics_view(request):
    """HTTP-view для Prometheus-скрейпера.

    Если METRICS_TOKEN задан в settings — требует «Authorization: Bearer <token>».
    Иначе открыт (OK для закрытых внутренних сетей).
    """
    from django.conf import settings
    from django.http import HttpResponse
    from django.utils.crypto import constant_time_compare
    from prometheus_client import generate_latest
    from prometheus_client.exposition import CONTENT_TYPE_LATEST

    token = getattr(settings, "METRICS_TOKEN", "")
    if token:
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        # Сравнение за константное время — без timing side-channel для shared-secret.
        if not constant_time_compare(auth, f"Bearer {token}"):
            return HttpResponse("Unauthorized", status=401)

    output = generate_latest(REGISTRY)
    return HttpResponse(output, content_type=CONTENT_TYPE_LATEST)
