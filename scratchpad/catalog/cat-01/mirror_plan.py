# -*- coding: utf-8 -*-
"""CAT-01: read-only зеркало логики enrich_attributes.

Считает план CREATE / UPDATE / PRUNE / SKIP_PRIORITY без записи в БД.
Запуск: python manage.py shell < mirror_plan.py  (env RULES_PATH — каталог со
словарём attribute_rules.json; по умолчанию data/).

Логика повторяет apps/catalog/management/commands/enrich_attributes.py:
- scope: товары, чей tool_type (PAV value_option.slug) входит в словарь;
- CREATE: движок извлёк значение, PAV нет;
- UPDATE: PAV есть, приоритет позволяет, значение ОТЛИЧАЕТСЯ (same-value
  перезаписи команды — не считаются обновлением);
- PRUNE: PAV с prunable-источником (regex/keyword/inferred), атрибут управляемый,
  движок значение больше не извлекает;
- SKIP_PRIORITY: приоритет нового источника ниже сохранённого.
"""
import json
import os
from decimal import Decimal

from apps.catalog.attribute_extract import BOOLEAN, NUMBER, SELECT, AttributeRules
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    Product,
    ProductAttributeValue,
)

PRUNABLE = {"regex", "keyword", "inferred"}
TOOL_TYPE_SLUG = "tool_type"

base = os.environ.get("RULES_PATH") or "data"
raw = json.loads(open(f"{base}/attribute_rules.json", encoding="utf-8").read())
rules = AttributeRules.from_dict(raw)
priority = rules.source_priority

tt_slugs = [tt["tool_type"] for tt in raw.get("tool_types", [])]
managed_slugs = {a["slug"] for tt in raw.get("tool_types", []) for a in tt["attributes"]}
managed_by_tt = {
    tt["tool_type"]: {a["slug"] for a in tt["attributes"]} for tt in raw.get("tool_types", [])
}

attr_by_slug = {a.slug: a for a in Attribute.objects.filter(slug__in=managed_slugs)}
missing = managed_slugs - set(attr_by_slug)
if missing:
    # Команда enrich_attributes здесь падает («сначала load_attributes»).
    # Для read-only замера исключаем отсутствующие из управляемых и рапортуем.
    managed_slugs -= missing
    managed_by_tt = {tt: slugs - missing for tt, slugs in managed_by_tt.items()}

option_index = {}
for opt in AttributeOption.objects.filter(attribute__slug__in=managed_slugs).select_related(
    "attribute"
):
    option_index.setdefault(opt.attribute.slug, {})[opt.slug] = opt

product_tt = {
    row["product_id"]: row["value_option__slug"]
    for row in ProductAttributeValue.objects.filter(
        attribute__slug=TOOL_TYPE_SLUG,
        value_option__isnull=False,
        value_option__slug__in=tt_slugs,
    ).values("product_id", "value_option__slug")
}
product_ids = sorted(product_tt)

existing = {}
for pav in ProductAttributeValue.objects.filter(
    product_id__in=product_ids, attribute__slug__in=managed_slugs
).select_related("attribute", "value_option"):
    existing[(pav.product_id, pav.attribute.slug)] = pav

published = set(
    Product.objects.filter(id__in=product_ids, status="published", is_active=True)
    .values_list("id", flat=True)
)
names = {
    pid: (orig, name)
    for pid, orig, name in Product.objects.filter(id__in=product_ids).values_list(
        "id", "original_name", "name"
    )
}

plan = {"create": [], "update": [], "prune": [], "skip_priority": []}

for pid in product_ids:
    tt_slug = product_tt[pid]
    original, name = names[pid]
    full_name = original or name
    values = rules.extract(tt_slug, full_name)
    current = {av.slug for av in values}

    for slug in managed_by_tt.get(tt_slug, ()):
        if slug in current:
            continue
        pav = existing.get((pid, slug))
        if pav is None or pav.source not in PRUNABLE:
            continue
        plan["prune"].append(
            {"pid": pid, "tt": tt_slug, "attr": slug, "source": pav.source,
             "pub": pid in published}
        )

    for av in values:
        option = None
        if av.kind == SELECT:
            option = option_index.get(av.slug, {}).get(av.option_slug)
            if option is None:
                continue
        pav = existing.get((pid, av.slug))
        if pav is None:
            val = (
                str(av.number)
                if av.kind == NUMBER
                else (av.option_slug if av.kind == SELECT else av.boolean)
            )
            plan["create"].append(
                {"pid": pid, "tt": tt_slug, "attr": av.slug, "val": str(val),
                 "source": av.source, "pub": pid in published, "name": full_name}
            )
            continue
        if priority.get(av.source, 0) < priority.get(pav.source, 0):
            plan["skip_priority"].append({"pid": pid, "tt": tt_slug, "attr": av.slug})
            continue
        if av.kind == NUMBER:
            same = pav.value_decimal is not None and Decimal(pav.value_decimal) == av.number
            old = str(pav.value_decimal)
            new = str(av.number)
        elif av.kind == SELECT:
            old = pav.value_option.slug if pav.value_option else None
            same = old == av.option_slug
            new = av.option_slug
        else:  # BOOLEAN
            same = pav.value_boolean == av.boolean
            old = pav.value_boolean
            new = av.boolean
        if not same:
            plan["update"].append(
                {"pid": pid, "tt": tt_slug, "attr": av.slug, "old": str(old),
                 "new": str(new), "old_source": pav.source, "new_source": av.source,
                 "pub": pid in published, "name": full_name}
            )


def breakdown(items):
    out = {}
    for it in items:
        key = (it["attr"], it["tt"])
        row = out.setdefault(key, {"n": 0, "pub": 0})
        row["n"] += 1
        row["pub"] += 1 if it.get("pub") else 0
    return {f"{a}|{t}": v for (a, t), v in sorted(out.items())}


summary = {
    "missing_attributes": sorted(missing),
    "scope_products": len(product_ids),
    "CREATE": len(plan["create"]),
    "CREATE_pub": sum(1 for i in plan["create"] if i["pub"]),
    "UPDATE": len(plan["update"]),
    "PRUNE": len(plan["prune"]),
    "SKIP_PRIORITY": len(plan["skip_priority"]),
    "create_by_attr_tt": breakdown(plan["create"]),
    "update_by_attr_tt": breakdown(plan["update"]),
    "prune_by_attr_tt": breakdown(plan["prune"]),
}

print("===JSON===")
print(json.dumps({"summary": summary, "plan": plan}, ensure_ascii=False, default=str))
print("===END===")
