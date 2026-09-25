# -*- coding: utf-8 -*-
"""CAT-05 · задача 2: привязки krugi (disc_diameter, bore, disc_type). Dry/write/rollback.

Режим через CAT05_MODE: dry (по умолчанию) | write | rollback.
Write — одна транзакция, fail-closed: атрибуты должны существовать и быть is_filterable,
строк не должно быть, категория — та самая. Rollback — по снимку CAT05_ROLLBACK (JSON
с created_ids). Флаги строк — зеркало соседних узлов (lepestkovye/shlifovalnye-zachistnye).
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from django.db import transaction  # noqa: E402

from apps.catalog.models import Attribute, Category, CategoryAttribute  # noqa: E402

CAT_SLUG = "krugi"
# (attribute_slug, is_filter, group, is_seo_facet, sort_order) — как у соседних узлов
ROWS = [
    ("disc_diameter", True, "main", False, 0),
    ("bore", True, "main", False, 0),
    ("disc_type", True, "main", True, 0),
]

MODE = os.environ.get("CAT05_MODE", "dry")
cat = Category.objects.get(slug=CAT_SLUG)
assert cat.get_parent().slug == "osnastka", f"неожиданный родитель: {cat.get_parent().slug}"

attrs = {}
for slug, *_ in ROWS:
    a = Attribute.objects.filter(slug=slug).first()
    assert a is not None, f"Attribute {slug} отсутствует — стоп (создавать запрещено)"
    assert a.is_filterable, f"Attribute {slug} не is_filterable — стоп"
    attrs[slug] = a

existing = list(CategoryAttribute.objects.filter(category=cat).values_list("attribute__slug", flat=True))

if MODE == "dry":
    assert not existing, f"у krugi уже есть CA: {existing} — стоп"
    for slug, is_filter, group, seo, sort in ROWS:
        print("DRY create:", cat.slug, "→", slug, is_filter, group, seo, sort)
    print("DRY-RUN: записи нет (CAT05_MODE!=write)")

elif MODE == "write":
    assert not existing, f"у krugi уже есть CA: {existing} — стоп"
    created = []
    with transaction.atomic():
        for slug, is_filter, group, seo, sort in ROWS:
            ca = CategoryAttribute.objects.create(
                category=cat,
                attribute=attrs[slug],
                is_filter=is_filter,
                group=group,
                is_seo_facet=seo,
                sort_order=sort,
            )
            created.append(ca.pk)
    snap = os.environ.get("CAT05_SNAPSHOT", "/tmp/cat05_rollback.json")
    io.open(snap, "w", encoding="utf-8").write(
        json.dumps({"created_ids": created}, ensure_ascii=False)
    )
    print("WROTE created_ids:", created, "snapshot:", snap)

elif MODE == "rollback":
    snap = json.load(open(os.environ["CAT05_ROLLBACK"], encoding="utf-8"))
    ids = snap["created_ids"]
    with transaction.atomic():
        n, _ = CategoryAttribute.objects.filter(id__in=ids, category=cat).delete()
    print("ROLLBACK deleted:", n, "of", ids)

else:
    raise SystemExit(f"unknown CAT05_MODE={MODE}")
