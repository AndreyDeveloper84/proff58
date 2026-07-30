# -*- coding: utf-8 -*-
"""CAT-09 recon-2: lebedki вне 169, смазка-слово вне prochaya. READ-ONLY."""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402


def type_map(pids):
    """product_id -> tool_type slug для выборки."""
    m = {}
    for r in PAV.objects.filter(
        attribute__slug="tool_type", product_id__in=pids
    ).values_list("product_id", "value_option__slug"):
        m[r[0]] = r[1]
    return m


proch = set(
    PAV.objects.filter(
        attribute__slug="tool_type", value_option__slug="prochaya-osnastka"
    ).values_list("product_id", flat=True)
)
proch_qs = Product.objects.filter(id__in=proch)

rx = re.compile(r"^(таль|тельфер|лебёдк|лебедк)", re.IGNORECASE)
out = {}

# lebedki-имя в prochaya независимо от категории
leb_all = []
for r in proch_qs.order_by("id").values(
    "id", "name", "is_active", "status", "category_id"
):
    if rx.match(r["name"].lstrip("яЯ ")):
        leb_all.append(r)
out["lebedki_by_name_total"] = len(leb_all)
out["lebedki_by_name_outside_169"] = [r for r in leb_all if r["category_id"] != 169]
out["lebedki_by_name_in_169"] = sum(1 for r in leb_all if r["category_id"] == 169)

# OR-критерий: имя ИЛИ категория 169
cat169 = set(proch_qs.filter(category_id=169).values_list("id", flat=True))
leb_ids = {r["id"] for r in leb_all}
or_ids = leb_ids | cat169
out["lebedki_or_total"] = len(or_ids)
or_qs = Product.objects.filter(id__in=or_ids, is_active=True, status="published")
out["lebedki_or_pub"] = or_qs.count()
# что в 169 без lebedki-имени (мы видели: пусто) — контроль
out["cat169_count"] = len(cat169)

# смазка-слово вне prochaya: типы
outside = list(
    Product.objects.filter(name__icontains="смазка")
    .exclude(id__in=proch)
    .values_list("id", "name")
)
tm = type_map([i for i, _ in outside])
by_type = {}
no_type = []
for i, n in outside:
    t = tm.get(i)
    if t:
        by_type.setdefault(t, []).append((i, n[:80]))
    else:
        no_type.append((i, n[:80]))
out["smazka_outside_by_type"] = {k: len(v) for k, v in by_type.items()}
out["smazka_outside_no_type"] = no_type
out["smazka_outside_other_types"] = {
    k: v for k, v in by_type.items() if k != "str-smazki"
}

print(json.dumps(out, ensure_ascii=False, default=str))
