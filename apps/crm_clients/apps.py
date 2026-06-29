from django.apps import AppConfig


class CrmClientsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm_clients"
    verbose_name = "CRM · Клиенты"

    def ready(self):
        from apps.core.features import is_enabled

        if is_enabled("crm"):
            from . import receivers  # noqa: F401
