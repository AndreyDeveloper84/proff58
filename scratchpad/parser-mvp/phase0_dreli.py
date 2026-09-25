"""Phase 0 parser-MVP: read-only разведка категории «Дрели».

Ничего не пишет. Считает: где живут дрели (категории v2 + tool_type),
сколько товаров, у скольких нет фото и характеристик.
"""

import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.db.models import Count, Q  # noqa: E402

from apps.catalog.models import AttributeOption, Category, Product  # noqa: E402


def line(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


line("КАТЕГОРИИ со словом 'дрел'")
for c in Category.objects.filter(name__icontains="дрел").values(
    "id", "name", "slug", "depth", "on_site", "is_active", "is_site_v2"
):
    cnt = Product.objects.filter(category_id=c["id"]).count()
    print(
        f"  id={c['id']:<6} depth={c['depth']} on_site={c['on_site']!s:<5} "
        f"v2={c['is_site_v2']!s:<5} товаров={cnt:<6} {c['name']}"
    )

line("tool_type ОПЦИИ со словом 'дрел'")
for o in AttributeOption.objects.filter(
    attribute__slug="tool_type", value__icontains="дрел"
).values("id", "value", "slug"):
    cnt = Product.objects.filter(
        attribute_values__attribute__slug="tool_type",
        attribute_values__value_option_id=o["id"],
    ).count()
    print(f"  id={o['id']:<6} товаров={cnt:<6} {o['value']}  [{o['slug']}]")

line("ТОВАРЫ с 'дрел' в названии — общая картина")
qs = Product.objects.filter(Q(name__icontains="дрел") | Q(original_name__icontains="дрел"))
total = qs.count()
no_img = qs.filter(images__isnull=True).count()
no_pav = qs.annotate(n=Count("attribute_values")).filter(n=0).count()
print(f"  всего:              {total}")
print(f"  без единого фото:   {no_img}")
print(f"  без характеристик:  {no_pav}")

line("ТОП категорий, где лежат эти товары")
rows = (
    qs.values("category_id", "category__name", "category__on_site", "category__is_site_v2")
    .annotate(n=Count("id"))
    .order_by("-n")[:12]
)
for r in rows:
    print(
        f"  {r['n']:<6} cat_id={r['category_id']} on_site={r['category__on_site']!s:<5} "
        f"v2={r['category__is_site_v2']!s:<5} {r['category__name']}"
    )

line("ТОП брендов (оценка матчинга по бренду+артикулу)")
for r in qs.values("brand").annotate(n=Count("id")).order_by("-n")[:15]:
    with_article = qs.filter(brand=r["brand"]).exclude(article="").count()
    print(f"  {r['n']:<5} с артикулом: {with_article:<5} {r['brand'] or '(пусто)'}")
