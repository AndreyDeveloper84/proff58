# -*- coding: utf-8 -*-
"""CAT-01: выгрузка всех значений length (izm-urovni) и size (izm-ugolniki) со staging.
Read-only. Вывод: JSON между ===JSON=== и ===END===."""
import json

from apps.catalog.models import Product, ProductAttributeValue as PAV

out = {}
for tt, attr in (("izm-urovni", "length"), ("izm-ugolniki", "size")):
    pids = list(
        PAV.objects.filter(attribute__slug="tool_type", value_option__slug=tt)
        .values_list("product_id", flat=True)
    )
    prods = {p.id: p for p in Product.objects.filter(id__in=pids)}
    rows = []
    for pav in (
        PAV.objects.filter(product_id__in=pids, attribute__slug=attr)
        .order_by("product_id")
    ):
        p = prods[pav.product_id]
        rows.append({
            "pid": pav.product_id,
            "name": p.original_name or p.name,
            "val": str(pav.value_decimal),
            "source": pav.source,
            "pub": p.status == "published" and p.is_active,
        })
    out[f"{tt}|{attr}"] = {"products": len(pids), "rows": rows}

print("===JSON===")
print(json.dumps(out, ensure_ascii=False))
print("===END===")
