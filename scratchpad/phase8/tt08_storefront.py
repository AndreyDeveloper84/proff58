"""TT-08 · витрина ПОСЛЕ: фильтры по новым типам живым запросом products_in.

Для каждого из 3 новых типов: выборка товаров типа из каталога, проверка,
что products_in(category, tool_type=slug) содержит их, и счётчик фильтра
сходится с прямым PAV-подсчётом в поддереве. Плюс сводные счётчики типов.

Запуск: manage.py shell -c "exec(open('scratchpad/phase8/tt08_storefront.py', encoding='utf-8').read())"
"""

from __future__ import annotations

import hashlib
import json

from django.db.models import Count

from apps.catalog.models import Product, ProductAttributeValue
from apps.catalog.queries import _subtree_ids, products_in

NEW = ["gaikoverty", "gaikoverty-ruchnye", "bp-leska"]

attr_pav = ProductAttributeValue.objects.filter(attribute__slug="tool_type")

# 1. Сводные счётчики типов (PAV)
print("== счётчики типов (PAV) ==")
for slug, n in (
    attr_pav.filter(value_option__slug__in=NEW + [
        "dreli-shurupoverty", "prochaya-osnastka", "golovki",
        "spetsialnye-klyuchi", "izm-ugolniki", "bp-trimmery",
    ])
    .values("value_option__slug").annotate(n=Count("id")).order_by("value_option__slug")
    .values_list("value_option__slug", "n")
):
    print(f"  {slug:22s} {n}")

# 2. Фильтр витрины по новым типам: случайные до 5 товаров каждого типа
print("== products_in(category, tool_type) — выборочно ==")
all_ok = True
for slug in NEW:
    pids = list(
        attr_pav.filter(value_option__slug=slug)
        .order_by("product_id").values_list("product_id", flat=True)[:5]
    )
    for pid in pids:
        p = Product.objects.select_related("category").get(pk=pid)
        via = products_in(p.category, tool_type=slug)
        in_f = via.filter(pk=pid).exists()
        direct = Product.objects.filter(
            category_id__in=_subtree_ids(p.category),
            attribute_values__attribute__slug="tool_type",
            attribute_values__value_option__slug=slug,
        ).count()
        ok = in_f and via.count() == direct
        all_ok = all_ok and ok
        if not ok or pid == pids[0]:
            print(f"  {slug:20s} product={pid:6d} in_filter={in_f} count={via.count()} direct={direct} {'OK' if ok else 'FAIL'}")
print("STOREFRONT_ALL_OK:", all_ok)

# 3. Хэш неприкасаемых полей
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
print("PAV_TOOL_TYPE_TOTAL:", attr_pav.count(), "(ожидание 38833)")
