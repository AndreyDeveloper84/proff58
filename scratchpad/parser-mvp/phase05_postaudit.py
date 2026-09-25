# -*- coding: utf-8 -*-
"""Phase 0.5 post-audit (read-only): покрытие, дубли PAV, attrs_cache == EAV."""
import json
from collections import Counter

from apps.catalog.models import Product, ProductAttributeValue
from apps.catalog.read_models import build_attrs_cache
from django.db.models import Count

TT = "perforatory"
MANAGED = [
    "power", "energy_impact", "chuck", "no_load_speed", "voltage",
    "power_source", "motor_type", "battery_capacity", "battery_included",
]

pids = sorted(
    ProductAttributeValue.objects.filter(
        attribute__slug="tool_type", value_option__slug=TT
    ).values_list("product_id", flat=True)
)

cov = Counter()
by_source = Counter()
for pav in ProductAttributeValue.objects.filter(
    product_id__in=pids, attribute__slug__in=MANAGED
).select_related("attribute"):
    cov[pav.attribute.slug] += 1
    by_source[pav.source] += 1

dups = list(
    ProductAttributeValue.objects.filter(product_id__in=pids)
    .values("product_id", "attribute_id")
    .annotate(n=Count("id"))
    .filter(n__gt=1)[:20]
)

mismatch = []
n_attrs = Counter()
for p in Product.objects.filter(id__in=pids).prefetch_related(
    "attribute_values__attribute", "attribute_values__value_option"
):
    expected = build_attrs_cache(p)
    if (p.attrs_cache or {}) != expected:
        mismatch.append(p.id)
    n_attrs[len([k for k in (p.attrs_cache or {}) if k != "tool_type"])] += 1

manual = list(
    ProductAttributeValue.objects.filter(product_id__in=pids, source="manual").values_list(
        "product_id", "attribute__slug"
    )
)

# распределение значений для фасетов
chuck_dist = Counter(
    ProductAttributeValue.objects.filter(
        product_id__in=pids, attribute__slug="chuck"
    ).values_list("value_option__slug", flat=True)
)
ps_dist = Counter(
    ProductAttributeValue.objects.filter(
        product_id__in=pids, attribute__slug="power_source"
    ).values_list("value_option__slug", flat=True)
)

print("===JSON===")
print(
    json.dumps(
        {
            "scope": len(pids),
            "coverage_after": {k: cov[k] for k in MANAGED},
            "pav_by_source": dict(by_source),
            "duplicate_pav": dups,
            "attrs_cache_mismatch": mismatch,
            "attrs_per_product_hist": dict(sorted(n_attrs.items())),
            "manual_values": manual,
            "chuck_distribution": dict(chuck_dist),
            "power_source_distribution": dict(ps_dist),
        },
        ensure_ascii=False,
        default=str,
    )
)
print("===END===")
