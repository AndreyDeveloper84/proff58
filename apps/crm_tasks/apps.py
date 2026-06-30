from django.apps import AppConfig


class CrmTasksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm_tasks"
    verbose_name = "CRM · Задачи"

    def ready(self):
        from apps.core.features import is_enabled

        if is_enabled("crm"):
            from . import receivers  # noqa: F401
            from .admin import register

            register()
