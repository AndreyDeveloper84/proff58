"""ХАР-03: read-only предсказание diff load_attributes на стенде.

НИЧЕГО не пишет в БД. Запуск: manage.py shell < har03_predict_load_attributes.py
или python manage.py runscript через shell -c "exec(open(...).read())".
"""
import json
from pathlib import Path

from apps.catalog.ingest import data_dir
from apps.catalog.models import Attribute, AttributeOption, Category

SAFE_FIELDS = ("unit", "is_filterable", "is_ai_feature")

base = data_dir()
data = json.loads(Path(f"{base}/attribute_rules.json").read_text(encoding="utf-8"))

report = {
    "attributes": {"total_slugs": 0, "existing": [], "missing": [], "will_change": []},
    "options": {"total_select_attrs": 0, "total_option_pairs": 0, "slug_mismatches": []},
    "category_binding": {"names": []},
    "summary": {},
}

# ---------- 1. Attribute ----------
slug_to_rule = {}
for tt in data.get("tool_types", []):
    for a in tt.get("attributes", []):
        slug_to_rule[a["slug"]] = a  # last write wins if slug repeated across tool_types

report["attributes"]["total_slugs"] = len(slug_to_rule)

existing_attrs = {a.slug: a for a in Attribute.objects.filter(slug__in=slug_to_rule.keys())}
for slug, rule in slug_to_rule.items():
    if slug not in existing_attrs:
        report["attributes"]["missing"].append(slug)
        continue
    report["attributes"]["existing"].append(slug)
    attr = existing_attrs[slug]
    new_values = {
        "unit": rule.get("unit", ""),
        "is_filterable": rule.get("is_filter", True),
        "is_ai_feature": rule.get("is_ai_feature", False),
    }
    changed = {
        f: {"old": getattr(attr, f), "new": new_values[f]}
        for f in SAFE_FIELDS
        if getattr(attr, f) != new_values[f]
    }
    if changed:
        report["attributes"]["will_change"].append({"slug": slug, "changes": changed})

# ---------- 2. AttributeOption ----------
select_pairs = []  # (attr_slug, value, rule_slug)
for tt in data.get("tool_types", []):
    for a in tt.get("attributes", []):
        if a["kind"] == "select":
            for opt in a.get("options", []):
                select_pairs.append((a["slug"], opt["value"], opt.get("slug", "")))

select_attr_slugs = {a["slug"] for tt in data.get("tool_types", []) for a in tt.get("attributes", []) if a["kind"] == "select"}
report["options"]["total_select_attrs"] = len(select_attr_slugs)
report["options"]["total_option_pairs"] = len(select_pairs)

db_options = {}  # (attr_slug, value) -> AttributeOption
for opt in AttributeOption.objects.filter(attribute__slug__in=select_attr_slugs).select_related("attribute"):
    db_options[(opt.attribute.slug, opt.value)] = opt

created_pairs = 0
mismatched = []
matched_same_slug = 0
for attr_slug, value, rule_slug in select_pairs:
    key = (attr_slug, value)
    db_opt = db_options.get(key)
    if db_opt is None:
        created_pairs += 1
        continue
    if db_opt.slug != rule_slug:
        mismatched.append(
            {
                "attribute": attr_slug,
                "value": value,
                "db_slug": db_opt.slug,
                "rule_slug": rule_slug,
            }
        )
    else:
        matched_same_slug += 1

report["options"]["will_create"] = created_pairs
report["options"]["slug_mismatches"] = mismatched
report["options"]["matched_same_slug"] = matched_same_slug

# ---------- 3. CategoryAttribute / _bind_category ----------
category_names = []
seen = set()
for tt in data.get("tool_types", []):
    name = tt.get("category")
    if name and name not in seen:
        seen.add(name)
        category_names.append(name)

for name in category_names:
    qs = Category.objects.filter(name=name)
    cands = list(qs.values("id", "depth"))
    depth1 = [c for c in cands if c["depth"] == 1]
    if depth1:
        chosen = depth1[0]
        rule = "depth==1 first()"
    elif len(cands) == 1:
        chosen = cands[0]
        rule = "unique match"
    else:
        chosen = None
        rule = "WARNING: not found / ambiguous"
    # ХАР-03B: попадает ли выбор _bind_category на живой v2-узел витрины
    # (is_active/on_site/is_site_v2) — исходный скрипт этого не проверял,
    # только воспроизводил bound/WARNING исход самой команды.
    chosen_is_live_v2 = None
    if chosen is not None:
        cat_obj = Category.objects.get(pk=chosen["id"])
        chosen_is_live_v2 = bool(
            cat_obj.is_active and cat_obj.on_site and cat_obj.is_site_v2
        )
        chosen["is_active"] = cat_obj.is_active
        chosen["on_site"] = cat_obj.on_site
        chosen["is_site_v2"] = cat_obj.is_site_v2
        chosen["slug"] = cat_obj.slug
    report["category_binding"]["names"].append(
        {
            "name": name,
            "candidates": cands,
            "chosen": chosen,
            "rule": rule,
            "chosen_is_live_v2": chosen_is_live_v2,
        }
    )

# ---------- 4/5. Summary ----------
bound_ok = sum(1 for x in report["category_binding"]["names"] if x["chosen"] is not None)
bound_warn = len(report["category_binding"]["names"]) - bound_ok
bound_live_v2 = sum(
    1 for x in report["category_binding"]["names"] if x["chosen_is_live_v2"]
)

report["summary"] = {
    "attributes_created": len(report["attributes"]["missing"]),
    "attributes_changed": len(report["attributes"]["will_change"]),
    "attributes_unchanged": len(report["attributes"]["existing"]) - len(report["attributes"]["will_change"]),
    "options_created": created_pairs,
    "options_slug_mismatch_will_overwrite": len(mismatched),
    "options_matched_no_change": matched_same_slug,
    "category_bindings_ok": bound_ok,
    "category_bindings_warning": bound_warn,
    "category_bindings_live_v2": bound_live_v2,
    "fail_closed_fully_resolved": len(report["attributes"]["missing"]) == 0,
}

out_path = "/app/var/har03_report.json"
Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("WRITTEN:", out_path)
print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
