from django.apps import AppConfig


class IntegrationMaxConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integration_max"
    verbose_name = "Интеграция MAX"

    def ready(self):
        try:
            from apps.core.features import is_enabled

            if is_enabled("max_chat"):
                pass  # receivers подключаются из integration_max.receivers при наличии
        except Exception:
            pass
