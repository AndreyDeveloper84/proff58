# -*- coding: utf-8 -*-
"""CAT-08 · задача 3: write — переименование по rollback-map батчами. Dry/write.

Режим CAT08_MODE: dry | write.
Write: батчи по CAT08_BATCH (default 450), каждый одна transaction.atomic,
bulk_update ТОЛЬКО по полю name, fail-closed: текущее имя обязано совпадать
с map.old (иначе стоп — кто-то изменил имя между планом и записью).
Карта читается из CAT08_MAP (rollback-map, создана dry-run'ом до записи).
"""
import json
import os
import sys

sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from django.db import transaction  # noqa: E402

from apps.catalog.models import Product  # noqa: E402

MODE = os.environ.get("CAT08_MODE", "dry")
BATCH = int(os.environ.get("CAT08_BATCH", "450"))
MAP = os.environ.get("CAT08_MAP", "/tmp/cat08_rollback_map.json")
plan = json.load(open(MAP, encoding="utf-8"))
print("map строк:", len(plan), "| batch:", BATCH, "| mode:", MODE)

if MODE == "dry":
    sample = plan[:5]
    for s in sample:
        print("  DRY:", s["pid"], repr(s["old"])[:50], "->", repr(s["new"])[:50])
    print("DRY-RUN: записи нет")
elif MODE == "write":
    done = 0
    for i in range(0, len(plan), BATCH):
        chunk = plan[i : i + BATCH]
        with transaction.atomic():
            products = {p.id: p for p in Product.objects.filter(id__in=[c["pid"] for c in chunk])}
            assert len(products) == len(chunk), f"batch {i}: найдено {len(products)} из {len(chunk)} — стоп"
            for c in chunk:
                p = products[c["pid"]]
                assert p.name == c["old"], (
                    f"pid {c['pid']}: имя изменилось с плана {c['old']!r} -> {p.name!r} — стоп"
                )
                p.name = c["new"]
            Product.objects.bulk_update(products.values(), ["name"], batch_size=BATCH)
        done += len(chunk)
        print(f"  batch {i // BATCH + 1}: +{len(chunk)} (итого {done})")
    print("WROTE:", done)
else:
    raise SystemExit(f"unknown CAT08_MODE={MODE}")
