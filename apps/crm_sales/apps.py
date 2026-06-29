from django.apps import AppConfig


class CrmSalesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm_sales"
    verbose_name = "CRM · Продажи"

    def ready(self):
        from apps.core.features import is_enabled

        if is_enabled("crm"):
            from . import receivers  # noqa: F401
