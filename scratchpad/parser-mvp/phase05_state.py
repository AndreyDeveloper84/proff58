# -*- coding: utf-8 -*-
"""Phase 0.5 read-only: состояние attrs_cache, атрибутов cat=3, фасетов. НИЧЕГО НЕ ПИШЕТ."""
import json
from collections import Counter

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    CategoryAttribute,
    Product,
    ProductAttributeValue,
    ImportRun,
)

TT = "perforatory"
pids = list(
    ProductAttributeValue.objects.filter(
        attribute__slug="tool_type", value_option__slug=TT
    ).values_list("product_id", flat=True)
)

cache_keys = Counter()
cache_only_tt = 0
cats = Counter()
pub = 0
for p in Product.objects.filter(id__in=pids).only(
    "id", "attrs_cache", "category_id", "status", "is_active", "content_locked"
):
    c = p.attrs_cache or {}
    for k in c:
        cache_keys[k] += 1
    if set(c) <= {"tool_type"}:
        cache_only_tt += 1
    cats[p.category_id] += 1
    pub += int(p.status == "published" and p.is_active)

ca = [
    {
        "slug": ca.attribute.slug,
        "name": ca.attribute.name,
        "type": ca.attribute.attribute_type,
        "unit": ca.attribute.unit,
        "is_filter": ca.is_filter,
        "facet": ca.is_seo_facet,
        "filterable": ca.attribute.is_filterable,
    }
    for ca in CategoryAttribute.objects.filter(category_id=3).select_related("attribute")
]

attrs = [
    {"slug": a.slug, "name": a.name, "type": a.attribute_type, "unit": a.unit,
     "filterable": a.is_filterable}
    for a in Attribute.objects.filter(
        slug__in=[
            "power",
            "chuck",
            "energy_impact",
            "no_load_speed",
            "voltage",
            "power_source",
            "motor_type",
            "battery_capacity",
            "battery_included",
        ]
    )
]

opts = {
    a: sorted(
        AttributeOption.objects.filter(attribute__slug=a).values_list("slug", flat=True)
    )
    for a in ["chuck", "power_source", "motor_type"]
}

runs = [
    {"id": r.id, "src": r.source, "at": str(r.started_at), "status": r.status, "stats": r.stats}
    for r in ImportRun.objects.filter(source="enrich_attributes").order_by("-id")[:3]
]

print("===JSON===")
print(
    json.dumps(
        {
            "n": len(pids),
            "published": pub,
            "categories": dict(cats),
            "cache_keys": dict(cache_keys),
            "cache_only_tool_type": cache_only_tt,
            "cat3_attributes": ca,
            "attributes_exist": attrs,
            "options": opts,
            "recent_enrich_runs": runs,
        },
        ensure_ascii=False,
        default=str,
    )
)
print("===END===")
