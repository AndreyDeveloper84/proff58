from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analytics"
    verbose_name = "Аналитика событий"

    def ready(self):
        from apps.core.features import is_enabled

        if is_enabled("analytics"):
            from . import receivers  # noqa: F401
