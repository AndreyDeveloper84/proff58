"""Массовая пересборка Product.attrs_cache (бэкафилл существующих товаров)."""

from django.core.management.base import BaseCommand

from apps.catalog.models import Product
from apps.catalog.services import rebuild_attrs_cache


class Command(BaseCommand):
    help = "Пересобрать attrs_cache по всем товарам из EAV-значений."

    def handle(self, *args, **options):
        count = 0
        for product in Product.objects.all().iterator():
            rebuild_attrs_cache(product)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Пересобрано attrs_cache: {count}"))
