"""TT-06 · финальная сверка + витрина (фильтр по tool_type живым запросом).

Запуск: manage.py shell -c "exec(open('scratchpad/phase8/tt06_storefront.py', encoding='utf-8').read())"
"""

from __future__ import annotations

import hashlib
import json

from apps.catalog.models import Attribute, Category, Product, ProductAttributeValue
from apps.catalog.queries import _subtree_ids, products_in

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
IDS = sorted(EXPECTED)

# 0. Хэш неприкасаемых полей — финальная сверка с ДО
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
print("UNTOUCHABLE_HASH:", hashlib.sha256(canon.encode("utf-8")).hexdigest(),
      "(ожидание be36cf755b…)")

# 1. Финальное состояние PAV
attr = Attribute.objects.get(slug="tool_type")
pav = {
    row.product_id: row.value_option.slug
    for row in ProductAttributeValue.objects.filter(product_id__in=IDS, attribute=attr)
    .select_related("value_option")
}
print("PAV_FINAL_MATCH:", pav == EXPECTED)
print("PAV_TOOL_TYPE_TOTAL:", ProductAttributeValue.objects.filter(attribute=attr).count(),
      "(ожидание 38833)")

# 2. Витрина: products_in(category, tool_type=slug) — товар виден в фильтре,
#    счётчик фильтра сходится с прямым PAV-подсчётом в поддереве
all_ok = True
for pid, slug in sorted(EXPECTED.items()):
    p = Product.objects.select_related("category").get(pk=pid)
    cat = p.category
    via_filter = products_in(cat, tool_type=slug)
    in_filter = via_filter.filter(pk=pid).exists()
    filter_count = via_filter.count()
    direct_count = Product.objects.filter(
        category_id__in=_subtree_ids(cat),
        attribute_values__attribute__slug="tool_type",
        attribute_values__value_option__slug=slug,
    ).count()
    ok = in_filter and filter_count == direct_count
    all_ok = all_ok and ok
    print(f"  product={pid:6d} {slug:22s} in_filter={in_filter} "
          f"filter_count={filter_count} direct={direct_count} {'OK' if ok else 'FAIL'}")
print("STOREFRONT_ALL_OK:", all_ok)
