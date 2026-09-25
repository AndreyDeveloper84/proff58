# Task 6 Step 3 (taxonomy export) + Task 5/7 post-check инвариантов §4.
# READ-ONLY: один SELECT-пакет + запись export-файла в /app/logs/.
import json
import urllib.request

from django.conf import settings

from apps.ai.models import ContentFinding
from apps.catalog.models import (
    AttributeOption,
    CatalogChange,
    CatalogProcessingItem,
    CatalogProcessingRun,
    Product,
    ProductAttributeValue,
)
from apps.catalog.queue_contract import _allowed_tool_type_options, _taxonomy_hash

opts = _allowed_tool_type_options()
payload = {"options": opts, "taxonomy_hash": _taxonomy_hash(opts), "count": len(opts)}
with open("/app/logs/tool_type_options_export.json", "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
print("options_exported", len(opts))
print("taxonomy_hash", _taxonomy_hash(opts))

# --- post-инварианты §4 (сверка с pre-базовой линией Stage 0) ---
print("pav_total", ProductAttributeValue.objects.count())
print("options", AttributeOption.objects.filter(attribute__slug="tool_type").count())
print("changes_total", CatalogChange.objects.count())
print("applied_tt", CatalogChange.objects.filter(status="applied", target_kind="tool_type").count())
print("non_final", CatalogChange.objects.filter(status__in=["proposed", "approved"]).count())
print("runs_total", CatalogProcessingRun.objects.count())
print("items_total", CatalogProcessingItem.objects.count())
print("products", Product.objects.count())
print("findings", ContentFinding.objects.count())
print("batch50", CatalogProcessingRun.objects.get(pk="aa9b1df5-41c5-4b10-a6d8-957c2ff57aa9").status)
print("remediation", CatalogProcessingRun.objects.get(pk="3afffd16-005a-4f73-95fd-d068aa725391").status)
print("feature_flag", getattr(settings, "FEATURES", {}).get("catalog_processing"))

urllib.request.urlopen("http://localhost:8000/healthz/")
print("healthz 200")
