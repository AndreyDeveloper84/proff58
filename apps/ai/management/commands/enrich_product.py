from django.core.management.base import BaseCommand, CommandError

from apps.catalog.enrichment import get_enrichable_product

from ...services import enrich


class Command(BaseCommand):
    help = "Обогатить конкретный товар (для отладки)"

    def add_arguments(self, parser):
        parser.add_argument("--id", type=int)
        parser.add_argument("--article", type=str)
        parser.add_argument("--code-1c", type=str, dest="code_1c")
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--verbose", action="store_true")

    def handle(self, *args, **o):
        from apps.catalog.models import Product

        if o.get("id") is not None:
            product = get_enrichable_product(o["id"])
        elif o.get("article"):
            product = Product.objects.filter(article=o["article"]).first()
        elif o.get("code_1c"):
            product = Product.objects.filter(code_1c=o["code_1c"]).first()
        else:
            raise CommandError("укажите --id / --article / --code-1c")
        if product is None:
            raise CommandError("товар не найден")
        result = enrich(product_id=product.pk, force=o["force"])
        self.stdout.write(f"source={result.source} confidence={result.confidence}")
        if o["verbose"]:
            self.stdout.write(f"name={result.name!r}\ndesc={result.description!r}")
