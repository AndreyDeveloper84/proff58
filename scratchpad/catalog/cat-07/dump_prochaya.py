# -*- coding: utf-8 -*-
"""CAT-07: выгрузка prochaya-osnastka (id, pub, имя, категория). READ-ONLY."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402

pids = PAV.objects.filter(
    attribute__slug="tool_type", value_option__slug="prochaya-osnastka"
).values_list("product_id", flat=True)
rows = []
for p in (
    Product.objects.filter(id__in=pids)
    .select_related("category")
    .order_by("id")
):
    rows.append(
        {
            "pid": p.id,
            "pub": p.is_active and p.status == "published",
            "name": (p.original_name or p.name)[:120],
            "cat": p.category.slug if p.category else None,
            "cat_id": p.category_id,
            "cat_name": p.category.name if p.category else None,
        }
    )
print(json.dumps(rows, ensure_ascii=False))
