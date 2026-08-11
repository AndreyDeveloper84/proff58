"""TT-06 · post-audit: ровно 11 типов, без дублей, attrs_cache, хэш неприкасаемых.

Запуск: manage.py shell -c "exec(open('scratchpad/phase8/tt06_postaudit.py', encoding='utf-8').read())"
"""

from __future__ import annotations

import hashlib
import json

from apps.catalog.models import (
    Attribute,
    Product,
    ProductAttributeValue,
)

IDS = [4, 22, 123, 164, 179, 377, 422, 4944, 4945, 11232, 23606]
EXPECTED = {
    4: "izm-areometry",
    22: "spetsialnye-klyuchi",
    123: "domkraty",
    164: "zaryadnye",
    179: "bp-kompressory",
    377: "sharoshki",
    422: "bp-vozdukhoduvki",
    4944: "yashchiki-sumki",
    4945: "krep-bolty",
    11232: "payalniki",
    23606: "hoz-himiya",
}

# 1. Хэш неприкасаемых полей (без tool_type) — должен совпасть с ДО
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

# 2. PAV по 11 товарам: ровно 11, slug == одобренный, без дублей
attr = Attribute.objects.get(slug="tool_type")
pav = list(
    ProductAttributeValue.objects.filter(product_id__in=IDS, attribute=attr)
    .select_related("value_option").order_by("product_ref" if False else "product_id")
)
actual = {row.product_id: (row.value_option.slug if row.value_option else None) for row in pav}
print("PAV_11_COUNT:", len(pav), "(ожидание 11)")
print("PAV_MATCH_EXPECTED:", actual == {k: v for k, v in EXPECTED.items()})
for pid, slug in sorted(actual.items()):
    dup = ProductAttributeValue.objects.filter(product_id=pid, attribute=attr).count()
    print(f"  product={pid:6d} tool_type={slug:22s} rows={dup}")
print("PAV_TOOL_TYPE_TOTAL:", ProductAttributeValue.objects.filter(attribute=attr).count(),
      "(ожидание 38833)")

# 3. attrs_cache точечно: значение == value опции
mismatch = []
for pid, slug in sorted(EXPECTED.items()):
    p = Product.objects.get(pk=pid)
    cached = (p.attrs_cache or {}).get("tool_type")
    expected_value = pav_value = next(
        row.value_option.value for row in pav if row.product_id == pid
    )
    ok = cached == expected_value
    if not ok:
        mismatch.append((pid, cached, expected_value))
    print(f"  attrs_cache product={pid:6d} {cached!r:30s} {'OK' if ok else 'MISMATCH'}")
print("ATTRS_CACHE_MISMATCH:", mismatch, "(ожидание [])")

# 4. rejected/needs_review не затронуты: PAV у 9 items вне apply
others = [1453, 1860, 2126, 5312, 6503, 6798, 10559, 28270, 39029]
touched = ProductAttributeValue.objects.filter(product_id__in=others, attribute=attr).count()
print("PAV_OTHERS_COUNT:", touched, "(ожидание 0)")
