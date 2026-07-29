"""TT-08 · драйвер батча: precheck → write (одна transaction.atomic) → postcheck.

Запуск: BATCH=G1 manage.py shell -c "exec(open('scratchpad/phase8/tt08_batch.py', encoding='utf-8').read())"

Write — по плейбуку recategorize.md: bulk-обновление PAV (только value_option)
+ точечная пересборка attrs_cache. source НЕ меняется (решение владельца:
оставить manual). Категория, цена, остаток, публикация — вне досягаемости.
"""

from __future__ import annotations

import io
import json
import os

from django.db import transaction

from apps.catalog.models import Product, ProductAttributeValue
from apps.catalog.read_models import rebuild_attrs_cache

BATCH = os.environ["BATCH"]
lists = json.load(io.open("scratchpad/phase8/tt-08-lists.json", encoding="utf-8"))
rollback = json.load(io.open("scratchpad/phase8/artifacts-tt08/rollback-map.json", encoding="utf-8"))
spec = next(b for b in lists["batches"] if b["batch"] == BATCH)
ids = spec["ids"]
plan = {int(pid): spec["map"][str(pid)] for pid in ids}

# FP-guard: текущее состояние каждого товара == ожидаемое «старое» из rollback-map
errors = []
for pid in ids:
    rb = rollback.get(str(pid))
    if rb is None:
        errors.append(f"{pid}: нет в rollback-map")
        continue
    pav = ProductAttributeValue.objects.filter(product_id=pid, attribute__slug="tool_type").first()
    cur = pav.value_option_id if pav else None
    if cur != rb["old_option_id"]:
        errors.append(f"{pid}: current option {cur} != expected old {rb['old_option_id']}")
    if rb["new_slug"] != plan[pid]:
        errors.append(f"{pid}: rollback new {rb['new_slug']} != plan {plan[pid]}")
if errors:
    raise SystemExit("FP-guard FAILED:\n" + "\n".join(errors))
print(f"FP-guard ok: {len(ids)} товаров, текущие типы == ожидаемым")

moved = 0
with transaction.atomic():
    for pid in ids:
        rb = rollback[str(pid)]
        pav = ProductAttributeValue.objects.select_for_update().get(
            product_id=pid, attribute__slug="tool_type"
        )
        pav.value_option_id = rb["new_option_id"]  # source/confidence не трогаем
        pav.save(update_fields=["value_option"])
        product = Product.objects.get(pk=pid)
        rebuild_attrs_cache(product)
        moved += 1

# postcheck: тип == новый, attrs_cache ≡ EAV, дублей нет
bad = []
for pid in ids:
    rb = rollback[str(pid)]
    pav = ProductAttributeValue.objects.filter(product_id=pid, attribute__slug="tool_type")
    if pav.count() != 1:
        bad.append(f"{pid}: PAV rows={pav.count()}")
        continue
    row = pav.first()
    if row.value_option_id != rb["new_option_id"]:
        bad.append(f"{pid}: option {row.value_option_id} != {rb['new_option_id']}")
    cached = (Product.objects.get(pk=pid).attrs_cache or {}).get("tool_type")
    if cached != row.value_option.value:
        bad.append(f"{pid}: attrs_cache {cached!r} != {row.value_option.value!r}")
if bad:
    raise SystemExit("postcheck FAILED:\n" + "\n".join(bad))
print(f"BATCH {BATCH}: moved={moved}, postcheck ok ({len(ids)} типов + attrs_cache)")
