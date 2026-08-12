# -*- coding: utf-8 -*-
"""CAT-06 · задача 2: выборка названий по tool_type-кандидатам. READ-ONLY."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402

TTS = [
    "svar-electrody",
    "str-valiki",
    "str-shpateli",
    "zap-podshipniki",
    "hoz-lopaty",
    "bp-cepi",
    "str-kisti",
    "zap-shchetki-ugolnye",
]

out = {}
for tt in TTS:
    pids = PAV.objects.filter(
        attribute__slug="tool_type",
        value_option__slug=tt,
        product__is_active=True,
        product__status="published",
    ).values_list("product_id", flat=True)
    names = list(
        Product.objects.filter(id__in=pids)
        .order_by("id")
        .values_list("original_name", "name")[:50]
    )
    out[tt] = {"n_pub": len(pids), "sample": [(o or n)[:100] for o, n in names]}
print(json.dumps(out, ensure_ascii=False, indent=1))
