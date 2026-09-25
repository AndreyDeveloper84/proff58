from django.apps import AppConfig


class LeadsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.leads"
    verbose_name = "Заявки покупателей"

    def ready(self):
        from apps.core.events import product_inquiry_created

        from . import receivers

        # DRF-2296: подписка без гейта FEATURE_EVENTBUS — как у orders и
        # integration_max; иначе при выключенном флаге заказы уведомляли бы
        # сотрудников, а заявки молча нет.
        product_inquiry_created.connect(
            receivers.notify_new_inquiry, dispatch_uid="leads.notify_new_inquiry"
        )
