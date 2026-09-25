"""Phase 8 · ступень 3 — стратифицированный отбор 20 товаров без tool_type.

Критерий (дословно, см. протокол):
- вселенная: товары без заполненного tool_type (предикат
  catalog_queue_create._products_without_tool_type);
- страта: корневой раздел категории товара (depth=1 в дереве MP_Node);
- порядок страт: по убыванию числа untyped-товаров, при равенстве — по
  возрастанию id корневой категории;
- внутри страты: товары по возрастанию id;
- выборка: round-robin — по одному следующему товару из каждой непустой
  страты в порядке страт, циклически, пока не набрано 20.

Запуск: manage.py shell -c "exec(open('scratchpad/phase8/select_step3.py', encoding='utf-8').read())"
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

from django.db.models import Exists, OuterRef

from apps.catalog.models import Category, Product, ProductAttributeValue

N = 20

has_tt = ProductAttributeValue.objects.filter(
    product_id=OuterRef("pk"),
    attribute__slug="tool_type",
    value_option__isnull=False,
)
untyped = (
    Product.objects.annotate(has_tt=Exists(has_tt))
    .filter(has_tt=False)
    .order_by("pk")
    .values_list("pk", "category_id")
)
untyped = list(untyped)
print("untyped_total:", len(untyped))

# Корневые категории: depth=1 в MP_Node; корень — первые steplen символов path.
# Сегменты path у treebeard alphanumeric → маппинг через path, не int().
root_objs = list(Category.objects.filter(depth=1))
roots = {c.pk: c.name for c in root_objs}
path_to_root = {c.path: c.pk for c in root_objs}
steplen = Category.steplen
cat_to_root: dict[int, int] = {}
for c in Category.objects.all().only("pk", "path", "depth"):
    cat_to_root[c.pk] = path_to_root.get(c.path[:steplen], 0)

strata: dict[int, list[int]] = defaultdict(list)
no_cat = 0
for pk, cat_id in untyped:
    if cat_id is None or cat_id not in cat_to_root:
        no_cat += 1
        strata[0].append(pk)  # страта 0 = без категории/вне дерева
    else:
        strata[cat_to_root[cat_id]].append(pk)
print("products_without_category_mapping:", no_cat)

# Порядок страт: count desc, id asc (страта 0 — в конец, если есть)
def strata_key(item):
    root_id, ids = item
    return (-len(ids), root_id == 0, root_id)

ordered = sorted(strata.items(), key=strata_key)
print("\nstrata (root_id | name | untyped_count):")
for root_id, ids in ordered:
    print(f"  {root_id:6d} | {roots.get(root_id, '<без категории>')[:60]:60s} | {len(ids)}")

# Round-robin
selected: list[tuple[int, int]] = []  # (product_id, root_id)
idx = {root_id: 0 for root_id, _ in ordered}
while len(selected) < N:
    progressed = False
    for root_id, ids in ordered:
        if len(selected) >= N:
            break
        i = idx[root_id]
        if i < len(ids):
            selected.append((ids[i], root_id))
            idx[root_id] += 1
            progressed = True
    if not progressed:
        break

print("\nselected (product_id | root | name):")
sel_ids = [pid for pid, _ in selected]
names = {p.pk: p.name for p in Product.objects.filter(pk__in=sel_ids)}
for pid, root_id in selected:
    print(f"  {pid:6d} | {roots.get(root_id, '<без категории>')[:30]:30s} | {names.get(pid, '')[:80]}")

out = {
    "n": N,
    "untyped_total": len(untyped),
    "strata": [
        {"root_id": r, "root_name": roots.get(r), "untyped_count": len(ids)}
        for r, ids in ordered
    ],
    "selected": [
        {"product_id": pid, "root_id": rid, "root_name": roots.get(rid)}
        for pid, rid in selected
    ],
    "selected_ids": sel_ids,
}
out_path = os.environ.get("PH8_SELECTION_OUT", "scratchpad/phase8/artifacts-step3/selection.json")
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print("\nwrote:", out_path)
print("IDS:", ",".join(str(i) for i in sel_ids))
