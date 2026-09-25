"""Phase 8 · ступень 1 — отпечаток неприкасаемых полей каталога.

Считает SHA-256 по канонической проекции всех товаров песочницы:
code_1c, article, name, category_id, price, stock_quantity, status,
is_active + slug опции атрибута tool_type.

Печатает per-product строки и итоговый хэш. Используется как «до/после»
пруф инварианта «отмена batch не меняет каталог».

Usage:
    manage.py shell -c "exec(open(...).read())"   # печатает в stdout
Переменная окружения PH8_FINGERPRINT_OUT — путь для записи JSON.
"""

from __future__ import annotations

import hashlib
import json
import os

from apps.catalog.models import Product, ProductAttributeValue

TOOL_TYPE_SLUG = "tool_type"


def build() -> dict:
    tool_types: dict[int, str] = {}
    for pav in ProductAttributeValue.objects.filter(
        attribute__slug=TOOL_TYPE_SLUG
    ).select_related("value_option"):
        tool_types[pav.product_id] = pav.value_option.slug if pav.value_option else ""

    rows = []
    for product in Product.objects.order_by("pk"):
        rows.append(
            {
                "product_id": product.pk,
                "code_1c": product.code_1c or "",
                "article": product.article or "",
                "name": product.name or "",
                "category_id": product.category_id,
                "price": str(product.price) if product.price is not None else None,
                "stock_quantity": str(product.stock_quantity),
                "status": product.status,
                "is_active": product.is_active,
                "tool_type_option_slug": tool_types.get(product.pk, ""),
            }
        )
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return {
        "products": len(rows),
        "pav_tool_type_rows": len(tool_types),
        "fingerprint_sha256": digest,
        "rows": rows,
    }


_result = build()
_out = os.environ.get("PH8_FINGERPRINT_OUT")
if _out:
    with open(_out, "w", encoding="utf-8") as _f:
        json.dump(_result, _f, ensure_ascii=False, indent=2, sort_keys=True)
print(
    f"PRODUCTS={_result['products']} "
    f"PAV_TOOL_TYPE={_result['pav_tool_type_rows']} "
    f"FINGERPRINT={_result['fingerprint_sha256']}"
)
