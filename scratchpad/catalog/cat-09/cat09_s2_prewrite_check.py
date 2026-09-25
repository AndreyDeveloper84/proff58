# -*- coding: utf-8 -*-
"""CAT-09 S2: предзаписная сверка. READ-ONLY.

1) счётчики lebedki-tali / prochaya / PAV == prep;
2) TT-10 не писал: его 9 id на исходных типах (4 из них в lebedki-tali);
3) пересечения TT-10 с кластером S2 нет.
"""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402

TT10 = {
    1109: "akkumulyatory", 24866: "svar-provoloka",
    28886: "krep-gvozdi", 28887: "krep-gvozdi",
    34643: "lebedki-tali", 34644: "lebedki-tali",
    35057: "lebedki-tali", 35058: "lebedki-tali",
    36379: "svar-maski",
}


def cnt(slug, published=False):
    pids = PAV.objects.filter(
        attribute__slug="tool_type", value_option__slug=slug
    ).values_list("product_id", flat=True)
    q = Product.objects.filter(id__in=pids)
    if published:
        q = q.filter(is_active=True, status="published")
    return q.count()


tt10_state = {}
for pid, expect in TT10.items():
    pav = PAV.objects.filter(product_id=pid, attribute__slug="tool_type").first()
    cur = pav.value_option.slug if pav and pav.value_option else None
    tt10_state[pid] = {"expect": expect, "current": cur, "ok": cur == expect}

s2_ids = {int(k) for k in json.load(io.open("/tmp/cat09-s2-rollback.json", encoding="utf-8"))}
overlap = sorted(s2_ids & set(TT10))

print(json.dumps({
    "lebedki-tali_total": cnt("lebedki-tali"),
    "lebedki-tali_pub": cnt("lebedki-tali", True),
    "prochaya_total": cnt("prochaya-osnastka"),
    "prochaya_pub": cnt("prochaya-osnastka", True),
    "pav_total": PAV.objects.filter(attribute__slug="tool_type").count(),
    "tt10_all_on_source_types": all(v["ok"] for v in tt10_state.values()),
    "tt10_state": tt10_state,
    "tt10_overlap_with_s2": overlap,
}, ensure_ascii=False))
