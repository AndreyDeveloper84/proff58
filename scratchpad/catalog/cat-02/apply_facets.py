# -*- coding: utf-8 -*-
"""CAT-02: завести связи показа CategoryAttribute для izmeritelnyy/*.

Создаёт ТОЛЬКО строки CategoryAttribute (связи показа). Никогда не создаёт
Attribute/AttributeOption, не трогает значения характеристик, не трогает attrs_cache,
не трогает tool_type и дерево категорий — fail-closed при любом отклонении.

Режимы (env):
    CAT02_MODE=dry     — только план и предсказание (по умолчанию)
    CAT02_MODE=commit  — записать одной транзакцией
    CAT02_ROLLBACK=<файл> — удалить строки по снимку отката

Флаги is_filter/is_seo_facet взяты из data/attribute_rules.json (кураторский реестр),
group/sort_order — как во всех существующих строках каталога (main/0).
"""
import io
import json
import os

from django.db import transaction

from apps.catalog.category_tree import invalidate_category_tree_cache
from apps.catalog.facets import invalidate_facets_cache
from apps.catalog.models import Attribute, Category, CategoryAttribute

# (category_slug, attribute_slug, is_filter, is_seo_facet) — источник: data/attribute_rules.json
PLAN = [
    ("izmeritelnyy-ruletki", "tape_length", True, True),
    ("izmeritelnyy-ruletki", "tape_width", True, False),
    ("izmeritelnyy-urovni", "length", True, True),
    ("izmeritelnyy-shtangencirkuli-i-mikrometry", "measuring_range", True, True),
    ("izmeritelnyy-shtangencirkuli-i-mikrometry", "readout_type", True, True),
    ("izmeritelnyy-ugolniki-i-lineyki", "size", True, True),
    ("izmeritelnyy-dalnomery", "max_distance", True, True),
]

MODE = os.environ.get("CAT02_MODE", "dry")
# CAT02_ONLY=length,size — ограничить план подмножеством атрибутов (для БД, где часть
# Attribute отсутствует; создавать их нельзя — границы задачи).
ONLY = {s.strip() for s in os.environ.get("CAT02_ONLY", "").split(",") if s.strip()}
if ONLY:
    PLAN = [p for p in PLAN if p[1] in ONLY]
ROLLBACK = os.environ.get("CAT02_ROLLBACK")
SNAPSHOT = os.environ.get("CAT02_SNAPSHOT", "/tmp/cat02_rollback.json")

# ------------------------------------------------------------------ откат
if ROLLBACK:
    data = json.loads(io.open(ROLLBACK, encoding="utf-8").read())
    ids = data["created_ids"]
    with transaction.atomic():
        n, _ = CategoryAttribute.objects.filter(id__in=ids).delete()
        transaction.on_commit(invalidate_facets_cache)
        transaction.on_commit(invalidate_category_tree_cache)
    print(f"ROLLBACK: удалено {n} из {len(ids)} CategoryAttribute")
    raise SystemExit(0)

# ------------------------------------------------------- валидация (fail-closed)
errors = []
resolved = []
for cat_slug, attr_slug, is_filter, is_seo in PLAN:
    cat = Category.objects.filter(slug=cat_slug).first()
    if cat is None:
        errors.append(f"нет категории {cat_slug}")
        continue
    attr = Attribute.objects.filter(slug=attr_slug).first()
    if attr is None:
        errors.append(f"нет атрибута {attr_slug} — создавать НЕЛЬЗЯ (границы задачи)")
        continue
    if not attr.is_filterable:
        errors.append(f"{attr_slug}.is_filterable=False — менять НЕЛЬЗЯ (границы задачи)")
        continue
    exists = CategoryAttribute.objects.filter(category=cat, attribute=attr).first()
    resolved.append(
        {
            "cat_slug": cat_slug,
            "cat_id": cat.pk,
            "attr_slug": attr_slug,
            "attr_id": attr.pk,
            "attr_type": attr.attribute_type,
            "unit": attr.unit,
            "is_filter": is_filter,
            "is_seo_facet": is_seo,
            "action": "SKIP(уже есть)" if exists else "CREATE",
            "existing_id": exists.pk if exists else None,
            "descendants": cat.get_descendants().count(),
        }
    )

print("=== CAT-02 план связей показа (CategoryAttribute) ===")
for r in resolved:
    print(
        f"  {r['action']:14s} {r['cat_slug']:44s} {r['attr_slug']:16s} "
        f"type={r['attr_type']:8s} is_filter={r['is_filter']} seo={r['is_seo_facet']} "
        f"потомков={r['descendants']}"
    )
n_create = sum(1 for r in resolved if r["action"] == "CREATE")
n_skip = sum(1 for r in resolved if r["action"].startswith("SKIP"))
print(f"\nCREATE={n_create}  SKIP={n_skip}  UPDATE=0  DELETE=0")
if errors:
    print("\nОШИБКИ (запись запрещена):")
    for e in errors:
        print("  -", e)
    raise SystemExit(2)

if MODE != "commit":
    print("\nDRY-RUN: ничего не записано. Применить — CAT02_MODE=commit.")
    raise SystemExit(0)

# ------------------------------------------------------------------ запись
created_ids = []
with transaction.atomic():
    for r in resolved:
        if r["action"] != "CREATE":
            continue
        obj = CategoryAttribute.objects.create(
            category_id=r["cat_id"],
            attribute_id=r["attr_id"],
            is_required=False,
            is_filter=r["is_filter"],
            group="main",
            is_seo_facet=r["is_seo_facet"],
            sort_order=0,
        )
        created_ids.append(obj.pk)
    io.open(SNAPSHOT, "w", encoding="utf-8").write(
        json.dumps(
            {"task": "CAT-02", "created_ids": created_ids, "plan": resolved},
            ensure_ascii=False,
        )
    )
    transaction.on_commit(invalidate_facets_cache)
    transaction.on_commit(invalidate_category_tree_cache)

print(f"\nCOMMIT: создано {len(created_ids)} CategoryAttribute. Снимок отката: {SNAPSHOT}")
print("created_ids =", created_ids)
