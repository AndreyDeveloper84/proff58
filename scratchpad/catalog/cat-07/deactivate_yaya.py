# -*- coding: utf-8 -*-
"""CAT-07 · деактивация яя-товаров (is_active=False). Dry/write/rollback.

Решение владельца: «яя — сделать все товары неактивными».
Цель: Product.objects.filter(name__istartswith='яя', is_active=True) — ровно они.
Меняется ТОЛЬКО is_active (status, цена, остаток, категория, PAV, attrs_cache — нет).
update() не шлёт сигналы — кэши инвалидируем явно.
Режим CAT07_MODE: dry (по умолчанию) | write | rollback (по снимку CAT07_ROLLBACK).
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from django.db import transaction  # noqa: E402

from apps.catalog.category_tree import invalidate_category_tree_cache  # noqa: E402
from apps.catalog.facets import invalidate_facets_cache  # noqa: E402
from apps.catalog.models import Product  # noqa: E402

MODE = os.environ.get("CAT07_MODE", "dry")
qs = Product.objects.filter(name__istartswith="яя", is_active=True)
n = qs.count()
print("целевых (name ~ 'яя*', is_active=True):", n)

if MODE == "dry":
    print("visible до:", Product.objects.filter(is_active=True, status="published").count())
    print("DRY-RUN: записи нет (CAT07_MODE!=write)")

elif MODE == "write":
    pids = list(qs.values_list("id", flat=True))
    with transaction.atomic():
        updated = Product.objects.filter(id__in=pids, is_active=True).update(is_active=False)
        assert updated == len(pids), f"partial update {updated} != {len(pids)} — стоп"
    snap = os.environ.get("CAT07_SNAPSHOT", "/tmp/cat07_rollback.json")
    io.open(snap, "w", encoding="utf-8").write(json.dumps({"pids": pids}))
    invalidate_facets_cache()
    invalidate_category_tree_cache()
    print("WROTE deactivated:", updated, "| snapshot:", snap)

elif MODE == "rollback":
    snap = json.load(open(os.environ["CAT07_ROLLBACK"], encoding="utf-8"))
    pids = snap["pids"]
    with transaction.atomic():
        updated = Product.objects.filter(id__in=pids, is_active=False).update(is_active=True)
        assert updated == len(pids), f"partial rollback {updated} != {len(pids)} — стоп"
    invalidate_facets_cache()
    invalidate_category_tree_cache()
    print("ROLLBACK re-activated:", updated)

else:
    raise SystemExit(f"unknown CAT07_MODE={MODE}")
