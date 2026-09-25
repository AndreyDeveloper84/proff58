# -*- coding: utf-8 -*-
"""CAT-08 · корректировка 9 имён «яяЯ-слово» (корь/щик → Якорь/Ящик). Одна транзакция."""
import json
import os
import sys

sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from django.db import transaction  # noqa: E402

from apps.catalog.models import Product  # noqa: E402

fix = json.load(open(os.environ.get("CAT08_FIX", "/tmp/cat08_fix_map.json"), encoding="utf-8"))
print("к исправлению:", len(fix))
with transaction.atomic():
    products = {p.id: p for p in Product.objects.filter(id__in=[f["pid"] for f in fix])}
    assert len(products) == len(fix), "не все товары найдены — стоп"
    for f in fix:
        p = products[f["pid"]]
        assert p.name == f["wrong"], f"pid {f['pid']}: текущее {p.name!r} != {f['wrong']!r} — стоп"
        p.name = f["correct"]
    Product.objects.bulk_update(products.values(), ["name"])
for f in fix:
    print("  FIXED", f["pid"], "->", f["correct"][:60])
print("WROTE 9")
