"""Prometheus-экспортёр метрик notification domain (#521).

Собирает агрегаты из NotificationLog (delivery/outbox) и Notification (intent/
policy) на каждый запрос скрейпера. Stateless — как apps.ai.metrics.
"""

from __future__ import annotations

import datetime

from django.db.models import Avg, Count, F, Min
from django.utils import timezone
from prometheus_client import CollectorRegistry
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector


class NotificationCollector(Collector):
    """Кастомный коллектор: агрегирует NotificationLog/Notification при каждом collect()."""

    def collect(self):
        from .models import Notification, NotificationLog, NotificationStatus

        # Доставка по статусу (queued/sending/sent/failed/skipped/unknown).
        delivery_gauge = GaugeMetricFamily(
            "notification_delivery_total",
            "Количество NotificationLog по статусу outbox",
            labels=["status"],
        )
        counts = dict(NotificationLog.objects.values_list("status").annotate(cnt=Count("pk")))
        for status, _label in NotificationStatus.choices:
            delivery_gauge.add_metric([status], counts.get(status, 0))
        yield delivery_gauge

        # FAILED, разбитые по классификации (retryable/permanent/неклассифицировано).
        failed_gauge = GaugeMetricFamily(
            "notification_delivery_failed_total",
            "FAILED-строки outbox по классификации ошибки (#521)",
            labels=["error_kind"],
        )
        failed_counts = dict(
            NotificationLog.objects.filter(status=NotificationStatus.FAILED)
            .values_list("error_kind")
            .annotate(cnt=Count("pk"))
        )
        for kind in ("retryable", "permanent", ""):
            failed_gauge.add_metric([kind or "unclassified"], failed_counts.get(kind, 0))
        yield failed_gauge

        # Queue lag: сколько сейчас "висит" в QUEUED и как давно самая старая строка
        # — одним aggregate (COUNT+MIN), а не двумя отдельными запросами.
        queue_stats = NotificationLog.objects.filter(status=NotificationStatus.QUEUED).aggregate(
            cnt=Count("pk"), oldest=Min("created_at")
        )
        queue_size_gauge = GaugeMetricFamily(
            "notification_queue_size", "Строк outbox в статусе queued прямо сейчас"
        )
        queue_size_gauge.add_metric([], queue_stats["cnt"])
        yield queue_size_gauge

        oldest = queue_stats["oldest"]
        lag_gauge = GaugeMetricFamily(
            "notification_queue_lag_seconds",
            "Возраст самой старой queued-строки outbox (секунды)",
        )
        lag_gauge.add_metric([], (timezone.now() - oldest).total_seconds() if oldest else 0.0)
        yield lag_gauge

        # Intent policy-skip по причине (#515/#516/#518 — category_disabled:*, max_disabled).
        skip_gauge = GaugeMetricFamily(
            "notification_intent_skipped_total",
            "Notification intent с непустым policy_skip_reason, по причине",
            labels=["reason"],
        )
        for row in (
            Notification.objects.exclude(policy_skip_reason="")
            .values("policy_skip_reason")
            .annotate(cnt=Count("pk"))
        ):
            skip_gauge.add_metric([row["policy_skip_reason"]], row["cnt"])
        yield skip_gauge

        # Средняя задержка intent → sent (секунды) — по завершённым Notification с delivery.
        latency_gauge = GaugeMetricFamily(
            "notification_intent_to_sent_seconds_avg",
            "Средняя задержка между созданием intent и отправкой delivery (секунды)",
        )
        avg_latency = (
            Notification.objects.filter(delivery__status=NotificationStatus.SENT)
            .annotate(latency=F("delivery__updated_at") - F("created_at"))
            .aggregate(avg=Avg("latency"))["avg"]
        )
        if isinstance(avg_latency, datetime.timedelta):
            latency_gauge.add_metric([], avg_latency.total_seconds())
        else:
            latency_gauge.add_metric([], 0.0)
        yield latency_gauge


def make_registry() -> CollectorRegistry:
    registry = CollectorRegistry(auto_describe=False)
    registry.register(NotificationCollector())
    return registry


REGISTRY = make_registry()


def metrics_view(request):
    """HTTP-view для Prometheus-скрейпера — та же схема токена, что apps.ai.metrics."""
    from django.conf import settings
    from django.http import HttpResponse
    from django.utils.crypto import constant_time_compare
    from prometheus_client import generate_latest
    from prometheus_client.exposition import CONTENT_TYPE_LATEST

    token = getattr(settings, "METRICS_TOKEN", "")
    if token:
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not constant_time_compare(auth, f"Bearer {token}"):
            return HttpResponse("Unauthorized", status=401)

    output = generate_latest(REGISTRY)
    return HttpResponse(output, content_type=CONTENT_TYPE_LATEST)
