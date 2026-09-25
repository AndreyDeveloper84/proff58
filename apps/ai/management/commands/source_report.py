from django.core.management.base import BaseCommand
from django.db.models import Count, Sum

from ...models import ContentFinding, ExternalCall


class Command(BaseCommand):
    help = "Отчёт по находкам внешнего контента"

    def handle(self, *args, **o):
        self.stdout.write("Находки по статусам:")
        for row in (
            ContentFinding.objects.values("status").annotate(n=Count("id")).order_by("status")
        ):
            self.stdout.write(f"  {row['status']}: {row['n']}")
        self.stdout.write("По источникам (pending):")
        for row in (
            ContentFinding.objects.filter(status="pending")
            .values("source_name")
            .annotate(n=Count("id"))
        ):
            self.stdout.write(f"  {row['source_name']}: {row['n']}")
        cost = ExternalCall.objects.aggregate(s=Sum("cost"))["s"] or 0
        self.stdout.write(f"Суммарная стоимость вызовов: {cost}")
