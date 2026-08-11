from django.db.models import Count
from apps.catalog.models import CatalogChange, CatalogProcessingRun

print("changes_by_status", list(CatalogChange.objects.values("status").annotate(n=Count("pk"))))
print(
    "changes_by_status_target",
    list(CatalogChange.objects.values("status", "target_kind").annotate(n=Count("pk"))),
)
print(
    "runs",
    list(
        CatalogProcessingRun.objects.values("pk", "kind", "mode", "status").order_by("created_at")
    ),
)
