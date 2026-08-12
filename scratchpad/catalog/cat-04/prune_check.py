# -*- coding: utf-8 -*-
"""CAT-04: сверка PRUNE=17 — имена товаров и текущие значения PAV. READ-ONLY."""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402

plan = json.load(open("/tmp/cat04_plan.json", encoding="utf-8"))
rows = []
for it in plan["plan"]["prune"]:
    p = Product.objects.get(id=it["pid"])
    pav = PAV.objects.get(product_id=it["pid"], attribute__slug=it["attr"])
    val = pav.value_decimal if pav.value_decimal is not None else (
        pav.value_option.slug if pav.value_option else pav.value_text
    )
    rows.append(
        {
            "pid": it["pid"],
            "tt": it["tt"],
            "attr": it["attr"],
            "db_value": str(val),
            "db_source": pav.source,
            "pub": it["pub"],
            "name": (p.original_name or p.name)[:90],
        }
    )
print(json.dumps(rows, ensure_ascii=False, indent=1))
