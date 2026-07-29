# -*- coding: utf-8 -*-
"""CAT-02: независимые счётчики по БД для сверки с живым API. READ-ONLY."""
import io
import json
import os

from django.db.models import Count
from django.db.models.fields.json import KeyTextTransform

from apps.catalog.filters import visible_products
from apps.catalog.models import Category

TARGETS = {
    "izmeritelnyy-ruletki": ["tape_length", "tape_width"],
    "izmeritelnyy-urovni": ["length"],
    "izmeritelnyy-shtangencirkuli-i-mikrometry": ["measuring_range", "readout_type"],
    "izmeritelnyy-ugolniki-i-lineyki": ["size"],
    "izmeritelnyy-dalnomery": ["max_distance"],
    "izmeritelnyy-lazernye-urovni-i-niveliry": ["level_type"],
    "izmeritelnyy-uglomery-i-uklonomery": ["size"],
}
RANGES = [
    ("izmeritelnyy-urovni", "length", 1000),
    ("izmeritelnyy-ruletki", "tape_length", 5),
    ("izmeritelnyy-ugolniki-i-lineyki", "size", 300),
]

out = {}
for cat_slug, attrs in TARGETS.items():
    cat = Category.objects.get(slug=cat_slug)
    ids = [cat.pk, *cat.get_descendants().values_list("pk", flat=True)]
    base = visible_products().filter(category_id__in=ids)
    e = {"published_total": base.count(), "attrs": {}}
    for a in attrs:
        rows = (
            base.annotate(_fv=KeyTextTransform(a, "attrs_cache"))
            .filter(_fv__isnull=False)
            .values("_fv")
            .annotate(c=Count("id"))
        )
        e["attrs"][a] = {r["_fv"]: r["c"] for r in rows}
    out[cat_slug] = e

rng = {}
for cat_slug, attr, lo in RANGES:
    cat = Category.objects.get(slug=cat_slug)
    ids = [cat.pk, *cat.get_descendants().values_list("pk", flat=True)]
    base = visible_products().filter(category_id__in=ids)
    n = 0
    for v in base.filter(attrs_cache__has_key=attr).values_list("attrs_cache", flat=True):
        try:
            if float(v.get(attr)) >= lo:
                n += 1
        except (TypeError, ValueError):
            pass
    rng[f"{cat_slug}|{attr}|{lo}"] = {"published_total": base.count(), "ge": n}
out["_ranges"] = rng

OUT = os.environ.get("CAT02_OUT", "/tmp/cat02_dbcounts.json")
io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, default=str))
print("WROTE", OUT)
