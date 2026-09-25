# -*- coding: utf-8 -*-
"""CAT-05: предсказание панелей krugi — те же счётчики, что даст build_facets. READ-ONLY.

visible_products() + GROUP BY attrs_cache по каждому из 3 атрибутов.
Вывод — JSON в $CAT05_OUT.
"""
import io
import json
import os

from django.db.models import Count
from django.db.models.fields.json import KeyTextTransform

from apps.catalog.filters import visible_products
from apps.catalog.models import Category

ATTRS = ["disc_diameter", "bore", "disc_type"]

out = {}
c = Category.objects.get(slug="krugi")
ids = [c.pk, *c.get_descendants().values_list("pk", flat=True)]
base = visible_products().filter(category_id__in=ids)
out["published_total"] = base.count()
for a in ATTRS:
    rows = (
        base.annotate(_fv=KeyTextTransform(a, "attrs_cache"))
        .filter(_fv__isnull=False)
        .values("_fv")
        .annotate(c=Count("id"))
    )
    vals = sorted(((r["_fv"], r["c"]) for r in rows), key=lambda t: t[0])
    out[a] = {
        "products_with_attr": sum(n for _, n in vals),
        "distinct_values": len(vals),
        "values": vals,
    }

OUT = os.environ.get("CAT05_OUT", "/tmp/cat05_predict.json")
io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, default=str))
print("WROTE", OUT)
