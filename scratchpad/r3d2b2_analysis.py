"""READ-ONLY Round 3D.2b.2 анализ: 3 электропривода к вибраторам (38369-38371).
Архитектурный вопрос: привод = вибратор (→417) или принадлежность? Ничего не пишет.
"""
import collections
import re
from apps.catalog.models import Attribute, Product, ProductAttributeValue

attr = Attribute.objects.get(slug="tool_type")
cat_name = {}
from apps.catalog.models import Category
allcat = {c.pk: c for c in Category.objects.all()}
def cname(cid): return allcat[cid].name if cid in allcat else "?"
def croot(cid):
    c = allcat.get(cid)
    return c.get_root().name if c else "?"
def tt_of(pid):
    return list(ProductAttributeValue.objects.filter(attribute=attr, product_id=pid).values_list("value_option__value", flat=True))
def nm(p): return p.get("original_name") or p["name"] or ""

CAND = [38369, 38370, 38371]
print("=== 3 КАНДИДАТА (электроприводы) ===")
for pid in CAND:
    p = Product.objects.get(pk=pid)
    print(f"   [{pid}] cat={p.category_id}({cname(p.category_id)}/{croot(p.category_id)}) | "
          f"tool_type={tt_of(pid)} | cache_tt={(p.attrs_cache or {}).get('tool_type')!r} | manual={p.category_is_manual} | pub={p.is_active and p.status=='published'}")
    print(f"        {(p.original_name or p.name)}")

# --- аналоги по всему каталогу ---
print("\n=== АНАЛОГИ по каталогу (электропривод/привод глубин/ИВ-/ЭПК/ЭП-/ВП-) ===")
PATS = ["электропривод", "привод глубин", "привод вибр", "эпк-1300", "эпк 1300"]
IVPAT = re.compile(r"\bив-?1?1[679]\b|\bив-?9[89]\b|\bэп-\d|\bвп-\d")
rows = list(Product.objects.values("id", "name", "original_name", "category_id"))
def txt(r): return (r.get("original_name") or r["name"] or "").lower().replace("ё", "е")
an = [r for r in rows if any(k in txt(r) for k in PATS) or IVPAT.search(txt(r))]
print(f"найдено аналогов: {len(an)}")
byleaf = collections.Counter((r["category_id"], cname(r["category_id"])) for r in an)
for (cid, cn), c in byleaf.most_common(10):
    print(f"   ANALOG_LEAF|{cid}|{cn}|root={croot(cid)}|count={c}")
# их tool_type
tts = collections.Counter()
for r in an:
    for v in tt_of(r["id"]) or ["<нет>"]:
        tts[v] += 1
print("   tool_type аналогов:", dict(tts))
print("   sample аналогов:")
for r in sorted(an, key=lambda x: x["id"])[:14]:
    print(f"      [{r['id']}] {nm(r)[:52]} <{cname(r['category_id'])}> tt={tt_of(r['id'])}")

# --- есть ли приводы среди 417 ---
print("\n=== среди tool_type 417: есть ли 'электропривод/привод' ? ===")
p417 = list(ProductAttributeValue.objects.filter(attribute=attr, value_option_id=417).values_list("product_id", flat=True))
drv417 = [pid for pid in p417 if "привод" in (Product.objects.get(pk=pid).name or "").lower()]
print(f"417-товаров всего={len(p417)} | из них со словом 'привод'={len(drv417)}: {drv417}")
for pid in drv417[:5]:
    p = Product.objects.get(pk=pid)
    print(f"   [{pid}] {(p.original_name or p.name)[:56]}")

# --- производители 3 кандидатов ---
print("\n=== производители/бренды 3 кандидатов ===")
for pid in CAND:
    p = Product.objects.get(pk=pid)
    print(f"   [{pid}] {(p.original_name or p.name)[:66]}")
