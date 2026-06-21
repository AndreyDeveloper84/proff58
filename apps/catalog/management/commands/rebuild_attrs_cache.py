"""Массовая пересборка Product.attrs_cache (бэкафилл существующих товаров).

Батч чанками по id: для каждого чанка делается локальный prefetch EAV-значений и
один ``bulk_update`` — без prefetch всего каталога и без N+1. Содержимое кэша
идентично одиночному :func:`apps.catalog.read_models.rebuild_attrs_cache`.
"""

from django.core.management.base import BaseCommand

from apps.catalog.models import Product
from apps.catalog.read_models import build_attrs_cache

BATCH_SIZE = 500


class Command(BaseCommand):
    help = "Пересобрать attrs_cache по всем товарам из EAV-значений (батч чанками)."

    def handle(self, *args, **options):
        ids = list(Product.objects.order_by("id").values_list("id", flat=True))
        count = 0
        for start in range(0, len(ids), BATCH_SIZE):
            chunk = ids[start : start + BATCH_SIZE]
            # Локальный prefetch ТОЛЬКО по чанку — не по всему каталогу.
            products = list(
                Product.objects.filter(id__in=chunk).prefetch_related(
                    "attribute_values__attribute",
                    "attribute_values__value_option",
                )
            )
            for product in products:
                product.attrs_cache = build_attrs_cache(product)
            Product.objects.bulk_update(products, ["attrs_cache"], batch_size=BATCH_SIZE)
            count += len(products)
        self.stdout.write(self.style.SUCCESS(f"Пересобрано attrs_cache: {count}"))
