# -*- coding: utf-8 -*-
"""CAT-08: отпечаток неприкасаемых полей + имён вне целевого множества. READ-ONLY.

Хэширует по всем товарам: id, code_1c, article, slug, category_id, price,
stock_quantity, status, is_active, original_name — поля, которые задача НЕ меняет.
Отдельно хэширует name товаров ВНЕ целевого множества (чужие названия не тронуты).
Имена целевых 4550 не хэшируются — их проверка 1:1 по rollback-map.
"""
import hashlib
import io
import json
import os

from apps.catalog.models import Product

h = hashlib.sha256()
n = 0
for p in (
    Product.objects.order_by("id").values_list(
        "id", "code_1c", "article", "slug", "category_id", "price",
        "stock_quantity", "status", "is_active", "original_name",
    )
):
    n += 1
    h.update(json.dumps([str(x) for x in p], ensure_ascii=False).encode())

hn = hashlib.sha256()
nn = 0
for pid, name in (
    Product.objects.exclude(name__iregex=r"^\s*яя").order_by("id").values_list("id", "name")
):
    nn += 1
    hn.update(json.dumps([pid, name], ensure_ascii=False).encode())

out = {
    "n_products": n,
    "fp_untouchable": h.hexdigest(),
    "n_names_outside": nn,
    "fp_names_outside": hn.hexdigest(),
}
OUT = os.environ.get("CAT08_OUT", "/tmp/cat08_fp.json")
io.open(OUT, "w", encoding="utf-8").write(json.dumps(out))
print("WROTE", OUT, out["fp_untouchable"][:16], out["fp_names_outside"][:16])
