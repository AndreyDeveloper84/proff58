"""TT-08 · ДО-состояние + rollback-map (read-only).

Запуск: manage.py shell -c "exec(open('scratchpad/phase8/tt08_state.py', encoding='utf-8').read())"
PH8_TT08_MODE: 'before' — пишет rollback-map + ДО; 'after' — только счётчики.
"""

from __future__ import annotations

import hashlib
import io
import json
import os

from apps.catalog.models import Attribute, AttributeOption, Product, ProductAttributeValue

WATCH = [
    "dreli-shurupoverty", "prochaya-osnastka", "gaikoverty", "gaikoverty-ruchnye",
    "bp-leska", "golovki", "spetsialnye-klyuchi", "izm-ugolniki", "bp-trimmery",
]

rows = []
for p in Product.objects.order_by("pk").values(
    "pk", "code_1c", "article", "name", "category_id",
    "price", "stock_quantity", "status", "is_active",
):
    rows.append([
        p["pk"], p["code_1c"] or "", p["article"] or "", p["name"] or "",
        p["category_id"], str(p["price"]), str(p["stock_quantity"]),
        p["status"], p["is_active"],
    ])
canon = json.dumps(rows, ensure_ascii=False, sort_keys=True)
print("UNTOUCHABLE_HASH:", hashlib.sha256(canon.encode("utf-8")).hexdigest())

attr = Attribute.objects.get(slug="tool_type")
counts = {}
from django.db.models import Count
for slug, n in (
    ProductAttributeValue.objects.filter(attribute=attr, value_option__slug__in=WATCH)
    .values("value_option__slug").annotate(n=Count("id")).order_by("value_option__slug")
    .values_list("value_option__slug", "n")
):
    counts[slug] = n
    print(f"  {slug:22s} {n}")
print("PAV_TOOL_TYPE_TOTAL:", ProductAttributeValue.objects.filter(attribute=attr).count())

mode = os.environ.get("PH8_TT08_MODE", "before")
if mode == "before":
    lists = json.load(io.open("scratchpad/phase8/tt-08-lists.json", encoding="utf-8"))
    pid_to_new = {}
    for slug, ids in lists["plan"].items():
        for pid in ids:
            pid_to_new[pid] = slug
    opts = {o.slug: o.pk for o in AttributeOption.objects.filter(attribute=attr)}
    rollback = {}
    for row in ProductAttributeValue.objects.filter(
        product_id__in=pid_to_new, attribute=attr
    ).select_related("value_option"):
        rollback[row.product_id] = {
            "old_option_id": row.value_option_id,
            "old_slug": row.value_option.slug if row.value_option else None,
            "new_option_id": opts[pid_to_new[row.product_id]],
            "new_slug": pid_to_new[row.product_id],
        }
    missing = sorted(set(pid_to_new) - set(rollback))
    print("PAV_MISSING_FOR_PLAN:", missing, "(ожидание [])")
    with io.open("scratchpad/phase8/artifacts-tt08/rollback-map.json", "w", encoding="utf-8") as fh:
        json.dump(rollback, fh, ensure_ascii=False, indent=1)
    print("rollback-map rows:", len(rollback))
