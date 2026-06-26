from django.apps import AppConfig


class LeadsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.leads"
    verbose_name = "Заявки"

    def ready(self):
        from apps.core.features import is_enabled
        from apps.core.events import product_inquiry_created
        from . import receivers

        if is_enabled("eventbus"):
            product_inquiry_created.connect(
                receivers.notify_new_inquiry, dispatch_uid="leads.notify_new_inquiry"
            )
