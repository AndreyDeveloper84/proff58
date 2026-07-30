"""READ-ONLY Round 4 characterization: 4A Герметики-остаток / 4B Антикор /
4C Ковши / 4D Скребки. Ничего не пишет. Кластеры — карта, не правила.
"""
import collections
import re
from apps.catalog.models import (Attribute, AttributeOption, Category, Product,
                                 ProductAttributeValue, ProductStatus)

root = Category.objects.get(pk=191)
src_ids = [root.pk, *root.get_descendants().values_list("pk", flat=True)]
cat_name = {c.pk: c.name for c in Category.objects.all()}
attr = Attribute.objects.get(slug="tool_type")
opt_values = set(AttributeOption.objects.filter(attribute=attr).values_list("value", flat=True))
typed = set(ProductAttributeValue.objects.filter(attribute=attr, product__category_id__in=src_ids).values_list("product_id", flat=True))
prods = list(Product.objects.filter(category_id__in=src_ids)
             .values("id", "name", "original_name", "is_active", "status", "category_id"))


def nm(p): return p.get("original_name") or p["name"] or ""
def nrm(p): return nm(p).lower().replace("ё", "е")
def pub(p): return p["is_active"] and p["status"] == ProductStatus.PUBLISHED
def stat(lst): return "%s/%s" % (len(lst), sum(1 for p in lst if pub(p)))
def show(lst, k=8):
    for p in sorted(lst, key=lambda x: x["id"])[:k]:
        print("      [%s] %s <%s>" % (p["id"], nm(p)[:56], cat_name.get(p["category_id"])))

LEAF193 = 193

# ============ 4A: остаток leaf 193 (untyped) ============
print("======== 4A ГЕРМЕТИКИ-ОСТАТОК (leaf 193, untyped) ========")
a = [p for p in prods if p["category_id"] == LEAF193 and p["id"] not in typed]
print("untyped в 193: %s" % stat(a))
A_BUCKETS = [
    ("газоблоки/блоки", ["газоблок", "газобетон", "пеноблок", "блок 2", "блок 6", "блок керамзит", "блок газо"]),
    ("сыпучие (вермикулит/керамзит/перлит)", ["вермикулит", "керамзит", "перлит", "песок", "щебень"]),
    ("желоба/водосток", ["желоб", "водосточн", "водосток", "воронка водост", "колено водост"]),
    ("бетонконтакт", ["бетонконтакт", "бетоноконтакт"]),
    ("антистатик/антишум/антизапот", ["антистатик", "антишум", "антизапот", "антиналедь"]),
    ("проникающая/жидкий ключ", ["жидкий ключ", "проникающ", "wd-40", "wd 40"]),
    ("стройхимия (антисептик/огнебио/пропитка/добавки)", ["антисептик", "огнебио", "антипирен", "пропитк", "отвердитель", "затвердител", "добавка", "пластификатор", "жидкое стекло", "битум", "мастика", "праймер", "адгилин"]),
    ("бытовая химия", ["мыло", "порошок", "чистящ", "моющ", "дезинфиц", "для рук", "белизна", "освежит", "пятновывод"]),
    ("автохимия-остаток", ["антифриз", "тосол", "стеклоом", "теплоноситель"]),
    ("материалы прочие", ["сетка", "пленка", "сода", "гипс", "цемент", "шпаклевк", "штукатурк", "смесь"]),
]
a_assign = {}
for p in a:
    n = nrm(p); lab = None
    for L, kws in A_BUCKETS:
        if any(k in n for k in kws): lab = L; break
    a_assign.setdefault(lab or "RESIDUAL", []).append(p)
for L, _ in A_BUCKETS:
    if a_assign.get(L):
        print("  A|%s|%s" % (L, stat(a_assign[L]))); show(a_assign[L], 6)
res = a_assign.get("RESIDUAL", [])
print("  A|RESIDUAL|%s" % stat(res))
cnt = collections.Counter()
for p in res:
    for w in re.findall(r"[а-яёa-z0-9]+", nrm(p)):
        if len(w) >= 4: cnt[w] += 1
print("     top tokens:", "; ".join("%s:%s" % (w, c) for w, c in cnt.most_common(25)))
show(res, 14)

# ============ 4B: Антикор ============
print("\n======== 4B АНТИКОР (root 191) ========")
b = [p for p in prods if any(k in nrm(p) for k in ["ржавчин", "антикор", "преобразователь рж", "цинкар", "мовиль"])]
print("всего: %s" % stat(b))
B_SUB = [
    ("преобразователь ржавчины", ["преобразователь рж", "преобразователь ржавч"]),
    ("удалитель/гель от ржавчины", ["от ржавчины", "удалитель рж", "гель от рж", "очиститель рж"]),
    ("антикор-покрытие/мастика", ["антикор полимер", "антикор битум", "мастика антикор", "цинкар", "мовиль", "антикоррозийн покрыт"]),
    ("FP (теплоизоляция/прочее)", ["теплоизоляц", "броня"]),
]
b_assign = {}
for p in b:
    n = nrm(p); lab = None
    for L, kws in B_SUB:
        if any(k in n for k in kws): lab = L; break
    b_assign.setdefault(lab or "прочее-антикор", []).append(p)
for L in [x[0] for x in B_SUB] + ["прочее-антикор"]:
    if b_assign.get(L):
        print("  B|%s|%s" % (L, stat(b_assign[L]))); show(b_assign[L], 6)

# ============ 4C: Ковши ============
print("\n======== 4C КОВШИ (root 191) ========")
c = [p for p in prods if "ковш" in nrm(p)]
print("всего 'ковш': %s | typed уже: %s" % (stat(c), sum(1 for p in c if p["id"] in typed)))
show(c, 12)
print("  OPTION 'Кельмы, гладилки, тёрки' exists:", "Кельмы, гладилки, тёрки" in opt_values)
print("  OPTION 'Ковши штукатурные' exists:", "Ковши штукатурные" in opt_values)

# ============ 4D: Скребки ============
print("\n======== 4D СКРЕБКИ (root 191) ========")
d = [p for p in prods if "скребок" in nrm(p) or "скребк" in nrm(p)]
print("всего 'скреб': %s | typed уже: %s" % (stat(d), sum(1 for p in d if p["id"] in typed)))
D_SUB = [
    ("машинные Nilfisk/поломоечные", ["nilfisk", "br755", "поломоеч", "для машины"]),
    ("для кафеля/плитки", ["кафел", "плитк"]),
    ("для пола/льда/снега", ["для пола", "напольн", "лед", "снег"]),
    ("строительные/малярные", ["малярн", "строительн", "шпател", "для краск", "обойн"]),
]
d_assign = {}
for p in d:
    n = nrm(p); lab = None
    for L, kws in D_SUB:
        if any(k in n for k in kws): lab = L; break
    d_assign.setdefault(lab or "прочие скребки", []).append(p)
for L in [x[0] for x in D_SUB] + ["прочие скребки"]:
    if d_assign.get(L):
        print("  D|%s|%s" % (L, stat(d_assign[L]))); show(d_assign[L], 6)
print("  OPTION 'Скребки' exists:", "Скребки" in opt_values)
