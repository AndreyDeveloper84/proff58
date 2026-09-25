"""READ-ONLY Round 3D.2 анализ: гибкие валы / виброоснастка (root 191).
Отделяем от «Вибраторы для бетона» (Электро). Ищем target leaf в Оснастке(74).
Ничего не пишет.
"""
import collections
from apps.catalog.models import Category, Product, ProductStatus

SRC = Category.objects.get(pk=191)
src_ids = [SRC.pk, *SRC.get_descendants().values_list("pk", flat=True)]
cat_name = {c.pk: c.name for c in Category.objects.all()}


def nm(p):
    return p.get("original_name") or p["name"] or ""


def nrm(p):
    return nm(p).lower().replace("ё", "е")


def pub(p):
    return p["is_active"] and p["status"] == ProductStatus.PUBLISHED


allp = list(Product.objects.filter(category_id__in=src_ids)
            .values("id", "name", "original_name", "is_active", "status",
                    "category_id", "category_is_manual"))
KW = ["вибратор", "вибронаконечник", "виброрейк", "глубинный вибр", "вал гибкий", "гибкий вал", "булава"]
aff = [p for p in allp if any(k in nrm(p) for k in KW)]
print(f"=== 3D.2 ВИБРО/ГИБКИЕ ВАЛЫ (root 191): affected={len(aff)} | pub={sum(1 for p in aff if pub(p))} ===")
print("current_leaf:", dict(collections.Counter(cat_name.get(p['category_id']) for p in aff)))
print(f"category_is_manual=True: {sum(1 for p in aff if p.get('category_is_manual'))}/{len(aff)}")

# под-разбор: сам вибратор(двигатель) vs гибкий вал vs наконечник/булава
def cls(p):
    n = nrm(p)
    if "вал гибкий" in n or "гибкий вал" in n:
        return "гибкий вал"
    if "наконечник" in n or "булава" in n:
        return "вибронаконечник/булава"
    if "виброрейк" in n or "виброплит" in n:
        return "виброрейка/плита"
    if "вибратор" in n:
        return "вибратор(двигатель?)"
    return "прочее"
sub = collections.Counter(cls(p) for p in aff)
print("--- под-классы ---")
for k, c in sub.most_common():
    print(f"   SUB|{k}|{c}")
print("--- все ---")
for p in sorted(aff, key=lambda x: x["id"]):
    print(f"   [{p['id']}] pub=%s | %s | %s" % (pub(p), cls(p), nm(p)[:56]))

# существующий tool_type «Вибраторы для бетона» (Электро) — не смешивать
print("\n=== существующие 'Вибраторы для бетона' (Электро) — для несмешивания ===")
from apps.catalog.models import Attribute, AttributeOption, ProductAttributeValue
attr = Attribute.objects.get(slug="tool_type")
vb = AttributeOption.objects.filter(attribute=attr, value__icontains="вибратор").values("id", "value")
print("option 'вибратор*':", list(vb))
for o in vb:
    cnt = ProductAttributeValue.objects.filter(attribute=attr, value_option_id=o["id"]).count()
    print(f"   usage|{o['value']}|{cnt}")

# кандидат target leaf в Оснастке (74)
OSN = Category.objects.get(pk=74)
osn_ids = [OSN.pk, *OSN.get_descendants().values_list("pk", flat=True)]
print(f"\n=== v2 root ОСНАСТКА id=74 slug={OSN.slug} — leaves (для target) ===")
for cid in osn_ids:
    c = Category.objects.get(pk=cid)
    mark = " <--?" if any(k in c.name.lower() for k in ["вибр", "вал", "гибк", "прочая", "расходн", "оснастк", "аксессуар", "комплект"]) else ""
    if c.depth <= OSN.depth + 1 or mark:
        print(f"   OSN_LEAF|id={cid}|{c.name}|slug={c.slug}|on_site={getattr(c,'on_site',None)}|active={c.is_active}|products={Product.objects.filter(category_id=cid).count()}{mark}")
# где лежат существующие гибкие валы/наконечники в других разделах
print("\n=== где уже лежат 'вал гибкий'/'вибронаконечник' по всему каталогу ===")
gv = list(Product.objects.filter(name__iregex="вал гибк|гибкий вал|вибронаконеч").values("id","name","category_id")[:10])
for p in gv:
    print(f"   [{p['id']}] {p['name'][:46]} <{cat_name.get(p['category_id'])}>")
