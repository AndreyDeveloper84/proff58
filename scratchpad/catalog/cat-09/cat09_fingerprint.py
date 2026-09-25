# -*- coding: utf-8 -*-
"""CAT-09: отпечаток неприкасаемых полей (как dump_proj в TT-08). READ-ONLY.

Печатает SHA-256 проекции (pk, code_1c, article, name, category_id, price,
stock_quantity, status, is_active) и сохраняет проекцию в /tmp/.
Имя файла — из CAT09_PROJ (default /tmp/cat09-proj.json).
"""
import hashlib
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product  # noqa: E402

out = []
for p in Product.objects.order_by("pk").values(
    "pk", "code_1c", "article", "name", "category_id",
    "price", "stock_quantity", "status", "is_active",
):
    out.append([p["pk"], p["code_1c"] or "", p["article"] or "", p["name"] or "",
                p["category_id"], str(p["price"]), str(p["stock_quantity"]),
                p["status"], p["is_active"]])
blob = json.dumps(out, ensure_ascii=False).encode("utf-8")
path = os.environ.get("CAT09_PROJ", "/tmp/cat09-proj.json")
with io.open(path, "wb") as f:
    f.write(blob)
print("rows=%d sha256=%s file=%s" % (len(out), hashlib.sha256(blob).hexdigest(), path))
