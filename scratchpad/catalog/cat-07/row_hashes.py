# -*- coding: utf-8 -*-
"""CAT-07: построчные мини-хэши PAV и attrs_cache для диффа. READ-ONLY."""
import hashlib
import io
import json
import os

from apps.catalog.models import Product, ProductAttributeValue as PAV

out = {"pav": [], "cache": []}
for v in (
    PAV.objects.order_by("product_id", "attribute__slug").values_list(
        "id", "product_id", "attribute__slug", "value_text", "value_integer",
        "value_decimal", "value_boolean", "value_option__slug", "source", "confidence",
    )
):
    row = json.dumps([str(x) for x in v[1:]], ensure_ascii=False)
    out["pav"].append([v[0], hashlib.md5(row.encode()).hexdigest()[:12]])

for pid, cache in Product.objects.order_by("id").values_list("id", "attrs_cache"):
    row = json.dumps(cache, sort_keys=True, ensure_ascii=False, default=str)
    out["cache"].append([pid, hashlib.md5(row.encode()).hexdigest()[:12]])

OUT = os.environ.get("CAT07_OUT", "/tmp/cat07_rows.json")
io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False))
print("WROTE", OUT, len(out["pav"]), len(out["cache"]))
