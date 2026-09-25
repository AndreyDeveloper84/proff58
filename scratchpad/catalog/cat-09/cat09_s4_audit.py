# -*- coding: utf-8 -*-
"""CAT-09 S1: post-audit счётчиков. READ-ONLY."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402


def cnt(slug, published=False):
    pids = PAV.objects.filter(
        attribute__slug="tool_type", value_option__slug=slug
    ).values_list("product_id", flat=True)
    q = Product.objects.filter(id__in=pids)
    if published:
        q = q.filter(is_active=True, status="published")
    return q.count()


# дубли PAV по кластеру
rollback = json.load(io.open("/tmp/cat09-s4-rollback.json", encoding="utf-8"))
ids = [int(k) for k in rollback]
dups = [
    pid for pid in ids
    if PAV.objects.filter(product_id=pid, attribute__slug="tool_type").count() != 1
]

print(json.dumps({
    "obor-telezhki_total": cnt("obor-telezhki"),
    "obor-telezhki_pub": cnt("obor-telezhki", True),
    "prochaya_total": cnt("prochaya-osnastka"),
    "prochaya_pub": cnt("prochaya-osnastka", True),
    "pav_total": PAV.objects.filter(attribute__slug="tool_type").count(),
    "pav_dups_in_cluster": dups,
}, ensure_ascii=False))
