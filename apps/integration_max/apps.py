"""Конфигурация приложения integration_max — уведомления через MAX Bot (#48)."""

from django.apps import AppConfig


class IntegrationMaxConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integration_max"
    verbose_name = "Интеграция с MAX"

    def ready(self) -> None:
        from apps.core.features import is_enabled

        if is_enabled("max_chat"):
            from . import receivers  # noqa: F401
