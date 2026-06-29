from django.apps import AppConfig


class AiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    verbose_name = "AI-слой (рекомендации, обогащение)"

    def ready(self):
        from apps.core.features import is_enabled

        if is_enabled("ai"):
            from . import receivers

            receivers.connect()
