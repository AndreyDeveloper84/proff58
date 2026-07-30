# -*- coding: utf-8 -*-
"""CAT-08: контроль имён вне целевого множества — по фиксированному списку pid. READ-ONLY."""
import hashlib
import io
import json
import os

from apps.catalog.models import Product

plan = json.load(open(os.environ.get("CAT08_MAP", "/tmp/cat08_rollback_map.json"), encoding="utf-8"))
target_ids = [c["pid"] for c in plan]

hn = hashlib.sha256()
n = 0
for pid, name in Product.objects.exclude(id__in=target_ids).order_by("id").values_list("id", "name"):
    n += 1
    hn.update(json.dumps([pid, name], ensure_ascii=False).encode())
out = {"n": n, "fp": hn.hexdigest()}
io.open(os.environ.get("CAT08_OUT", "/tmp/cat08_names_out.json"), "w").write(json.dumps(out))
print("WROTE", out["n"], out["fp"][:16])
