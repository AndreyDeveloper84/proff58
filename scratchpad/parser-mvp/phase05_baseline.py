# -*- coding: utf-8 -*-
"""Phase 0.5 read-only baseline: покрытие атрибутов перфораторов правилами.

НИЧЕГО НЕ ПИШЕТ. Печатает JSON в stdout (маркеры ===JSON=== ... ===END===).
Опциональный env RULES_PATH — каталог с attribute_rules.json (для прогона
докрученных правил без записи в репозиторий стенда).
"""
import json
import os
from collections import Counter

from apps.catalog.attribute_extract import AttributeRules
from apps.catalog.ingest import data_dir
from apps.catalog.models import ProductAttributeValue, Product

TT = "perforatory"

base = os.environ.get("RULES_PATH") or data_dir()
raw = json.loads(open(f"{base}/attribute_rules.json", encoding="utf-8").read())
rules = AttributeRules.from_dict(raw)
managed = [a["slug"] for tt in raw["tool_types"] if tt["tool_type"] == TT for a in tt["attributes"]]

pids = list(
    ProductAttributeValue.objects.filter(
        attribute__slug="tool_type", value_option__slug=TT
    ).values_list("product_id", flat=True)
)

# существующие PAV этих товаров (кроме самого tool_type) — контроль «до»
existing = Counter()
manual_rows = []
for pav in ProductAttributeValue.objects.filter(product_id__in=pids).select_related(
    "attribute", "value_option"
):
    if pav.attribute.slug == "tool_type":
        continue
    existing[f"{pav.attribute.slug}:{pav.source}"] += 1
    if pav.source == "manual":
        manual_rows.append([pav.product_id, pav.attribute.slug])

products = list(Product.objects.filter(id__in=pids).order_by("id"))
cov = Counter()
rows = []
for p in products:
    name = p.original_name or p.name
    vals = rules.extract(TT, name)
    got = {}
    for v in vals:
        cov[v.slug] += 1
        got[v.slug] = {
            "val": str(v.number) if v.number is not None else (v.option_value or v.boolean),
            "src": v.source,
            "m": v.matched,
        }
    rows.append(
        {
            "id": p.id,
            "art": p.article,
            "name": name,
            "n": len(got),
            "got": got,
        }
    )

out = {
    "total": len(products),
    "coverage": {k: cov[k] for k in managed},
    "managed": managed,
    "existing_pav_before": dict(existing),
    "manual_rows": manual_rows,
    "zero_attr": sum(1 for r in rows if r["n"] == 0),
    "rows": rows,
}
print("===JSON===")
print(json.dumps(out, ensure_ascii=False))
print("===END===")
