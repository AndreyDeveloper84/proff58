from django.apps import AppConfig
from django.core.checks import Error, register


class IntegrationOAuthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integration_oauth"
    verbose_name = "Вход через VK ID и Яндекс ID"

    def ready(self):
        register(_check_oauth_config)
        from apps.accounts.services import register_reset_eligibility

        from . import receivers  # noqa: F401 — подписка на user_deleted
        from .services import has_oauth_account

        # Аккаунт из VK ID / Яндекс ID создаётся без пароля: «Забыли пароль» —
        # его способ восстановить доступ, если провайдер недоступен.
        register_reset_eligibility(has_oauth_account)


def _check_oauth_config(app_configs, **kwargs):
    """Ключи провайдера заданы, а SITE_URL непригоден → redirect_uri не собрать.

    Провайдер при этом тихо выключен (кнопок нет) — ловим на старте
    (manage.py check / деплой), а не жалобой «кнопка VK пропала».
    """
    from django.conf import settings

    from .providers import site_origin

    def _set(name):
        return bool((getattr(settings, name, "") or "").strip())

    errors = []
    configured = [
        name
        for name, keys in (
            ("VK ID", ("VKID_CLIENT_ID",)),
            ("Яндекс ID", ("YANDEX_ID_CLIENT_ID", "YANDEX_ID_CLIENT_SECRET")),
        )
        if any(_set(k) for k in keys)
    ]
    if configured and not site_origin():
        errors.append(
            Error(
                f"Заданы ключи входа через {', '.join(configured)}, а SITE_URL пуст, не https "
                "или содержит путь — адрес возврата от провайдера не собрать.",
                hint="Задайте SITE_URL вида https://proff58.ru (без пути и хвоста).",
                id="integration_oauth.E001",
            )
        )
    if _set("YANDEX_ID_CLIENT_ID") != _set("YANDEX_ID_CLIENT_SECRET"):
        errors.append(
            Error(
                "Для Яндекс ID задан только один из YANDEX_ID_CLIENT_ID / "
                "YANDEX_ID_CLIENT_SECRET — вход через Яндекс выключен.",
                hint="Задайте оба значения из oauth.yandex.ru или очистите оба.",
                id="integration_oauth.E002",
            )
        )
    return errors
