# -*- coding: utf-8 -*-
"""CAT-02 read-only: что заведено в izmeritelnyy/* и какое покрытие атрибутов.

Печатает JSON между ===JSON=== и ===END===. Ничего не пишет.
"""
import json

from apps.catalog.models import (
    Attribute,
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue as PAV,
)

out = {}

# --- 1. Дерево izmeritelnyy ---
root = Category.objects.filter(slug="izmeritelnyy").first()
if root is None:
    root = Category.objects.filter(slug__startswith="izmeritel").first()
tree = []
if root is not None:
    nodes = [root, *root.get_descendants()]
    for c in nodes:
        sub = [c.pk, *c.get_descendants().values_list("pk", flat=True)]
        tree.append(
            {
                "id": c.pk,
                "slug": c.slug,
                "name": c.name,
                "depth": c.depth,
                "is_active": c.is_active,
                "on_site": getattr(c, "on_site", None),
                "is_site_v2": getattr(c, "is_site_v2", None),
                "products": Product.objects.filter(category_id__in=sub).count(),
                "published": Product.objects.filter(
                    category_id__in=sub, is_active=True, status="published"
                ).count(),
                "own_products": Product.objects.filter(category_id=c.pk).count(),
                "cat_attrs": [
                    {
                        "attr": ca.attribute.slug,
                        "is_filter": ca.is_filter,
                        "group": ca.group,
                        "sort": ca.sort_order,
                        "seo": ca.is_seo_facet,
                    }
                    for ca in c.category_attributes.select_related("attribute").order_by(
                        "sort_order"
                    )
                ],
            }
        )
out["tree"] = tree
out["root"] = {"id": root.pk, "slug": root.slug, "name": root.name} if root else None

# --- 2. Предки корня (наследование фасетов сверху) ---
if root is not None:
    anc = []
    for c in root.get_ancestors():
        anc.append(
            {
                "id": c.pk,
                "slug": c.slug,
                "name": c.name,
                "cat_attrs": [
                    ca.attribute.slug for ca in c.category_attributes.select_related("attribute")
                ],
            }
        )
    out["ancestors"] = anc

# --- 3. Покрытие атрибутов по товарам поддерева izmeritelnyy ---
if root is not None:
    sub_ids = [root.pk, *root.get_descendants().values_list("pk", flat=True)]
    total = Product.objects.filter(category_id__in=sub_ids).count()
    total_pub = Product.objects.filter(
        category_id__in=sub_ids, is_active=True, status="published"
    ).count()
    out["subtree_totals"] = {"products": total, "published": total_pub}

    cov = {}
    rows = (
        PAV.objects.filter(product__category_id__in=sub_ids)
        .values("attribute__slug", "attribute__name", "attribute__attribute_type",
                "attribute__is_filterable", "attribute__unit")
        .order_by()
    )
    from django.db.models import Count, Q

    rows = rows.annotate(
        n=Count("id"),
        n_pub=Count("id", filter=Q(product__is_active=True, product__status="published")),
    )
    for r in rows:
        cov[r["attribute__slug"]] = {
            "name": r["attribute__name"],
            "type": r["attribute__attribute_type"],
            "is_filterable": r["attribute__is_filterable"],
            "unit": r["attribute__unit"],
            "n": r["n"],
            "n_pub": r["n_pub"],
        }
    out["coverage_subtree"] = cov

# --- 4. Покрытие по tool_type (типы измерительного) ---
tt_slugs = list(
    PAV.objects.filter(
        attribute__slug="tool_type",
        product__category_id__in=(sub_ids if root else []),
        value_option__isnull=False,
    )
    .values_list("value_option__slug", flat=True)
    .distinct()
)
out["tool_types_in_subtree"] = sorted(tt_slugs)

by_tt = {}
for tt in tt_slugs:
    pids = list(
        PAV.objects.filter(attribute__slug="tool_type", value_option__slug=tt).values_list(
            "product_id", flat=True
        )
    )
    n_tt = len(pids)
    n_tt_pub = Product.objects.filter(
        id__in=pids, is_active=True, status="published"
    ).count()
    attrs = {}
    from django.db.models import Count, Q

    for r in (
        PAV.objects.filter(product_id__in=pids)
        .exclude(attribute__slug="tool_type")
        .values("attribute__slug")
        .annotate(
            n=Count("id"),
            n_pub=Count("id", filter=Q(product__is_active=True, product__status="published")),
        )
    ):
        attrs[r["attribute__slug"]] = {"n": r["n"], "pub": r["n_pub"]}
    by_tt[tt] = {"products": n_tt, "published": n_tt_pub, "attrs": attrs}
out["by_tool_type"] = by_tt

import io,os
OUT=os.environ.get("CAT02_OUT","/tmp/cat02_out.json")
io.open(OUT,"w",encoding="utf-8").write(json.dumps(out,ensure_ascii=False,default=str))
print("WROTE",OUT)
print("===JSON===")
print(json.dumps(out, ensure_ascii=False, default=str))
print("===END===")
