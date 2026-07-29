# -*- coding: utf-8 -*-
"""CAT-06 · задача 1: read-only разбор трёх скрытых товаров. Ничего не пишет."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402

out = []
for pid in (44507, 44538, 44540):
    p = Product.objects.filter(id=pid).first()
    if p is None:
        out.append({"pid": pid, "exists": False})
        continue
    pavs = list(
        PAV.objects.filter(product=p).select_related("attribute", "value_option").order_by(
            "attribute__slug"
        )
    )
    attrs = {}
    for pav in pavs:
        if pav.value_option:
            v = pav.value_option.value
        elif pav.value_decimal is not None:
            v = str(pav.value_decimal)
        elif pav.value_integer is not None:
            v = str(pav.value_integer)
        elif pav.value_boolean is not None:
            v = pav.value_boolean
        else:
            v = pav.value_text
        attrs[pav.attribute.slug] = {"value": v, "source": pav.source}
    out.append(
        {
            "pid": pid,
            "exists": True,
            "name": p.name,
            "original_name": p.original_name,
            "slug": p.slug,
            "is_active": p.is_active,
            "status": p.status,
            "category": p.category.slug if p.category else None,
            "price": str(p.price),
            "stock_quantity": str(p.stock_quantity),
            "stock_status": p.stock_status,
            "brand": p.brand,
            "content_locked": p.content_locked,
            "category_is_manual": p.category_is_manual,
            "n_images": p.images.count(),
            "description": bool(p.description),
            "attrs": attrs,
        }
    )
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
