# -*- coding: utf-8 -*-
"""CAT-02 read-only: покрытие атрибутов ПО КАЖДОЙ категории izmeritelnyy/*.

Считает по attrs_cache (то, из чего build_facets реально строит панель) и по EAV,
чтобы поймать рассинхрон. Ничего не пишет.
"""
import io
import json
import os

from django.db.models import Count, Q

from apps.catalog.models import Category, Product, ProductAttributeValue as PAV

CAND = [
    "tape_length",
    "tape_width",
    "length",
    "level_type",
    "max_distance",
    "measuring_range",
    "readout_type",
    "size",
]

out = {}
root = Category.objects.get(slug="izmeritelnyy")
nodes = [root, *root.get_descendants()]
res = []
for c in nodes:
    sub = [c.pk, *c.get_descendants().values_list("pk", flat=True)]
    qs = Product.objects.filter(category_id__in=sub)
    qs_pub = qs.filter(is_active=True, status="published")
    row = {
        "slug": c.slug,
        "name": c.name,
        "depth": c.depth,
        "products": qs.count(),
        "published": qs_pub.count(),
        "attrs": {},
    }
    for a in CAND:
        eav = PAV.objects.filter(product__category_id__in=sub, attribute__slug=a).aggregate(
            n=Count("id"),
            npub=Count("id", filter=Q(product__is_active=True, product__status="published")),
        )
        cache_n = qs.filter(attrs_cache__has_key=a).count()
        cache_pub = qs_pub.filter(attrs_cache__has_key=a).count()
        distinct_pub = (
            qs_pub.filter(attrs_cache__has_key=a).values_list("attrs_cache__" + a, flat=True)
            if False
            else None
        )
        vals = set()
        for v in qs_pub.filter(attrs_cache__has_key=a).values_list("attrs_cache", flat=True):
            vals.add(str(v.get(a)))
        row["attrs"][a] = {
            "eav": eav["n"],
            "eav_pub": eav["npub"],
            "cache": cache_n,
            "cache_pub": cache_pub,
            "distinct_pub": len(vals),
        }
    res.append(row)
out["per_category"] = res

OUT = os.environ.get("CAT02_OUT", "/tmp/cat02_cov.json")
io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, default=str))
print("WROTE", OUT)
