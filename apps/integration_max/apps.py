from django.apps import AppConfig
from django.core.checks import Error, register


class IntegrationMaxConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integration_max"
    verbose_name = "Интеграция MAX"

    def ready(self):
        register(_check_max_webhook_secret)
        try:
            from apps.core.features import is_enabled

            if is_enabled("max_chat"):
                from . import receivers  # noqa: F401
        except Exception:
            pass


def _check_max_webhook_secret(app_configs, **kwargs):
    """#428 (M-04): при активной интеграции MAX секрет webhook обязателен.

    Активна = задан MAX_BOT_TOKEN. Без MAX_WEBHOOK_SECRET webhook работает
    fail-closed (отклоняет всё) — это ошибка конфигурации, ловим её на старте
    (manage.py check / деплой), а не молчаливой недоступностью бота.
    """
    from django.conf import settings

    if getattr(settings, "MAX_BOT_TOKEN", "") and not getattr(settings, "MAX_WEBHOOK_SECRET", ""):
        return [
            Error(
                "MAX_BOT_TOKEN задан, но MAX_WEBHOOK_SECRET пуст — webhook отклонит "
                "все запросы (fail-closed).",
                hint="Задайте MAX_WEBHOOK_SECRET в окружении интеграции MAX.",
                id="integration_max.E001",
            )
        ]
    return []
