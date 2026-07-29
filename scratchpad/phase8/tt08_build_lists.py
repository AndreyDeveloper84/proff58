"""TT-08 · аудит и фиксация списков переклассификации (read-only).

Критерий (дословно, воспроизводим):
- Гайковёрты → gaikoverty (электрические): name ILIKE '%гайковерт%' AND
  текущий tool_type='dreli-shurupoverty' AND name NOT MATCHES ручной паттерн
  (ручн|механическ|32х33|РГ ?5|мультиплик) → 107.
- Гайковёрты ручные → gaikoverty-ruchnye: явные id 21, 23, 26213, 26214
  (механические/ручные, сейчас golovki/prochaya-osnastka), 43790 (внутри
  dreli-выборки), 22 (spetsialnye-klyuchi — кейс, ради которого заводился тип).
- Леска → bp-leska: текущий tool_type='prochaya-osnastka' AND
  name ILIKE '%леска%' AND товар — сама леска (исключены 3 головки
  триммерные: 26239, 26256, 26257) → 190; плюс 2 явных id из izm-ugolniki
  (26724, 26749 — леска, попавшая в «Угольники» по слову «треугольник»).
- Исключения: 38762–38768 (услуги «Ремонт гайковерта …» — не товар-инструмент),
  8832 (крюк для гайковерта — аксессуар, типа нет), 19 бензокос в bp-trimmery
  (машины, на своём месте), 3 головки триммерные (остаются в prochaya-osnastka).

Запуск: manage.py shell -c "exec(open('scratchpad/phase8/tt08_build_lists.py', encoding='utf-8').read())"
"""

from __future__ import annotations

import io
import json
import re

from apps.catalog.models import Product, ProductAttributeValue

MANUAL_RE = re.compile(r"ручн|механическ|32\s?[хx]\s?33|РГ\s?5|мультиплик", re.I)
RUCHNYE_IDS = [21, 22, 23, 26213, 26214, 43790]
LESKA_EXCLUDE_HEADS = [26239, 26256, 26257]
LESKA_UGOLNIKI_IDS = [26724, 26749]
EXCLUDED_SERVICES = [38762, 38763, 38764, 38765, 38766, 38767, 38768]
EXCLUDED_HOOK = [8832]

g = list(Product.objects.filter(name__icontains="гайковерт").order_by("pk"))
tt = {}
for r in ProductAttributeValue.objects.filter(
    product__in=g, attribute__slug="tool_type"
).select_related("value_option"):
    tt[r.product_id] = r.value_option.slug if r.value_option else None

elec = sorted(
    p.pk for p in g
    if tt.get(p.pk) == "dreli-shurupoverty" and not MANUAL_RE.search(p.name)
)
assert len(elec) == 107, f"ожидалось 107 электрических, факт {len(elec)}"
assert 43790 not in elec

l = list(Product.objects.filter(name__icontains="леска").order_by("pk"))
tt2 = {}
for r in ProductAttributeValue.objects.filter(
    product__in=l, attribute__slug="tool_type"
).select_related("value_option"):
    tt2[r.product_id] = r.value_option.slug if r.value_option else None
leska = sorted(
    p.pk for p in l
    if tt2.get(p.pk) == "prochaya-osnastka" and p.pk not in LESKA_EXCLUDE_HEADS
)
assert len(leska) == 190, f"ожидалось 190 лески, факт {len(leska)}"
leska_all = sorted(leska + LESKA_UGOLNIKI_IDS)

plan = {
    "gaikoverty": elec,
    "gaikoverty-ruchnye": RUCHNYE_IDS,
    "bp-leska": leska_all,
}
total = sum(len(v) for v in plan.values())

# batches ≤30: гайковёрты (elec+ruchnye объединённая очередь, сорт по pk), леска
gai_queue = sorted(elec + RUCHNYE_IDS)
leska_queue = leska_all

def chunks(xs, n=30):
    return [xs[i:i + n] for i in range(0, len(xs), n)]

batches = []
for i, ch in enumerate(chunks(gai_queue), 1):
    batches.append({
        "batch": f"G{i}", "ids": ch,
        "map": {pid: ("gaikoverty-ruchnye" if pid in RUCHNYE_IDS else "gaikoverty") for pid in ch},
    })
for i, ch in enumerate(chunks(leska_queue), 1):
    batches.append({"batch": f"L{i}", "ids": ch, "map": {pid: "bp-leska" for pid in ch}})

doc = {
    "plan": plan,
    "excluded": {
        "services": EXCLUDED_SERVICES,
        "hook": EXCLUDED_HOOK,
        "trimmer_heads": LESKA_EXCLUDE_HEADS,
        "bp_trimmery_machines_untouched": 19,
    },
    "batches": batches,
    "total": total,
}
with io.open("scratchpad/phase8/tt-08-lists.json", "w", encoding="utf-8") as fh:
    json.dump(doc, fh, ensure_ascii=False, indent=1)
print("gaikoverty:", len(elec), "| gaikoverty-ruchnye:", len(RUCHNYE_IDS),
      "| bp-leska:", len(leska_all), "| total:", total)
print("batches:", [(b["batch"], len(b["ids"])) for b in batches])
