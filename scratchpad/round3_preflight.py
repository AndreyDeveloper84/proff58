"""READ-ONLY Round 3 preflight (recategorize) — фундамент.
Определяет: есть ли v2-целевой дом для каждого бакета; affected/current-leaf/
category_is_manual. НЕ маршрутизирует, ничего не пишет.
"""
import collections

from apps.catalog.models import Category, Product, ProductStatus

root = Category.objects.get(pk=191)
sub_ids = [root.pk, *root.get_descendants().values_list("pk", flat=True)]
cat_name = {c.pk: c.name for c in Category.objects.filter(pk__in=sub_ids)}

# --- v2-корни-цели (куда можно мигрировать) ---
print("=== v2-КОРНИ (кандидаты-цели recat) ===")
v2_roots = [r for r in Category.get_root_nodes() if r.is_site_v2]
for r in sorted(v2_roots, key=lambda x: x.name):
    print(f"V2ROOT|id={r.pk}|{r.name}|slug={r.slug}")
# есть ли Хозтовары/Авто среди v2?
names = {r.name.lower() for r in v2_roots}
print("HAS_v2_hoztovary=%s | HAS_v2_avto=%s" % (
    any("хозтовар" in n for n in names), any("авто" in n for n in names)))

prods = list(Product.objects.filter(category_id__in=sub_ids)
             .values("id", "name", "original_name", "is_active", "status",
                     "category_id", "category_is_manual"))


def nm(p):
    return p.get("original_name") or p["name"] or ""


def nrm(p):
    return nm(p).lower().replace("ё", "е")


def pub(p):
    return p["is_active"] and p["status"] == ProductStatus.PUBLISHED


BUCKETS = [
    ("3A Бытовая химия → Хозтовары", ["мыло", "стиральн", "порошок", "для посуд", "чистящ", "моющ", "фейри", "fairy", "пропер", "пятновывод", "отбелив", "санитарн", "унитаз", "освежит", "дезинфиц", "белизна", "для мытья"]),
    ("3B Автохимия → Авто", ["антифриз", "тосол", "стеклоом", "незамерз", "омыват", "автошампунь", "жидкость для запуска"]),
    ("3C Топоры → Ручной", ["топор"]),
    ("3C Гвоздодёры → Ручной", ["гвоздодер"]),
    ("3D Винты ГОСТ → Крепёж", ["винт с шестигранной головкой гост", "винт гост", " гост р исо 4017"]),
    ("3D Вибраторы → Электро/Оборуд", ["вибратор", "вибронаконечник", "виброрейк", "глубинный вибр"]),
]

for lab, kw in BUCKETS:
    aff = [p for p in prods if any(k in nrm(p) for k in kw)]
    manual = sum(1 for p in aff if p.get("category_is_manual"))
    leaves = collections.Counter(cat_name.get(p["category_id"]) for p in aff)
    print(f"\nBUCKET|{lab}|affected={len(aff)}|pub={sum(1 for p in aff if pub(p))}|category_is_manual=True:{manual}")
    for lname, c in leaves.most_common(4):
        print(f"   current_leaf|{lname}|{c}")
    for p in sorted(aff, key=lambda x: x["id"])[:6]:
        print(f"   [{p['id']}] manual=%s | %s" % (p.get("category_is_manual"), nm(p)[:60]))
