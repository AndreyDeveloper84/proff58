"""READ-ONLY Round 3C.1 target-leaf preflight: топоры (root 191) → Ручной (root 339).
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
aff = [p for p in allp if "топор" in nrm(p)]
print(f"=== 3C.1 ТОПОРЫ: affected={len(aff)} | pub={sum(1 for p in aff if pub(p))} ===")
print(f"category_is_manual=True: {sum(1 for p in aff if p.get('category_is_manual'))}/{len(aff)}")
print("current_leaf:", dict(collections.Counter(cat_name.get(p['category_id']) for p in aff)))
# FP-скан
FP = ["топорище", "мачете", "ледоруб", "кирка", "мотыга", "секира сувенир", "сувенир"]
fp = [p for p in aff if any(k in nrm(p) for k in FP)]
print(f"FP-подозрительные (топорище/мачете/ледоруб/кирка/сувенир) = {len(fp)}")
for p in fp:
    print(f"   FP?|[{p['id']}] {nm(p)[:60]}")
print("--- sample 49 ---")
for p in sorted(aff, key=lambda x: x["id"])[:14]:
    print(f"   [{p['id']}] pub=%s | %s" % (pub(p), nm(p)[:60]))

# --- дерево Ручной (339) ---
print(f"\n=== v2 root РУЧНОЙ id={RUCH.pk} slug={RUCH.slug} on_site={getattr(RUCH,'on_site',None)} active={RUCH.is_active} ===")
ruch_prod = list(Product.objects.filter(category_id__in=ruch_ids).values("id", "name", "original_name", "category_id"))
cnt = collections.Counter(p["category_id"] for p in ruch_prod)
for cid in ruch_ids:
    c = ruch_cat[cid]
    mark = " <-- ТОПОРЫ?" if "топор" in c.name.lower() else ""
    print(f"   RUCH_LEAF|id={cid}|{c.name}|slug={c.slug}|on_site={getattr(c,'on_site',None)}|active={c.is_active}|products={cnt.get(cid,0)}{mark}")

# --- существующие топоры в Ручном (естественный target) ---
ex = [p for p in ruch_prod if "топор" in ((p.get('original_name') or p['name'] or '').lower().replace('ё','е'))]
print(f"\nсуществующие 'топор' в Ручном: {len(ex)} | по leaf: {dict(collections.Counter(ruch_cat[p['category_id']].name for p in ex))}")
for p in sorted(ex, key=lambda x: x['id'])[:6]:
    print(f"   [{p['id']}] {(p.get('original_name') or p['name'])[:50]} <{ruch_cat[p['category_id']].name}>")
print("\nNOTE: recat меняет только category_id; tool_type/attrs_cache/slug/publish/category_is_manual — НЕ трогаются.")
