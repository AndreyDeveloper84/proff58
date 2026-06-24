"""Корневая конфигурация URL проекта."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", health.healthz, name="healthcheck"),
    path("api/1c/", include("apps.sync_1c.api.urls")),
    path("api/catalog/", include("apps.catalog.api.urls")),
    path("api/max/", include("apps.integration_max.urls")),
    path("api/ai/", include("apps.ai.api.urls")),
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
