"""READ-ONLY Round 3B target-leaf preflight: автохимия (root 191) → Авто (root 167).
Ничего не пишет. Определяет целевой leaf, rollback-map, SEO/visibility.
"""
import collections

from apps.catalog.models import Category, Product, ProductStatus

SRC = Category.objects.get(pk=191)
src_ids = [SRC.pk, *SRC.get_descendants().values_list("pk", flat=True)]
src_leaf = {c.pk: c.name for c in Category.objects.filter(pk__in=src_ids)}
AVTO = Category.objects.get(pk=167)
avto_ids = [AVTO.pk, *AVTO.get_descendants().values_list("pk", flat=True)]


def nm(p):
    return p.get("original_name") or p["name"] or ""


def nrm(p):
    return nm(p).lower().replace("ё", "е")


def pub(p):
    return p["is_active"] and p["status"] == ProductStatus.PUBLISHED


KW = ["антифриз", "тосол", "стеклоом", "незамерз", "омыват", "автошампунь", "жидкость для запуска"]
allp = list(Product.objects.filter(category_id__in=src_ids)
            .values("id", "name", "original_name", "is_active", "status",
                    "category_id", "category_is_manual"))
aff = [p for p in allp if any(k in nrm(p) for k in KW)]
print(f"=== 3B АВТОХИМИЯ: affected={len(aff)} | pub={sum(1 for p in aff if pub(p))} ===")
print(f"category_is_manual=True: {sum(1 for p in aff if p.get('category_is_manual'))}/{len(aff)}")
cur = collections.Counter(src_leaf.get(p["category_id"]) for p in aff)
print("current_leaf:", dict(cur))
print("--- список 24 (id | pub | name) ---")
for p in sorted(aff, key=lambda x: x["id"]):
    print(f"   [{p['id']}] pub=%s | %s" % (pub(p), nm(p)[:62]))

# --- дерево Авто (167): leaves + counts ---
print(f"\n=== v2 root АВТО id={AVTO.pk} slug={AVTO.slug} on_site={getattr(AVTO,'on_site',None)} active={AVTO.is_active} ===")
avto_prod = list(Product.objects.filter(category_id__in=avto_ids)
                 .values("id", "name", "original_name", "category_id"))
avto_cat = {c.pk: c for c in Category.objects.filter(pk__in=avto_ids)}
cnt_by_cat = collections.Counter(p["category_id"] for p in avto_prod)
print("--- leaves Авто (id|name|slug|on_site|active|products) ---")
for cid in avto_ids:
    c = avto_cat[cid]
    print(f"   AVTO_LEAF|id={cid}|{c.name}|slug={c.slug}|on_site={getattr(c,'on_site',None)}|active={c.is_active}|products={cnt_by_cat.get(cid,0)}")

# --- где уже лежат антифризы/стеклоомыватели в Авто ---
print("\n--- существующие антифризы/стеклоомыв в Авто (естественный target) ---")
avto_chem = [p for p in avto_prod if any(k in ((p.get('original_name') or p['name'] or '').lower().replace('ё','е')) for k in KW)]
tgt = collections.Counter(avto_cat[p["category_id"]].name for p in avto_chem)
print(f"найдено в Авто: {len(avto_chem)} | по leaf: {dict(tgt)}")
for p in sorted(avto_chem, key=lambda x: x["id"])[:8]:
    print(f"   [{p['id']}] {(p.get('original_name') or p['name'])[:55]} <{avto_cat[p['category_id']].name}>")

print("\nNOTE: recat меняет ТОЛЬКО product.category_id; tool_type/attrs_cache/slug — НЕ трогаются.")
print("NOTE: category_is_manual остаётся True (сайт-мастер сохраняется).")
