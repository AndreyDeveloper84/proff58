# -*- coding: utf-8 -*-
"""CAT-04: post-audit затронутого множества (задача 2). READ-ONLY.

Проверяет по плану (/tmp/cat04_plan.json = scoped-план):
  * каждый CREATE существует с ожидаемым значением/источником;
  * каждый PRUNE отсутствует;
  * у 20 затронутых товаров attrs_cache согласован с EAV по затронутым атрибутам.
"""
import io
import json
import sys
from decimal import Decimal

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402

plan = json.load(open("/tmp/cat04_plan.json", encoding="utf-8"))
errors = []

for it in plan["plan"]["create"]:
    pav = PAV.objects.filter(product_id=it["pid"], attribute__slug=it["attr"]).first()
    if pav is None:
        errors.append(f"CREATE {it}: PAV отсутствует")
        continue
    if pav.value_decimal is not None:
        got = str(pav.value_decimal.normalize())
    elif pav.value_option:
        got = pav.value_option.slug
    else:
        got = pav.value_text
    if got != it["val"] or pav.source != it["source"]:
        errors.append(f"CREATE {it}: got val={got} src={pav.source}")
    print("CREATE ok:", it["pid"], it["attr"], got, pav.source)

for it in plan["plan"]["prune"]:
    if PAV.objects.filter(product_id=it["pid"], attribute__slug=it["attr"]).exists():
        errors.append(f"PRUNE {it}: PAV на месте")
print("PRUNE: все 17 отсутствуют —", "OK" if not any("PRUNE" in e for e in errors) else "FAIL")

# attrs_cache ≡ EAV по затронутым атрибутам у затронутых товаров
pids = sorted({it["pid"] for it in plan["plan"]["create"] + plan["plan"]["prune"]})
attrs = sorted({it["attr"] for it in plan["plan"]["create"] + plan["plan"]["prune"]})
mism = 0
for p in Product.objects.filter(id__in=pids):
    cache = p.attrs_cache or {}
    eav = {}
    for pav in PAV.objects.filter(product=p, attribute__slug__in=attrs).select_related(
        "attribute", "value_option"
    ):
        if pav.value_decimal is not None:
            eav[pav.attribute.slug] = float(pav.value_decimal)
        elif pav.value_option:
            eav[pav.attribute.slug] = pav.value_option.value
        elif pav.value_text:
            eav[pav.attribute.slug] = pav.value_text
    for a in attrs:
        in_cache = a in cache
        in_eav = a in eav
        if in_cache != in_eav:
            mism += 1
            errors.append(f"cache/eav наличие: pid={p.id} attr={a} cache={in_cache} eav={in_eav}")
        elif in_eav:
            cv = cache[a]
            if isinstance(cv, (int, float)) and isinstance(eav[a], float):
                same = Decimal(str(cv)) == Decimal(str(eav[a]))
            else:
                same = str(cv) == str(eav[a])
            if not same:
                mism += 1
                errors.append(f"cache/eav значение: pid={p.id} attr={a} cache={cv!r} eav={eav[a]!r}")
print(f"attrs_cache≡EAV по {len(pids)} товарам × {len(attrs)} атрибутам: mismatches={mism}")

print("=== ИТОГ:", "ЧИСТО" if not errors else f"{len(errors)} ОШИБОК")
for e in errors:
    print("ERR:", e)
