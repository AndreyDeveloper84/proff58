from django.apps import AppConfig
from django.core.checks import Error, register


class IntegrationMaxConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integration_max"
    verbose_name = "Интеграция MAX"

    def ready(self):
        register(_check_max_webhook_secret)
        # #514: подключаем receivers детерминированно и безусловно — сама
        # подписка (events.*.connect) не трогает БД, а бизнес-флаг max_chat
        # проверяется в notifications.send() при постановке delivery в outbox.
        # Раньше гейт по is_enabled() здесь означал, что более позднее включение
        # флага в рантайме не подключало обработчики без рестарта процесса.
        from . import receivers  # noqa: F401


def _check_max_webhook_secret(app_configs, **kwargs):
    """#428 (M-04): при активной интеграции MAX секрет webhook обязателен.

    Активна = задан MAX_BOT_TOKEN. Без MAX_WEBHOOK_SECRET webhook работает
    fail-closed (отклоняет всё) — это ошибка конфигурации, ловим её на старте
    (manage.py check / деплой), а не молчаливой недоступностью бота.
    """
    from django.conf import settings

    token = (getattr(settings, "MAX_BOT_TOKEN", "") or "").strip()
    errors = []
    if token and not (getattr(settings, "MAX_WEBHOOK_SECRET", "") or "").strip():
        errors.append(
            Error(
                "MAX_BOT_TOKEN задан, но MAX_WEBHOOK_SECRET пуст — webhook отклонит "
                "все запросы (fail-closed).",
                hint="Задайте MAX_WEBHOOK_SECRET в окружении интеграции MAX.",
                id="integration_max.E001",
            )
        )
    if token and not (getattr(settings, "MAX_BOT_USERNAME", "") or "").strip():
        errors.append(
            Error(
                "MAX_BOT_TOKEN задан, но MAX_BOT_USERNAME пуст — QR-код и ссылка "
                "входа через MAX не могут быть сформированы.",
                hint="Задайте публичный ник бота из ответа MAX Bot API GET /me.",
                id="integration_max.E002",
            )
        )
    return errors
