# -*- coding: utf-8 -*-
"""CAT-09 S3 recon: что лежит в yashchiki-sumki сейчас. READ-ONLY."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402

pids = PAV.objects.filter(
    attribute__slug="tool_type", value_option__slug="yashchiki-sumki"
).values_list("product_id", flat=True)
rows = list(
    Product.objects.filter(id__in=pids)
    .order_by("id")
    .values("id", "name", "is_active", "status", "category_id")
)
# частоты первых слов — состав типа
from collections import Counter  # noqa: E402

first = Counter(r["name"].split()[0].lower() for r in rows if r["name"])
print(json.dumps({
    "total": len(rows),
    "pub": sum(1 for r in rows if r["is_active"] and r["status"] == "published"),
    "first_words": first.most_common(25),
    "sample_musor": [r["name"][:90] for r in rows if "мусор" in r["name"].lower()][:10],
    "sample_names": [r["name"][:90] for r in rows[:40]],
}, ensure_ascii=False))
