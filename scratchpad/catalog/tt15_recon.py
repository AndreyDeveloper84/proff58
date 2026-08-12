"""TT-15 · read-only пересчёт периметра по стенду.

Запуск на стенде (внутри контейнера web):
    python manage.py shell -c "exec(open('/app/var/tt15_recon.py', encoding='utf-8').read())"

Ничего не пишет в БД. Агрегаты — в stdout, полные списки id — в /app/var/tt15/.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from django.db.models import Count, Q

from apps.catalog.models import Attribute, AttributeOption, Product, ProductAttributeValue

OUT = Path("/app/var/tt15")
OUT.mkdir(parents=True, exist_ok=True)

TOOL_TYPE = "tool_type"


def type_map(pids):
    """pid -> (slug | None, source | None)."""
    rows = ProductAttributeValue.objects.filter(
        attribute__slug=TOOL_TYPE, product_id__in=pids
    ).values("product_id", "value_option__slug", "source")
    m = {r["product_id"]: (r["value_option__slug"], r["source"]) for r in rows}
    return {pid: m.get(pid, (None, None)) for pid in pids}


print("=== 0. Словарь и PAV ===")
total_pav = ProductAttributeValue.objects.filter(attribute__slug=TOOL_TYPE).count()
print(f"PAV tool_type всего: {total_pav}")
attr = Attribute.objects.get(slug=TOOL_TYPE)
opts = {o.slug: o.id for o in AttributeOption.objects.filter(attribute=attr)}
for slug in ("bp-golovki-trimmernye", "hoz-voronki", "izm-multimetry",
             "prochaya-osnastka", "avtomaty-predohraniteli", "bp-trimmery",
             "izm-areometry", "svar-sopla", "obor-smazka", "krep-gaiki", "krep-bolty"):
    print(f"option {slug}: {'OK id=' + str(opts[slug]) if slug in opts else 'ОТСУТСТВУЕТ'}")

# ---------------------------------------------------------------------------
print("\n=== 1. Кластер 1: триммерные головки ===")
qs1 = Product.objects.filter(
    Q(name__icontains="триммерн") & Q(name__icontains="головк")
).order_by("id")
pids1 = list(qs1.values_list("id", flat=True))
tm1 = type_map(pids1)
by_type = Counter(tm1[p][0] or "<без типа>" for p in pids1)
act = Counter()
stock = Counter()
for p in qs1.values("id", "is_active", "stock_quantity"):
    act[p["is_active"]] += 1
    stock[p["stock_quantity"] > 0] += 1
print(f"критерий «триммерн + головк»: {len(pids1)} товаров")
print(f"  по типам: {dict(by_type)}")
print(f"  is_active: {dict(act)}, stock>0: {dict(stock)}")
for pid in (38680, 26232, 1899, 28157, 28158, 28159):
    row = Product.objects.filter(id=pid).values("id", "name", "is_active", "stock_quantity").first()
    t = type_map([pid])[pid]
    inside = pid in pids1
    print(f"  pid={pid} inside_criterion={inside} type={t} | {row}")
pids1_final = sorted((set(pids1) - {38680}) | {26232})
print(f"ИТОГО кластер 1 к переносу: {len(pids1_final)} (ожидалось 108)")
tm1f = type_map(pids1_final)
print(f"  по исходным типам: {dict(Counter(tm1f[p][0] or '<без типа>' for p in pids1_final))}")
print(f"  по source: {dict(Counter(tm1f[p][1] or '<нет PAV>' for p in pids1_final))}")
(OUT / "cluster1-ids.json").write_text(json.dumps(pids1_final), encoding="utf-8")

# ---------------------------------------------------------------------------
print("\n=== 2. Кластер 2: воронки ===")
rx = re.compile(r"воронк", re.IGNORECASE)
qs2 = Product.objects.filter(name__iregex=r"(^|[^а-яё])воронк").order_by("id")
# iregex может отличаться от \b — доберём простым питоновским фильтром по \bворонк
cand2 = []
for p in Product.objects.filter(name__icontains="воронк").order_by("id").values(
    "id", "name", "is_active", "stock_quantity"
):
    if rx.search(p["name"]):
        cand2.append(p)
pids2 = [p["id"] for p in cand2]
tm2 = type_map(pids2)
print(f"regex \\bворонк: {len(pids2)} товаров")
for p in cand2:
    t = tm2[p["id"]]
    print(f"  pid={p['id']} active={p['is_active']} stock={p['stock_quantity']} "
          f"type={t[0]!r} src={t[1]!r} | {p['name']}")

# ---------------------------------------------------------------------------
print("\n=== 3. Кластер 3: нагрузочные вилки ===")
qs3 = Product.objects.filter(
    Q(name__icontains="нагрузочн") & Q(name__icontains="вилк")
).order_by("id").values("id", "name", "is_active", "stock_quantity")
cand3 = list(qs3)
pids3 = [p["id"] for p in cand3]
tm3 = type_map(pids3)
print(f"критерий «нагрузочн + вилк»: {len(pids3)} товаров")
for p in cand3:
    t = tm3[p["id"]]
    print(f"  pid={p['id']} active={p['is_active']} stock={p['stock_quantity']} "
          f"type={t[0]!r} src={t[1]!r} | {p['name']}")

# ---------------------------------------------------------------------------
print("\n=== 4. Счётчики затронутых типов (ДО) ===")
slugs = ["bp-golovki-trimmernye", "hoz-voronki", "izm-multimetry",
         "prochaya-osnastka", "krep-gaiki", "krep-bolty",
         "avtomaty-predohraniteli", "obor-smazka"]
counts = dict(
    ProductAttributeValue.objects.filter(
        attribute__slug=TOOL_TYPE, value_option__slug__in=slugs
    ).values("value_option__slug").annotate(c=Count("product_id"))
    .values_list("value_option__slug", "c")
)
print(json.dumps({s: counts.get(s, 0) for s in slugs}, ensure_ascii=False, sort_keys=True))

print("\n=== RECON DONE ===")
