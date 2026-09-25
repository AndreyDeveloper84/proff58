# -*- coding: utf-8 -*-
"""CAT-02: отпечаток неприкасаемых полей + предсказание фасетов. READ-ONLY.

Считает:
  * ``fp_untouchable`` — sha256 по цене/остатку/категории/статусу/tool_type/всем PAV/
    attrs_cache всех товаров поддерева izmeritelnyy (то, что задача НЕ должна трогать);
  * ``fp_ca_out_of_scope`` — sha256 по ВСЕМ CategoryAttribute вне 6 целевых категорий
    (доказывает, что чужие настройки показа не задеты);
  * ``ca_in_scope`` — строки CategoryAttribute целевых категорий (до/после);
  * ``predict`` — точные значения и счётчики будущих фасетов, посчитанные ТЕМ ЖЕ
    способом, что build_facets (visible_products + GROUP BY attrs_cache).

Вывод — JSON в $CAT02_OUT.
"""
import hashlib
import io
import json
import os

from django.db.models import Count
from django.db.models.fields.json import KeyTextTransform

from apps.catalog.filters import visible_products
from apps.catalog.models import (
    Category,
    CategoryAttribute,
    Product,
    ProductAttributeValue as PAV,
)

TARGETS = {
    "izmeritelnyy-ruletki": ["tape_length", "tape_width"],
    "izmeritelnyy-urovni": ["length"],
    "izmeritelnyy-shtangencirkuli-i-mikrometry": ["measuring_range", "readout_type"],
    "izmeritelnyy-ugolniki-i-lineyki": ["size"],
    "izmeritelnyy-dalnomery": ["max_distance"],
}
# Кандидаты, отклонённые критерием, — тоже мерим, чтобы обосновать отказ.
REJECTED = {
    "izmeritelnyy-lazernye-urovni-i-niveliry": ["level_type"],
    "izmeritelnyy-uglomery-i-uklonomery": ["size"],
}

out = {}
root = Category.objects.get(slug="izmeritelnyy")
sub_ids = [root.pk, *root.get_descendants().values_list("pk", flat=True)]
target_cat_ids = list(
    Category.objects.filter(slug__in=list(TARGETS)).values_list("pk", flat=True)
)
out["target_cat_ids"] = sorted(target_cat_ids)

# --- 1. Отпечаток неприкасаемых полей (товары поддерева) ---
h = hashlib.sha256()
for p in (
    Product.objects.filter(category_id__in=sub_ids)
    .order_by("id")
    .values_list(
        "id", "category_id", "price", "stock_quantity", "status", "is_active", "attrs_cache"
    )
):
    h.update(
        json.dumps(
            [p[0], p[1], str(p[2]), p[3], p[4], p[5], p[6]],
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ).encode()
    )
out["n_products_hashed"] = Product.objects.filter(category_id__in=sub_ids).count()

hp = hashlib.sha256()
n_pav = 0
for v in (
    PAV.objects.filter(product__category_id__in=sub_ids)
    .order_by("product_id", "attribute__slug")
    .values_list(
        "product_id",
        "attribute__slug",
        "value_text",
        "value_decimal",
        "value_option__slug",
        "source",
    )
):
    n_pav += 1
    hp.update(json.dumps([str(x) for x in v], ensure_ascii=False).encode())
out["n_pav_hashed"] = n_pav
out["fp_untouchable"] = hashlib.sha256(
    (h.hexdigest() + hp.hexdigest()).encode()
).hexdigest()
out["fp_products"] = h.hexdigest()
out["fp_pav"] = hp.hexdigest()

# --- 2. Отпечаток CategoryAttribute ВНЕ целевых категорий ---
ho = hashlib.sha256()
n_out = 0
for r in (
    CategoryAttribute.objects.exclude(category_id__in=target_cat_ids)
    .order_by("category__slug", "attribute__slug")
    .values_list(
        "category__slug",
        "attribute__slug",
        "is_filter",
        "group",
        "sort_order",
        "is_seo_facet",
        "is_required",
    )
):
    n_out += 1
    ho.update(json.dumps([str(x) for x in r], ensure_ascii=False).encode())
out["n_ca_out_of_scope"] = n_out
out["fp_ca_out_of_scope"] = ho.hexdigest()

# --- 3. Текущие CategoryAttribute целевых категорий ---
out["ca_in_scope"] = [
    {
        "cat": ca.category.slug,
        "attr": ca.attribute.slug,
        "is_filter": ca.is_filter,
        "group": ca.group,
        "sort": ca.sort_order,
        "seo": ca.is_seo_facet,
    }
    for ca in CategoryAttribute.objects.filter(category_id__in=target_cat_ids)
    .select_related("category", "attribute")
    .order_by("category__slug", "attribute__slug")
]

# --- 4. Предсказание фасетов: те же счётчики, что даст build_facets ---
pred = {}
for cat_slug, attrs in list(TARGETS.items()) + list(REJECTED.items()):
    c = Category.objects.get(slug=cat_slug)
    ids = [c.pk, *c.get_descendants().values_list("pk", flat=True)]
    base = visible_products().filter(category_id__in=ids)
    entry = {"category_id": c.pk, "published_total": base.count(), "descendants": len(ids) - 1}
    for a in attrs:
        rows = (
            base.annotate(_fv=KeyTextTransform(a, "attrs_cache"))
            .filter(_fv__isnull=False)
            .values("_fv")
            .annotate(c=Count("id"))
        )
        vals = sorted(((r["_fv"], r["c"]) for r in rows), key=lambda t: t[0])
        entry[a] = {
            "products_with_attr": sum(n for _, n in vals),
            "distinct_values": len(vals),
            "share_of_published": round(
                100.0 * sum(n for _, n in vals) / max(entry["published_total"], 1), 1
            ),
            "values": vals,
        }
    pred[cat_slug] = entry
out["predict"] = pred

OUT = os.environ.get("CAT02_OUT", "/tmp/cat02_fp.json")
io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, default=str))
print("WROTE", OUT, "fp_untouchable=", out["fp_untouchable"])
