from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    verbose_name = "Каталог товаров"

    def ready(self):
        from . import signals  # noqa: F401  — подключение сигналов attrs_cache
