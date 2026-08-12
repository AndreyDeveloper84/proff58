"""READ-ONLY Round 3C.2 target-leaf preflight: гвоздодёры (root 191) → Ручной (339).
Ничего не пишет.
"""
import collections

from apps.catalog.models import Category, Product, ProductStatus

SRC = Category.objects.get(pk=191)
src_ids = [SRC.pk, *SRC.get_descendants().values_list("pk", flat=True)]
cat_name = {c.pk: c.name for c in Category.objects.all()}
RUCH = Category.objects.get(pk=339)
ruch_ids = [RUCH.pk, *RUCH.get_descendants().values_list("pk", flat=True)]
ruch_cat = {c.pk: c for c in Category.objects.filter(pk__in=ruch_ids)}


def nm(p):
    return p.get("original_name") or p["name"] or ""


def nrm(p):
    return nm(p).lower().replace("ё", "е")


def pub(p):
    return p["is_active"] and p["status"] == ProductStatus.PUBLISHED


allp = list(Product.objects.filter(category_id__in=src_ids)
            .values("id", "name", "original_name", "is_active", "status",
                    "category_id", "category_is_manual"))
aff = [p for p in allp if "гвоздодер" in nrm(p)]
print(f"=== 3C.2 ГВОЗДОДЁРЫ: affected={len(aff)} | pub={sum(1 for p in aff if pub(p))} ===")
print(f"category_is_manual=True: {sum(1 for p in aff if p.get('category_is_manual'))}/{len(aff)}")
print("current_leaf:", dict(collections.Counter(cat_name.get(p['category_id']) for p in aff)))
FP = ["жидкие гвозд", "гвозди ", "гвоздь", "съемник"]
fp = [p for p in aff if any(k in nrm(p) for k in FP)]
print(f"FP-подозрительные (жидкие гвозди/гвозди-крепёж/съёмник) = {len(fp)}")
for p in fp:
    print(f"   FP?|[{p['id']}] {nm(p)[:60]}")
print("--- все 11 ---")
for p in sorted(aff, key=lambda x: x["id"]):
    print(f"   [{p['id']}] pub=%s | %s" % (pub(p), nm(p)[:62]))

print(f"\n=== v2 root РУЧНОЙ id={RUCH.pk} (leaves для контекста) ===")
for cid in ruch_ids:
    c = ruch_cat[cid]
    if any(k in c.name.lower() for k in ["лом", "гвоздодер", "монтиров", "молот", "ручной инструмент"]):
        print(f"   RUCH_LEAF|id={cid}|{c.name}|slug={c.slug}|on_site={getattr(c,'on_site',None)}|active={c.is_active}|products={Product.objects.filter(category_id=cid).count()}")

# где лежат существующие гвоздодёры/ломы/монтировки в Ручном
ruch_prod = list(Product.objects.filter(category_id__in=ruch_ids).values("id", "name", "original_name", "category_id"))
def m(p, kws): return any(k in ((p.get('original_name') or p['name'] or '').lower().replace('ё','е')) for k in kws)
for label, kws in [("гвоздодёр", ["гвоздодер"]), ("лом/ломик", ["лом ", "ломик", "лом-"]), ("монтировка", ["монтировк"])]:
    ex = [p for p in ruch_prod if m(p, kws)]
    print(f"\nв Ручном '{label}': {len(ex)} | по leaf: {dict(collections.Counter(ruch_cat[p['category_id']].name for p in ex))}")
    for p in sorted(ex, key=lambda x: x['id'])[:5]:
        print(f"   [{p['id']}] {(p.get('original_name') or p['name'])[:48]} <{ruch_cat[p['category_id']].name}>")
print("\nNOTE: recat меняет только category_id; tool_type/attrs_cache/slug/publish/category_is_manual — НЕ трогаются.")
