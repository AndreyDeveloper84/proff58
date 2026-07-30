# -*- coding: utf-8 -*-
"""CAT-04 · задача 3: состав tool_type=izm-ugolniki — измерение чужеродных товаров. READ-ONLY.

Ничего не меняет: только классифицирует названия и считает. Классы:
  * core — угольники/линейки/шаблоны/реечные инструменты разметки;
  * abrasive — абразивные треугольники/листы;
  * fitting — сантехнические фитинги (отвод/тройник/муфта/крестовина/уголок PPR и т.п.);
  * other — прочее чужеродное (кельма, бирки, платформа и т.д.).
"""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Product, ProductAttributeValue as PAV  # noqa: E402

CORE_RE = re.compile(
    r"угольник|линейк|шаблон|угломер|транспортир|малка|поверочн|разметочн|рейсмус|"
    r"щуп|калибр|реечн|строительн.{0,10}угол",
    re.I,
)
ABRASIVE_RE = re.compile(r"абразив|шлиф|наждач|треугольник.{0,30}P\d+|лист.{0,15}шлиф", re.I)
FITTING_RE = re.compile(
    r"фитинг|отвод|тройник|крестовин|муфта|полипропилен|PPR|ППР|сантехн|"
    r"уголок.{0,20}(90|45)\s*°|компрессионн|обжимн|резьбов.{0,10}соединен",
    re.I,
)

pids = PAV.objects.filter(
    attribute__slug="tool_type", value_option__slug="izm-ugolniki"
).values_list("product_id", flat=True)
products = Product.objects.filter(id__in=pids).order_by("id")

out = {"total": 0, "core": [], "abrasive": [], "fitting": [], "other": []}
for p in products:
    name = p.original_name or p.name
    pub = p.status == "published" and p.is_active
    row = {"pid": p.id, "pub": pub, "name": name[:110]}
    out["total"] += 1
    if CORE_RE.search(name):
        out["core"].append(row)
    elif ABRASIVE_RE.search(name):
        out["abrasive"].append(row)
    elif FITTING_RE.search(name):
        out["fitting"].append(row)
    else:
        out["other"].append(row)

summary = {
    k: (len(v) if isinstance(v, list) else v)
    for k, v in out.items()
}
summary["core_pub"] = sum(1 for r in out["core"] if r["pub"])
summary["foreign"] = len(out["abrasive"]) + len(out["fitting"]) + len(out["other"])
summary["foreign_pub"] = sum(
    1 for k in ("abrasive", "fitting", "other") for r in out[k] if r["pub"]
)
print("===SUMMARY===")
print(json.dumps(summary, ensure_ascii=False))
print("===FOREIGN===")
for k in ("abrasive", "fitting", "other"):
    print(f"--- {k} ({len(out[k])}) ---")
    for r in out[k]:
        print(f"{r['pid']} pub={r['pub']} {r['name']}")
