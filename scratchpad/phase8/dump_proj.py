import json
from apps.catalog.models import Product
out = []
for p in Product.objects.order_by("pk").values(
    "pk", "code_1c", "article", "name", "category_id",
    "price", "stock_quantity", "status", "is_active",
):
    out.append([p["pk"], p["code_1c"] or "", p["article"] or "", p["name"] or "",
                p["category_id"], str(p["price"]), str(p["stock_quantity"]),
                p["status"], p["is_active"]])
print(json.dumps(out, ensure_ascii=False))
