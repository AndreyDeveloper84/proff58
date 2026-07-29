import json
from collections import Counter, defaultdict

import django

django.setup()
from apps.catalog.processing import canonical_hash
from apps.catalog.rules_engine import load_corpus

c = load_corpus("scratchpad/phase7a/applied_corpus_tool_type.v1.json")
raw = json.load(open("scratchpad/phase7a/applied_corpus_tool_type.v1.json", encoding="utf-8"))
cat_map = json.load(open("scratchpad/phase7a/category_map.json", encoding="utf-8"))
items = list(c.items)

def dist(field):
    return dict(sorted(Counter(getattr(i, field) for i in items).items(), key=lambda kv: (-kv[1], kv[0])))

out = {}
out["totals"] = {
    "products": len({i.product_id for i in items}),
    "rows": len(items),
    "source_groups": len({i.source_group for i in items}),
    "categories": len({cat_map[str(i.product_id)][0] for i in items}),
    "tool_types": len({i.applied_option_slug for i in items}),
}
out["source_group_dist"] = dist("source_group")
out["tool_type_dist"] = dist("applied_option_slug")
out["brand_dist"] = dist("brand")
out["source_dist"] = dist("source")
out["confidence_dist"] = dict(sorted(Counter(i.confidence for i in items).items()))
cat_counter = Counter((cat_map[str(i.product_id)][0], cat_map[str(i.product_id)][1]) for i in items)
out["category_dist"] = {
    f"{cid}|{name}": n for (cid, name), n in sorted(cat_counter.items(), key=lambda kv: (-kv[1], kv[0][0]))
}
out["facts_hash_aggregate"] = canonical_hash(sorted(r["facts_hash"] for r in raw["items"]))

# ambiguous groups: brand+source_group+category -> >=2 distinct labels
groups = defaultdict(lambda: defaultdict(list))
for i in items:
    cid, cname = cat_map[str(i.product_id)]
    key = (i.brand, i.source_group, f"{cid}|{cname}")
    groups[key][i.applied_option_slug].append(i.product_id)
amb = []
for (brand, sg, cat), labels in groups.items():
    if len(labels) >= 2:
        for slug, pids in sorted(labels.items()):
            amb.append({
                "brand": brand, "source_group": sg, "category": cat,
                "label": slug, "count": len(pids), "product_ids": sorted(pids),
            })
out["ambiguous_groups"] = amb

# family groups (brand+source_group) для деривации: labels по группам
fam = defaultdict(lambda: defaultdict(list))
for i in items:
    fam[(i.brand, i.source_group)][i.applied_option_slug].append(i.product_id)
out["family_groups"] = [
    {"brand": b, "source_group": sg, "labels": {s: sorted(p) for s, p in sorted(l.items())}}
    for (b, sg), l in sorted(fam.items(), key=lambda kv: (-sum(len(x) for x in kv[1].values()), kv[0]))
]

json.dump(out, open("scratchpad/phase7a/analysis.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2, sort_keys=True)
print(json.dumps(out["totals"], sort_keys=True))
print("tool_type_dist", json.dumps(out["tool_type_dist"], ensure_ascii=False, sort_keys=True))
print("source_dist", out["source_dist"])
print("confidence_dist", out["confidence_dist"])
print("ambiguous_groups_count", len(amb))
print("facts_hash_aggregate", out["facts_hash_aggregate"])
