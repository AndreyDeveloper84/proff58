# -*- coding: utf-8 -*-
"""CAT-06 · задача 2b: привязки панелей elektrody×diameter, malyarnyy-instrument×length.

Режим CAT06_MODE: dry (по умолчанию) | write | rollback. Write — одна транзакция,
fail-closed. Критерий CAT-02 подтверждён на копии: 141/160 (88.1%) и 39/94 (41.5%).
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from django.db import transaction  # noqa: E402

from apps.catalog.models import Attribute, Category, CategoryAttribute  # noqa: E402

# (category_slug, attribute_slug, is_filter, group, is_seo_facet, sort_order)
ROWS = [
    ("elektrody", "diameter", True, "main", False, 0),
    ("malyarnyy-instrument", "length", True, "main", False, 0),
]

MODE = os.environ.get("CAT06_MODE", "dry")

for cat_slug, attr_slug, *_ in ROWS:
    a = Attribute.objects.filter(slug=attr_slug).first()
    assert a is not None and a.is_filterable, f"Attribute {attr_slug} — стоп"

existing = list(
    CategoryAttribute.objects.filter(
        category__slug__in=[r[0] for r in ROWS]
    ).values_list("category__slug", "attribute__slug")
)

if MODE == "dry":
    assert not existing, f"строки уже есть: {existing} — стоп"
    for r in ROWS:
        print("DRY create:", r)
    print("DRY-RUN: записи нет (CAT06_MODE!=write)")

elif MODE == "write":
    assert not existing, f"строки уже есть: {existing} — стоп"
    created = []
    with transaction.atomic():
        for cat_slug, attr_slug, is_filter, group, seo, sort in ROWS:
            ca = CategoryAttribute.objects.create(
                category=Category.objects.get(slug=cat_slug),
                attribute=Attribute.objects.get(slug=attr_slug),
                is_filter=is_filter,
                group=group,
                is_seo_facet=seo,
                sort_order=sort,
            )
            created.append(ca.pk)
    snap = os.environ.get("CAT06_SNAPSHOT", "/tmp/cat06_rollback.json")
    io.open(snap, "w", encoding="utf-8").write(json.dumps({"created_ids": created}))
    print("WROTE created_ids:", created, "snapshot:", snap)

elif MODE == "rollback":
    snap = json.load(open(os.environ["CAT06_ROLLBACK"], encoding="utf-8"))
    with transaction.atomic():
        n, _ = CategoryAttribute.objects.filter(id__in=snap["created_ids"]).delete()
    print("ROLLBACK deleted:", n, "of", snap["created_ids"])

else:
    raise SystemExit(f"unknown CAT06_MODE={MODE}")
