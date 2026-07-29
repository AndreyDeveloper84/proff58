"""READ-ONLY Round 3D.1 target-leaf preflight: винты ГОСТ 4945/4946 → Крепёж (355)."""
import collections
from apps.catalog.models import Category, Product, ProductStatus

IDS = [4945, 4946]
cat_name = {c.pk: c.name for c in Category.objects.all()}
KREP = Category.objects.get(pk=355)
krep_ids = [KREP.pk, *KREP.get_descendants().values_list("pk", flat=True)]
krep_cat = {c.pk: c for c in Category.objects.filter(pk__in=krep_ids)}


def nm(p):
    return p.original_name or p.name or ""


def pub(p):
    return p.is_active and p.status == ProductStatus.PUBLISHED


print("=== 3D.1 ВИНТЫ ГОСТ ===")
for pid in IDS:
    p = Product.objects.get(pk=pid)
    print(f"   [{pid}] pub={pub(p)} | manual={p.category_is_manual} | leaf={p.category_id}({cat_name.get(p.category_id)}) | {nm(p)[:60]}")

print(f"\n=== v2 root КРЕПЁЖ id={KREP.pk} slug={KREP.slug} on_site={getattr(KREP,'on_site',None)} active={KREP.is_active} ===")
for cid in krep_ids:
    c = krep_cat[cid]
    mark = " <-- БОЛТЫ/ВИНТЫ?" if any(k in c.name.lower() for k in ["болт", "винт"]) else ""
    print(f"   KREP_LEAF|id={cid}|{c.name}|slug={c.slug}|on_site={getattr(c,'on_site',None)}|active={c.is_active}|products={Product.objects.filter(category_id=cid).count()}{mark}")

# где лежат аналогичные винты ГОСТ/шестигранные в Крепеже
krep_prod = list(Product.objects.filter(category_id__in=krep_ids).values("id", "name", "original_name", "category_id"))
def m(p, kws): return any(k in ((p.get('original_name') or p['name'] or '').lower().replace('ё','е')) for k in kws)
for label, kws in [("винт", ["винт"]), ("болт с шестигранной головкой", ["болт с шестигран", "гост р исо 4017", "болт м8"])]:
    ex = [p for p in krep_prod if m(p, kws)]
    print(f"\nв Крепеже '{label}': {len(ex)} | по leaf: {dict(collections.Counter(krep_cat[p['category_id']].name for p in ex))}")
    for p in sorted(ex, key=lambda x: x['id'])[:5]:
        print(f"   [{p['id']}] {(p.get('original_name') or p['name'])[:50]} <{krep_cat[p['category_id']].name}>")
print("\nNOTE: recat меняет только category_id; tool_type/attrs_cache/slug/publish/category_is_manual — НЕ трогаются.")
