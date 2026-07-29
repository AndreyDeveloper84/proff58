# -*- coding: utf-8 -*-
"""CAT-09 S1 (смазки): драйвер записи — precheck → write (одна transaction.atomic)
→ postcheck. По плейбуку recategorize.md и маршруту TT-08.

Меняется ТОЛЬКО PAV.value_option + точечный attrs_cache. source не трогаем
(решение владельца в TT-08: оставить как есть — здесь все 88 записей manual).

Запуск (в контейнере web):
  docker exec -i -e FEATURE_CATALOG_PROCESSING=True proff58_staging-web-1 \
    python manage.py shell -c "exec(open('/tmp/cat09_s1_batch.py', encoding='utf-8').read())"
"""
from __future__ import annotations

import io
import json

from django.db import transaction

from apps.catalog.models import Product, ProductAttributeValue
from apps.catalog.read_models import rebuild_attrs_cache

rollback = json.load(io.open("/tmp/cat09-s4-rollback.json", encoding="utf-8"))
ids = sorted(int(pid) for pid in rollback)

# FP-guard: текущее состояние каждого товара == ожидаемое «старое»
errors = []
for pid in ids:
    rb = rollback[str(pid)]
    pav = ProductAttributeValue.objects.filter(
        product_id=pid, attribute__slug="tool_type"
    ).first()
    cur = pav.value_option_id if pav else None
    if cur != rb["old_option_id"]:
        errors.append(f"{pid}: current option {cur} != expected old {rb['old_option_id']}")
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
print(f"BATCH S4: moved={moved}, postcheck ok ({len(ids)} типов + attrs_cache)")
