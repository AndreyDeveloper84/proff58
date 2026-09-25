# -*- coding: utf-8 -*-
"""CAT-02 read-only: образец работающего раздела + карта CategoryAttribute по каталогу."""
import io
import json
import os

from apps.catalog.models import Category, CategoryAttribute, Product

out = {}
# --- 1. Все категории, у которых ЕСТЬ CategoryAttribute (кто и как настроен) ---
rows = []
for ca in CategoryAttribute.objects.select_related("category", "attribute").order_by(
    "category__slug", "sort_order"
):
    rows.append(
        {
            "cat_id": ca.category_id,
            "cat_slug": ca.category.slug,
            "cat_name": ca.category.name,
            "cat_depth": ca.category.depth,
            "attr": ca.attribute.slug,
            "attr_name": ca.attribute.name,
            "attr_type": ca.attribute.attribute_type,
            "is_filterable": ca.attribute.is_filterable,
            "is_filter": ca.is_filter,
            "group": ca.group,
            "sort": ca.sort_order,
            "seo": ca.is_seo_facet,
        }
    )
out["all_category_attributes"] = rows
out["total_ca"] = len(rows)

# --- 2. Разрез: сколько CA на категорию ---
per_cat = {}
for r in rows:
    per_cat.setdefault(r["cat_slug"], []).append(r["attr"])
out["per_category"] = {k: v for k, v in sorted(per_cat.items(), key=lambda x: -len(x[1]))}

# --- 3. Образец: elektroinstrument и его потомки ---
ref = []
for slug in ("elektroinstrument", "ruchnoy-instrument", "ruchnoy"):
    c = Category.objects.filter(slug=slug).first()
    if c is None:
        continue
    nodes = [c, *c.get_descendants()]
    for n in nodes:
        cas = list(n.category_attributes.select_related("attribute").order_by("sort_order"))
        if not cas:
            continue
        sub = [n.pk, *n.get_descendants().values_list("pk", flat=True)]
        ref.append(
            {
                "root": slug,
                "slug": n.slug,
                "name": n.name,
                "depth": n.depth,
                "products": Product.objects.filter(category_id__in=sub).count(),
                "ca": [
                    {
                        "attr": ca.attribute.slug,
                        "type": ca.attribute.attribute_type,
                        "is_filter": ca.is_filter,
                        "group": ca.group,
                        "sort": ca.sort_order,
                        "seo": ca.is_seo_facet,
                    }
                    for ca in cas
                ],
            }
        )
out["reference_sections"] = ref

OUT = os.environ.get("CAT02_OUT", "/tmp/cat02_ref.json")
io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, default=str))
print("WROTE", OUT, "total_ca=", out["total_ca"])
