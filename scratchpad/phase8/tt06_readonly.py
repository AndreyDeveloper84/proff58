"""TT-06 · read-only: отпечаток неприкасаемых полей (БЕЗ tool_type) + preflight.

Отпечаток ТТ-06 не включает tool_type (он меняется по замыслу); параллельно
печатается текущий tool_type 11 товаров (ожидание — пусто) и preflight:
content_locked, manual-значения, существование всех 11 опций в словаре.

Запуск: manage.py shell -c "exec(open('scratchpad/phase8/tt06_readonly.py', encoding='utf-8').read())"
PH8_TT06_OUT — путь для JSON-снимка.
"""

from __future__ import annotations

import hashlib
import json
import os

from apps.catalog.models import (
    Attribute,
    AttributeOption,
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

# 1. Отпечаток неприкасаемых полей ВСЕХ товаров (без tool_type)
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
untouchable_hash = hashlib.sha256(canon.encode("utf-8")).hexdigest()
print("UNTOUCHABLE_HASH:", untouchable_hash)
print("PRODUCTS:", len(rows))

# 2. Текущий tool_type у 11 (ожидание — пусто) + PAV-строки (дубли?)
attr = Attribute.objects.get(slug="tool_type")
pav = list(ProductAttributeValue.objects.filter(product_id__in=IDS, attribute=attr))
print("PAV_11_COUNT:", len(pav), "(ожидание 0)")
for row in pav:
    print("  UNEXPECTED_PAV:", row.product_id, row.value_option_id, row.source)

# 3. Preflight
locked = list(Product.objects.filter(pk__in=IDS, content_locked=True).values_list("pk", flat=True))
print("CONTENT_LOCKED:", locked, "(ожидание [])")
manual = [
    (row.product_id, row.source)
    for row in ProductAttributeValue.objects.filter(product_id__in=IDS, attribute=attr, source="manual")
]
print("MANUAL_TOOL_TYPE:", manual, "(ожидание [])")
opts = set(AttributeOption.objects.filter(attribute=attr, slug__in=set(EXPECTED.values())).values_list("slug", flat=True))
missing = sorted(set(EXPECTED.values()) - opts)
print("OPTIONS_MISSING:", missing, "(ожидание [])")
print("OPTIONS_TOTAL:", AttributeOption.objects.filter(attribute=attr).count())

out = {
    "untouchable_hash": untouchable_hash,
    "products": len(rows),
    "pav_11_count": len(pav),
    "content_locked": locked,
    "manual_tool_type": manual,
    "options_missing": missing,
    "expected": EXPECTED,
}
out_path = os.environ.get("PH8_TT06_OUT")
if out_path:
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("wrote:", out_path)
