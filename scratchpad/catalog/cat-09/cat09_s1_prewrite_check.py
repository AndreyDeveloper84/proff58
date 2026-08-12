# -*- coding: utf-8 -*-
"""CAT-09 S1: предзаписная сверка. READ-ONLY.

1) счётчики prochaya / str-smazki / PAV total — должны совпасть с prep;
2) товар 28259 — подтверждение, что 33 vs 32 видимых — это яя-деактивация CAT-07;
3) свежесть: max(updated_at) по Product — нет ли записи прямо сейчас.
"""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from django.db.models import Max  # noqa: E402

from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402


def cnt(slug, published=False):
    pids = PAV.objects.filter(
        attribute__slug="tool_type", value_option__slug=slug
    ).values_list("product_id", flat=True)
    q = Product.objects.filter(id__in=pids)
    if published:
        q = q.filter(is_active=True, status="published")
    return q.count()


p28259 = Product.objects.filter(pk=28259).values(
    "pk", "name", "is_active", "status", "is_active_1c", "stock_quantity", "updated_at"
).first()

# яя-деактивированные внутри кластера смазок (88 id)
smaz_pids = PAV.objects.filter(
    attribute__slug="tool_type", value_option__slug="prochaya-osnastka",
    product__name__icontains="смазка",
).values_list("product_id", flat=True)
yaya_in_cluster = list(
    Product.objects.filter(id__in=smaz_pids, name__istartswith="яя").values(
        "pk", "name", "is_active", "status"
    )
)

recent = Product.objects.aggregate(m=Max("updated_at"))["m"]
recent_names = list(
    Product.objects.filter(updated_at=recent).values_list("pk", "name")[:5]
)

print(json.dumps({
    "prochaya_total": cnt("prochaya-osnastka"),
    "prochaya_pub": cnt("prochaya-osnastka", True),
    "str-smazki_total": cnt("str-smazki"),
    "str-smazki_pub": cnt("str-smazki", True),
    "pav_total": PAV.objects.filter(attribute__slug="tool_type").count(),
    "p28259": {k: str(v) for k, v in (p28259 or {}).items()},
    "yaya_in_smazki_cluster": [
        {k: str(v) for k, v in r.items()} for r in yaya_in_cluster
    ],
    "max_updated_at": str(recent),
    "products_at_max_updated": recent_names,
}, ensure_ascii=False))
