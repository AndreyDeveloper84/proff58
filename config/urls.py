"""Корневая конфигурация URL проекта."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.ai.metrics import metrics_view
from apps.core import health
from apps.notifications.metrics import metrics_view as notifications_metrics_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", health.healthz, name="healthcheck"),
    path("metrics/", metrics_view, name="prometheus-metrics"),
    path(
        "metrics/notifications/", notifications_metrics_view, name="notifications-metrics"
    ),  # #521
    path("api/1c/", include("apps.sync_1c.api.urls")),
    path("api/catalog/", include("apps.catalog.api.urls")),
    path("api/payments/", include("apps.payments.urls")),
    path("api/max/", include("apps.integration_max.urls")),
    path("api/", include("apps.integration_max.api.urls")),
    path("api/", include("apps.notifications.api.urls")),
    path("api/leads/", include("apps.leads.api.urls")),
    path("api/ai/", include("apps.ai.api.urls")),
    path("api/account/", include("apps.accounts.api.urls")),
    path("api/core/", include("apps.core.urls")),
    path("api/delivery/", include("apps.delivery.urls")),
    path("api/", include("apps.orders.api.urls")),
    path("catalog/", include("apps.catalog.storefront_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    try:
        import debug_toolbar

        urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    except ImportError:
        pass
