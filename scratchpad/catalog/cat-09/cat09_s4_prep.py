# -*- coding: utf-8 -*-
"""CAT-09 S4 (тележки → obor-telezhki): rollback-map + предсказание. READ-ONLY.

Критерий: tool_type=prochaya-osnastka AND name ~ ^тележк (регистронезависимо).
Решение владельца 2026-07-29: кластер → obor-telezhki (НЕ hoz-tachki).
Пишет /tmp/cat09-s4-rollback.json (в контейнере). В БД не пишет.
"""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import AttributeOption  # noqa: E402
from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402

RX = re.compile(r"^тележк", re.IGNORECASE)

opt_old = AttributeOption.objects.get(attribute__slug="tool_type", slug="prochaya-osnastka")
opt_new = AttributeOption.objects.get(attribute__slug="tool_type", slug="obor-telezhki")

proch = PAV.objects.filter(
    attribute__slug="tool_type", value_option=opt_old
).values_list("product_id", flat=True)
qs = Product.objects.filter(id__in=proch).order_by("id")
ids = [p.id for p in qs if RX.match(p.name.lstrip("яЯ "))]

rollback = {}
errors = []
for pid in ids:
    pav = PAV.objects.filter(product_id=pid, attribute__slug="tool_type").first()
    if pav is None or pav.value_option_id != opt_old.id:
        errors.append(f"{pid}: option {pav.value_option_id if pav else None} != {opt_old.id}")
        continue
    rollback[str(pid)] = {
        "old_option_id": opt_old.id,
        "new_option_id": opt_new.id,
        "old_slug": "prochaya-osnastka",
        "new_slug": "obor-telezhki",
    }
if errors:
    raise SystemExit("PRECHECK FAILED:\n" + "\n".join(errors))

with io.open("/tmp/cat09-s4-rollback.json", "w", encoding="utf-8") as f:
    json.dump(rollback, f, ensure_ascii=False, indent=1)

pub = Product.objects.filter(id__in=ids, is_active=True, status="published").count()


def cnt(slug, published=False):
    pids = PAV.objects.filter(
        attribute__slug="tool_type", value_option__slug=slug
    ).values_list("product_id", flat=True)
    q = Product.objects.filter(id__in=pids)
    if published:
        q = q.filter(is_active=True, status="published")
    return q.count()


pav_total = PAV.objects.filter(attribute__slug="tool_type").count()

print(json.dumps({
    "old_option_id": opt_old.id,
    "new_option_id": opt_new.id,
    "ids_count": len(ids),
    "pub_in_cluster": pub,
    "predict": {
        "obor-telezhki_total": [cnt("obor-telezhki"), cnt("obor-telezhki") + len(ids)],
        "obor-telezhki_pub": [cnt("obor-telezhki", True), cnt("obor-telezhki", True) + pub],
        "prochaya_total": [cnt("prochaya-osnastka"), cnt("prochaya-osnastka") - len(ids)],
        "prochaya_pub": [cnt("prochaya-osnastka", True), cnt("prochaya-osnastka", True) - pub],
        "pav_total": [pav_total, pav_total],
    },
}, ensure_ascii=False))
