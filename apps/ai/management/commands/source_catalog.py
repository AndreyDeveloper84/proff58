from django.core.management.base import BaseCommand, CommandError

from apps.catalog.enrichment import pending_for_enrichment

from ...services import source_content


class Command(BaseCommand):
    help = "Батч-поиск внешнего контента (приоритет available_quantity > 0)"

    def add_arguments(self, parser):
        parser.add_argument("--category", type=str)
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--commit", action="store_true")

    def handle(self, *args, **o):
        if not o["category"] and not o["all"]:
            raise CommandError("укажите --category SLUG или --all")
        ids = pending_for_enrichment(category_slug=o["category"], limit=o["limit"])
        self.stdout.write(f"К обработке: {len(ids)}")
        if not o["commit"]:
            self.stdout.write("dry-run — добавьте --commit для реальных вызовов")
            return
        for pid in ids:
            source_content(product_id=pid, idempotency_key=f"cli-batch:{pid}")
        self.stdout.write(self.style.SUCCESS(f"Обработано: {len(ids)}"))
