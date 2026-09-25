from django.core.management.base import BaseCommand, CommandError

from ...services import source_content


class Command(BaseCommand):
    help = "Поиск внешнего контента для одного товара"

    def add_arguments(self, parser):
        parser.add_argument("--id", type=int)
        parser.add_argument("--article", type=str)
        parser.add_argument(
            "--dry-run", action="store_true", help="без платных вызовов — только показать план"
        )

    def handle(self, *args, **o):
        from apps.catalog.models import Product

        if o.get("id") is not None:
            product = Product.objects.filter(pk=o["id"]).first()
        elif o.get("article"):
            product = Product.objects.filter(article=o["article"]).first()
        else:
            raise CommandError("укажите --id или --article")
        if product is None:
            raise CommandError("товар не найден")
        if o["dry_run"]:
            self.stdout.write(
                f"dry-run: искали бы контент для #{product.pk} "
                f"'{product.original_name}'. Платных вызовов нет."
            )
            return
        run = source_content(product_id=product.pk, idempotency_key=f"cli:{product.pk}")
        self.stdout.write(f"run={run.idempotency_key} status={run.status}")
