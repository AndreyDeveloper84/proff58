from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.orders"
    verbose_name = "Заказы"

    def ready(self):
        # #423 (B-03): подписка на payment_succeeded/failed для confirm/release резерва.
        from . import receivers

        receivers.connect()
