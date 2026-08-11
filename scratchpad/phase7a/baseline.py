from apps.catalog.models import (
    AttributeOption,
    CatalogChange,
    CatalogProcessingRun,
    Product,
    ProductAttributeValue,
)
from apps.ai.models import ContentFinding

print("pav_total", ProductAttributeValue.objects.count())
print("options", AttributeOption.objects.filter(attribute__slug="tool_type").count())
qs = CatalogChange.objects.filter(status="applied", target_kind="tool_type")
print("raw_applied", qs.count())
print("distinct_products", qs.values("product_ref").distinct().count())
print(
    "non_final",
    CatalogChange.objects.filter(status__in=["proposed", "approved"]).count(),
)
print("products", Product.objects.count())
print("changes_total", CatalogChange.objects.count())
print("runs_total", CatalogProcessingRun.objects.count())
print(
    "batch50",
    CatalogProcessingRun.objects.get(pk="aa9b1df5-41c5-4b10-a6d8-957c2ff57aa9").status,
)
print(
    "remediation",
    CatalogProcessingRun.objects.get(pk="3afffd16-005a-4f73-95fd-d068aa725391").status,
)
print("findings", ContentFinding.objects.count())
