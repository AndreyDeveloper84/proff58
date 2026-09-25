# -*- coding: utf-8 -*-
"""Phase 0.5: проверка фасетов и фильтрации на витринном API (read-only)."""
import json

from django.test import Client

c = Client(SERVER_NAME="dev.proff58.ru", secure=True)


def g(url):
    r = c.get(url, follow=True)
    return r.status_code, (json.loads(r.content.decode()) if r.status_code == 200 else r.content[:300])


out = {}
st, facets = g("/api/catalog/categories/elektroinstrument/facets/?tool_type=perforatory")
out["facets_status"] = st
if st == 200:
    attrs = facets.get("attributes") or facets.get("facets") or []
    out["facet_attributes"] = [
        {
            "slug": a.get("slug"),
            "name": a.get("name"),
            "type": a.get("type"),
            "min": a.get("min"),
            "max": a.get("max"),
            "values": [(v.get("value") or v.get("slug"), v.get("count")) for v in (a.get("values") or [])][:8],
        }
        for a in attrs
    ]
    out["facets_top_keys"] = list(facets.keys())

checks = {
    "all_perforatory": "/api/catalog/products/?category=elektroinstrument&tool_type=perforatory",
    "chuck_sds_plus": "/api/catalog/products/?category=elektroinstrument&tool_type=perforatory&attr_chuck=sds-plus",
    "chuck_sds_max": "/api/catalog/products/?category=elektroinstrument&tool_type=perforatory&attr_chuck=sds-max",
    "power_800_1200": "/api/catalog/products/?category=elektroinstrument&tool_type=perforatory&attr_power_min=800&attr_power_max=1200",
    "power_1500_plus": "/api/catalog/products/?category=elektroinstrument&tool_type=perforatory&attr_power_min=1500",
    "energy_5_plus": "/api/catalog/products/?category=elektroinstrument&tool_type=perforatory&attr_energy_impact_min=5",
}
out["filters"] = {}
for k, u in checks.items():
    st, data = g(u)
    out["filters"][k] = {
        "status": st,
        "count": data.get("count") if st == 200 else None,
        "first": [p.get("name") for p in (data.get("results") or [])[:3]] if st == 200 else data,
    }

print("===JSON===")
print(json.dumps(out, ensure_ascii=False, default=str))
print("===END===")
