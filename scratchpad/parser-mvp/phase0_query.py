"""Phase 0 parser-MVP: read-only разведка «Дрели» + «Перфораторы» на staging.

Запускается через `manage.py shell -c "exec(open(...).read())"`.
Только SELECT: ничего не создаёт и не меняет.
"""

from django.db.models import Count, Q

from apps.catalog.models import AttributeOption, Category, Product

WORDS = ["дрел", "перфоратор"]


def line(t):
    print(f"\n{'=' * 72}\n{t}\n{'=' * 72}")


line("КАТЕГОРИИ")
for w in WORDS:
    for c in Category.objects.filter(name__icontains=w).values(
        "id", "name", "depth", "on_site", "is_site_v2"
    ):
        cnt = Product.objects.filter(category_id=c["id"]).count()
        pub = Product.objects.filter(category_id=c["id"], status="published").count()
        print(
            f"  id={c['id']:<6} d={c['depth']} on_site={c['on_site']!s:<5} "
            f"v2={c['is_site_v2']!s:<5} товаров={cnt:<6} published={pub:<6} {c['name']}"
        )

line("tool_type ОПЦИИ")
for w in WORDS:
    for o in AttributeOption.objects.filter(
        attribute__slug="tool_type", value__icontains=w
    ).values("id", "value", "slug"):
        cnt = Product.objects.filter(
            attribute_values__attribute__slug="tool_type",
            attribute_values__value_option_id=o["id"],
        ).count()
        print(f"  opt={o['id']:<6} товаров={cnt:<6} {o['value']}  [{o['slug']}]")

line("СОСТОЯНИЕ КОНТЕНТА по товарам с типом (дрели/перфораторы)")
opt_ids = list(
    AttributeOption.objects.filter(
        Q(attribute__slug="tool_type"),
        Q(value__icontains="дрел") | Q(value__icontains="перфоратор"),
    ).values_list("id", flat=True)
)
qs = Product.objects.filter(
    attribute_values__attribute__slug="tool_type",
    attribute_values__value_option_id__in=opt_ids,
).distinct()
total = qs.count()
pub = qs.filter(status="published").count()
no_img = qs.filter(images__isnull=True).count()
few_pav = qs.annotate(n=Count("attribute_values")).filter(n__lte=1).count()
locked = qs.filter(content_locked=True).count()
with_art = qs.exclude(article="").count()
print(f"  всего с типом:        {total}")
print(f"  published:            {pub}")
print(f"  без единого фото:     {no_img}")
print(f"  только tool_type PAV: {few_pav}   <- цель обогащения")
print(f"  content_locked:       {locked}   <- трогать нельзя")
print(f"  с непустым article:   {with_art}   <- основа матчинга")

line("ТОП КАТЕГОРИЙ размещения этих товаров")
for r in (
    qs.values("category_id", "category__name", "category__on_site")
    .annotate(n=Count("id"))
    .order_by("-n")[:10]
):
    print(
        f"  {r['n']:<5} cat={r['category_id']} on_site={r['category__on_site']!s:<5} "
        f"{r['category__name']}"
    )

line("ТОП БРЕНДОВ (оценка матчинга)")
for r in qs.values("brand").annotate(n=Count("id")).order_by("-n")[:12]:
    art = qs.filter(brand=r["brand"]).exclude(article="").count()
    print(f"  {r['n']:<4} с артикулом: {art:<4} {r['brand'] or '(пусто)'}")

line("НАСТРОЕННЫЕ ХАРАКТЕРИСТИКИ категорий (CategoryAttribute)")
cat_ids = [r["category_id"] for r in qs.values("category_id").annotate(n=Count("id")).order_by("-n")[:3]]
for cid in cat_ids:
    c = Category.objects.filter(id=cid).values("id", "name").first()
    if not c:
        continue
    attrs = list(
        Category.objects.get(id=cid)
        .category_attributes.select_related("attribute")
        .values_list("attribute__slug", "attribute__name")
    )
    print(f"  cat={c['id']} {c['name']}: {len(attrs)} атрибутов")
    for slug, nm in attrs[:15]:
        print(f"      - {slug}: {nm}")
