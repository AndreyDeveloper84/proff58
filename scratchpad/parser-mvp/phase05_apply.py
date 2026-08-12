# -*- coding: utf-8 -*-
"""Phase 0.5 scoped write: характеристики перфораторов из названий.

APPLY=0 (по умолчанию) — dry-run: план + rollback-map, БЕЗ записи.
APPLY=1 — запись в одной transaction.atomic после guard-assert.

Scope: строго товары с tool_type=perforatory (ожидается 188), только атрибуты
правил perforatory. tool_type/цена/остаток/категория/название не трогаются.
"""
import hashlib
import json
import os
from decimal import Decimal

from django.db import transaction

from apps.catalog.attribute_extract import BOOLEAN, NUMBER, SELECT, AttributeRules
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    ImportRun,
    ImportRunStatus,
    Product,
    ProductAttributeValue,
)
from apps.catalog.read_models import build_attrs_cache
from django.utils import timezone

TT = "perforatory"
APPLY = os.environ.get("APPLY") == "1"
EXPECTED_N = 188
PRUNABLE = {"regex", "keyword", "inferred"}
SOURCE_CONFIDENCE = {"manual": 100, "import_1c": 100, "regex": 100, "keyword": 90, "llm": 60,
                     "inferred": 100}
VALUE_FIELDS = ["value_text", "value_integer", "value_decimal", "value_boolean", "value_option"]

base = os.environ.get("RULES_PATH")
raw = json.loads(open(f"{base}/attribute_rules.json", encoding="utf-8").read())
rules = AttributeRules.from_dict(raw)
priority = rules.source_priority
managed = {a["slug"] for tt in raw["tool_types"] if tt["tool_type"] == TT for a in tt["attributes"]}

pids = sorted(
    ProductAttributeValue.objects.filter(
        attribute__slug="tool_type", value_option__slug=TT
    ).values_list("product_id", flat=True)
)

# ---------- guard-assert (до любой записи) ----------
assert len(pids) == EXPECTED_N, f"scope изменился: {len(pids)} != {EXPECTED_N}"
assert "tool_type" not in managed, "tool_type не должен быть в управляемых атрибутах"
prods = {p.id: p for p in Product.objects.filter(id__in=pids)}
assert all(p.category_id == 3 for p in prods.values()), "есть товары вне cat=3"
assert not any(p.content_locked for p in prods.values()), "есть content_locked=True"

attr_by_slug = {a.slug: a for a in Attribute.objects.filter(slug__in=managed)}
missing = managed - set(attr_by_slug)
assert not missing, f"нет Attribute: {sorted(missing)}"

option_index = {}
for opt in AttributeOption.objects.filter(attribute__slug__in=managed).select_related("attribute"):
    option_index.setdefault(opt.attribute.slug, {})[opt.slug] = opt

existing = {}
for pav in ProductAttributeValue.objects.filter(
    product_id__in=pids, attribute__slug__in=managed
).select_related("attribute", "value_option"):
    existing[(pav.product_id, pav.attribute.slug)] = pav

manual_like = [
    (k[0], k[1], p.source) for k, p in existing.items() if p.source not in PRUNABLE
]
assert not manual_like, f"есть авторитетные значения (manual/1С/llm): {manual_like[:10]}"

# ---------- снимок «неприкасаемых» полей ----------
def untouched_hash():
    h = hashlib.sha256()
    for pid in pids:
        p = Product.objects.get(id=pid)
        tt = (
            ProductAttributeValue.objects.filter(product_id=pid, attribute__slug="tool_type")
            .values_list("value_option__slug", flat=True)
            .first()
        )
        h.update(
            f"{pid}|{p.code_1c}|{p.article}|{p.name}|{p.original_name}|{p.category_id}|"
            f"{p.price}|{p.stock_quantity}|{p.available_quantity}|{p.status}|{p.is_active}|"
            f"{p.slug}|{tt}\n".encode()
        )
    return h.hexdigest()


UNTOUCHED_BEFORE = untouched_hash()

# ---------- план ----------
def pav_snapshot(pav):
    return {
        "attr": pav.attribute.slug,
        "source": pav.source,
        "confidence": pav.confidence,
        "text": pav.value_text,
        "int": pav.value_integer,
        "dec": str(pav.value_decimal) if pav.value_decimal is not None else None,
        "bool": pav.value_boolean,
        "opt": pav.value_option.slug if pav.value_option else None,
    }


