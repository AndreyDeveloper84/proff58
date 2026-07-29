"""READ-ONLY Round 3D.2b.1 preflight: 6 готовых вибраторов (38358-38363)
→ категория «Вибраторы для бетона» + tool_type option 417. Ничего не пишет.
"""
import collections
from apps.catalog.models import (Attribute, AttributeOption, Category, Product,
                                 ProductAttributeValue, ProductStatus)

attr = Attribute.objects.get(slug="tool_type")
OPT417 = 417
cat = {c.pk: c for c in Category.objects.all()}


def root_of(cid):
    c = cat.get(cid)
    if not c:
        return None
    return c.get_root()


def pub(p):
    return p.is_active and p.status == ProductStatus.PUBLISHED


# --- 1. где сейчас все товары с option 417 ---
pids417 = list(ProductAttributeValue.objects.filter(attribute=attr, value_option_id=OPT417)
               .values_list("product_id", flat=True))
prods417 = list(Product.objects.filter(id__in=pids417))
print(f"=== option 417 «Вибраторы для бетона»: usage={len(prods417)} ===")
byleaf = collections.Counter((p.category_id, cat[p.category_id].name) for p in prods417)
for (cid, cname), c in byleaf.most_common():
    r = root_of(cid)
    print(f"   417_LEAF|id={cid}|{cname}|root={r.pk if r else '?'}({r.name if r else '?'})|"
          f"on_site={getattr(cat[cid],'on_site',None)}|active={cat[cid].is_active}|count={c}")
manual417 = sum(1 for p in prods417 if p.category_is_manual)
pub417 = sum(1 for p in prods417 if pub(p))
print(f"   417: published={pub417}|category_is_manual=True:{manual417}/{len(prods417)}")
print("   sample:")
for p in sorted(prods417, key=lambda x: x.id)[:6]:
    print(f"      [{p.id}] {(p.original_name or p.name)[:50]} <{cat[p.category_id].name}>")

# определяем канонический target leaf = самый частый среди 417
target_leaf = byleaf.most_common(1)[0][0][0] if byleaf else None
tgt = cat.get(target_leaf)
print(f"\nКАНОНИЧЕСКИЙ TARGET LEAF = {target_leaf} «{tgt.name if tgt else '?'}» "
      f"slug={tgt.slug if tgt else '?'} on_site={getattr(tgt,'on_site',None)} active={tgt.is_active if tgt else '?'}")

# --- 2. 6 кандидатов 38358-38363 ---
CAND = [38358, 38359, 38360, 38361, 38362, 38363]
print(f"\n=== 6 КАНДИДАТОВ (готовые вибраторы) ===")
for pid in CAND:
    p = Product.objects.get(pk=pid)
    tt = list(ProductAttributeValue.objects.filter(attribute=attr, product_id=pid)
              .values_list("value_option__value", flat=True))
    cache_tt = (p.attrs_cache or {}).get("tool_type")
    print(f"   [{pid}] pub={pub(p)} | manual={p.category_is_manual} | "
          f"leaf={p.category_id}({cat[p.category_id].name}) | tool_type_PAV={tt} | cache_tt={cache_tt!r}")
    print(f"        {(p.original_name or p.name)[:64]}")

# --- 3. исключение электроприводов ---
EXCL = [38369, 38370, 38371]
print(f"\n=== ИСКЛЮЧЕНЫ (электроприводы, НЕ в scope) ===")
for pid in EXCL:
    p = Product.objects.get(pk=pid)
    print(f"   EXCL|[{pid}] {(p.original_name or p.name)[:56]} | in_candidates={pid in CAND}")

# --- 4. план ---
have_tt = sum(1 for pid in CAND if ProductAttributeValue.objects.filter(attribute=attr, product_id=pid).exists())
print(f"\nPLAN|scope=6|PAV_create=%s|PAV_update=0|attrs_cache_update=6|category_move=6->%s" % (6 - have_tt, target_leaf))
print(f"PLAN|уже имеют tool_type: {have_tt}/6 (ожидание 0)")
print("PLAN|category_is_manual остаётся True; publish/slug не трогаем")
print("NOTE: если target leaf под Электро — проверить, не смешаем ли с другим типом (там уже 417-аналоги).")
