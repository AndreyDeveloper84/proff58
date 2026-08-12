# -*- coding: utf-8 -*-
"""CAT-06 · задача 2: полные списки названий 3 типов-кандидатов. READ-ONLY."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402

TTS = ["svar-electrody", "str-valiki", "str-kisti"]

out = {}
for tt in TTS:
    rows = []
    pav_qs = PAV.objects.filter(
        attribute__slug="tool_type", value_option__slug=tt
    ).values_list("product_id", flat=True)
    for p in Product.objects.filter(id__in=pav_qs).order_by("id"):
        rows.append(
            {
                "pid": p.id,
                "pub": p.is_active and p.status == "published",
                "name": (p.original_name or p.name)[:120],
            }
        )
    out[tt] = rows
print(json.dumps(out, ensure_ascii=False, indent=1))
