# -*- coding: utf-8 -*-
"""CAT-04: отпечаток неприкасаемых полей. READ-ONLY.

Хэширует всё, что задача НЕ должна менять; планово затрагиваемое исключается
через env, чтобы «после» можно было сравнить с «до» при идентичных исключениях:

  CAT04_EXCLUDE_PAV   — "pid:attr_slug,..." пары PAV, которые план трогает (задача 2);
  CAT04_EXCLUDE_PIDS  — "pid,..." товары, чей attrs_cache план трогает (задача 2);
  CAT04_EXCLUDE_CA_DN — id строки CategoryAttribute, чей display_name план трогает
                        (задача 1; в хэше её display_name заменяется на "*").

Вывод — JSON в $CAT04_OUT (default /tmp/cat04_fp.json).
"""
import hashlib
import io
import json
import os

from apps.catalog.models import (
    CategoryAttribute,
    Product,
    ProductAttributeValue as PAV,
)

excl_pav = set(filter(None, (os.environ.get("CAT04_EXCLUDE_PAV") or "").split(",")))
excl_pids = {int(x) for x in filter(None, (os.environ.get("CAT04_EXCLUDE_PIDS") or "").split(","))}
ca_dn_id = os.environ.get("CAT04_EXCLUDE_CA_DN") or ""

# CAT06: файл с планом зеркала ({"plan": {"create": [{pid, attr}...]}}) — исключить
# плановые пары PAV и товары по attrs_cache (их ~400, в env не помещаются).
plan_file = os.environ.get("CAT04_PLAN_FILE") or ""
if plan_file:
    plan = json.load(open(plan_file, encoding="utf-8"))
    items = plan["plan"]["create"] + plan["plan"]["prune"]
    excl_pav |= {f"{it['pid']}:{it['attr']}" for it in items}
    excl_pids |= {it["pid"] for it in items}

out = {"excl_pav": sorted(excl_pav), "excl_pids": sorted(excl_pids), "ca_dn_id": ca_dn_id}

# --- 1. Ядро товаров (все): цена/остаток/категория/статус ---
# CAT07: CAT04_MASK_ACTIVE_YA=1 — у товаров с именем на «яя» поле is_active
# маскируется («*»): задача меняет его у них планово; всё остальное у них и всё
# у прочих товаров доказывается идентичным.
mask_ya = os.environ.get("CAT04_MASK_ACTIVE_YA") == "1"
h = hashlib.sha256()
n = 0
for p in (
    Product.objects.order_by("id").values_list(
        "id", "category_id", "price", "stock_quantity", "status", "is_active", "name"
    )
):
    n += 1
    is_active = "*" if (mask_ya and (p[6] or "").lower().startswith("яя")) else p[5]
    h.update(
        json.dumps(
            [p[0], p[1], str(p[2]), p[3], p[4], is_active], ensure_ascii=False, default=str
        ).encode()
    )
out["n_products"] = n
out["fp_products_core"] = h.hexdigest()

# --- 2. attrs_cache товаров вне планового множества ---
h = hashlib.sha256()
n = 0
for pid, cache in (
    Product.objects.exclude(id__in=excl_pids).order_by("id").values_list("id", "attrs_cache")
):
    n += 1
    h.update(json.dumps([pid, cache], sort_keys=True, ensure_ascii=False, default=str).encode())
out["n_cache"] = n
out["fp_attrs_cache"] = h.hexdigest()

# --- 3. PAV вне плановых пар (все значимые поля + источник) ---
h = hashlib.sha256()
n = 0
qs = PAV.objects.order_by("product_id", "attribute__slug").values_list(
    "product_id",
    "attribute__slug",
    "value_text",
    "value_integer",
    "value_decimal",
    "value_boolean",
    "value_option__slug",
    "source",
    "confidence",
)
for v in qs:
    key = f"{v[0]}:{v[1]}"
    if key in excl_pav:
        continue
    n += 1
    h.update(json.dumps([str(x) for x in v], ensure_ascii=False).encode())
out["n_pav"] = n
out["fp_pav"] = h.hexdigest()

# --- 4. CategoryAttribute (все строки; display_name целевой строки нормализован) ---
# CAT05: CAT04_EXCLUDE_CA_CAT — slug'и категорий (через запятую), чьи строки
# исключаются целиком (когда план создаёт новые привязки).
excl_ca_cat = set(filter(None, (os.environ.get("CAT04_EXCLUDE_CA_CAT") or "").split(",")))
h = hashlib.sha256()
n = 0
for r in (
    CategoryAttribute.objects.order_by("id").values_list(
        "id",
        "category__slug",
        "attribute__slug",
        "is_required",
        "is_filter",
        "group",
        "is_seo_facet",
        "display_name",
        "sort_order",
    )
):
    if excl_ca_cat and r[1] in excl_ca_cat:
        continue
    n += 1
    row = [str(x) for x in r]
    if ca_dn_id and str(r[0]) == ca_dn_id:
        row[7] = "*"
    h.update(json.dumps(row, ensure_ascii=False).encode())
out["n_ca"] = n
out["fp_ca"] = h.hexdigest()

# --- 5. Сводный отпечаток неприкасаемых ---
out["fp_untouchable"] = hashlib.sha256(
    (
        out["fp_products_core"] + out["fp_attrs_cache"] + out["fp_pav"] + out["fp_ca"]
    ).encode()
).hexdigest()

OUT = os.environ.get("CAT04_OUT", "/tmp/cat04_fp.json")
io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, default=str))
print("WROTE", OUT, "fp_untouchable=", out["fp_untouchable"])
