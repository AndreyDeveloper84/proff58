from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.catalog.models import ContentSource, EnrichStatus, Product


class Command(BaseCommand):
    help = "Отчёт по статусам обогащения"

    def handle(self, *args, **o):
        total = Product.objects.count() or 1
        self.stdout.write(f"Всего товаров: {total}")
        by_status = dict(
            Product.objects.values_list("enrich_status")
            .annotate(n=Count("id"))
            .values_list("enrich_status", "n")
        )
        for status in EnrichStatus:
            n = by_status.get(status.value, 0)
            self.stdout.write(f"  {status.label}: {n} ({100 * n // total}%)")
        self.stdout.write("Источники готовых:")
        for src in ContentSource.values:
            n = Product.objects.filter(content_source=src, enrich_status=EnrichStatus.DONE).count()
            self.stdout.write(f"  {src}: {n}")
        self.stdout.write(f"Без описания: {Product.objects.filter(description='').count()}")
