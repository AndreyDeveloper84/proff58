from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Покупатели"

    def ready(self):
        # Ресивер user_logged_in: любой вход ставит отметку «личность подтверждена» (DRF-2497).
        from . import reauth  # noqa: F401