rollback = {str(pid): [] for pid in pids}
for (pid, slug), pav in existing.items():
    rollback[str(pid)].append(pav_snapshot(pav))

plan = {"create": [], "update": [], "delete": [], "skip_priority": []}
to_create, to_update, to_delete = [], [], []
touched = set()

for pid in pids:
    product = prods[pid]
    name = product.original_name or product.name
    values = rules.extract(TT, name)
    current = {v.slug for v in values}

    for slug in managed:
        if slug in current:
            continue
        pav = existing.get((pid, slug))
        if pav is None or pav.source not in PRUNABLE:
            continue
        to_delete.append(pav.pk)
        plan["delete"].append([pid, slug, pav.source])
        touched.add(pid)

    for av in values:
        option = None
        if av.kind == SELECT:
            option = option_index.get(av.slug, {}).get(av.option_slug)
            if option is None:
                continue
        val = str(av.number) if av.number is not None else (av.option_slug or av.boolean)
        pav = existing.get((pid, av.slug))
        if pav is None:
            pav = ProductAttributeValue(
                product=product,
                attribute=attr_by_slug[av.slug],
                source=av.source,
                confidence=SOURCE_CONFIDENCE.get(av.source, 100),
            )
        else:
            if priority.get(av.source, 0) < priority.get(pav.source, 0):
                plan["skip_priority"].append([pid, av.slug])
                continue
            old = pav_snapshot(pav)
            new_repr = {"source": av.source, "val": str(val)}
            same = (
                old["source"] == av.source
                and (
                    (old["dec"] is not None and Decimal(old["dec"]) == av.number)
                    if av.kind == NUMBER
                    else True
                )
                and (old["opt"] == av.option_slug if av.kind == SELECT else True)
                and (old["bool"] == av.boolean if av.kind == BOOLEAN else True)
            )
            if same:
                continue
            plan["update"].append([pid, av.slug, old, new_repr])
            pav.source = av.source
            pav.confidence = SOURCE_CONFIDENCE.get(av.source, 100)

        pav.value_text = ""
        pav.value_integer = None
        pav.value_decimal = None
        pav.value_boolean = None
        pav.value_option = None
        if av.kind == NUMBER:
            pav.value_decimal = av.number
        elif av.kind == SELECT:
            pav.value_option = option
        elif av.kind == BOOLEAN:
            pav.value_boolean = av.boolean

        if pav.pk is None:
            to_create.append(pav)
            plan["create"].append([pid, av.slug, str(val), av.source])
        else:
            to_update.append(pav)
        touched.add(pid)

summary = {
    "apply": APPLY,
    "scope": len(pids),
    "PLAN_CREATE": len(plan["create"]),
    "PLAN_UPDATE": len(plan["update"]),
    "PLAN_DELETE": len(plan["delete"]),
    "PLAN_SKIP_PRIORITY": len(plan["skip_priority"]),
    "touched_products": len(touched),
    "untouched_hash_before": UNTOUCHED_BEFORE,
}

if not APPLY:
    print("===JSON===")
    print(json.dumps({"summary": summary, "plan": plan, "rollback": rollback}, ensure_ascii=False,
                     default=str))
    print("===END===")
else:
    run = ImportRun.objects.create(source="phase05_perforatory")
    with transaction.atomic():
        if to_delete:
            ProductAttributeValue.objects.filter(id__in=to_delete).delete()
        if to_create:
            ProductAttributeValue.objects.bulk_create(to_create, batch_size=500)
        if to_update:
            ProductAttributeValue.objects.bulk_update(
                to_update, VALUE_FIELDS + ["source", "confidence"], batch_size=500
            )
        # attrs_cache только по затронутым товарам (scoped-эквивалент rebuild_attrs_cache)
        refreshed = list(
            Product.objects.filter(id__in=sorted(touched)).prefetch_related(
                "attribute_values__attribute", "attribute_values__value_option"
            )
        )
        for p in refreshed:
            p.attrs_cache = build_attrs_cache(p)
        Product.objects.bulk_update(refreshed, ["attrs_cache"], batch_size=500)

    after = untouched_hash()
    assert after == UNTOUCHED_BEFORE, "ИЗМЕНИЛИСЬ неприкасаемые поля!"
    summary["untouched_hash_after"] = after
    run.status = ImportRunStatus.DONE
    run.finished_at = timezone.now()
    run.stats = summary
    run.save()
    print("===JSON===")
    print(json.dumps({"summary": summary, "run_id": run.pk}, ensure_ascii=False, default=str))
    print("===END===")
