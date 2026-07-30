"""Phase 5: эффект для покупателя — фасеты и фильтруемость по мощности.

Считает через ТОТ ЖЕ код, что и витрина (build_facets), плюс прямые счётчики
по видимым товарам с tool_type=perforatory. Запускается до и после записи;
результат — JSON для сравнения.

Использование:
    python manage.py shell < scratchpad/parser-mvp/phase5_facets.py -- <out.json>
"""
import json
import os

from apps.catalog.facets import build_facets
from apps.catalog.models import Category, ProductAttributeValue

TT = "perforatory"
CATEGORY_SLUG = "elektroinstrument"
WATCH = ["power", "energy_impact", "no_load_speed", "chuck", "motor_type", "power_source", "voltage"]

out_path = os.environ.get("PHASE5_OUT", "phase5_facets.json")

category = Category.objects.get(slug=CATEGORY_SLUG)

# видимые перфораторы (через tool_type-PAV, как панель навигации витрины)
perf_ids = list(
    ProductAttributeValue.objects.filter(
        attribute__slug="tool_type", value_option__slug=TT,
        product__is_active=True, product__status="published",
    ).values_list("product_id", flat=True)
)

# сколько видимых перфораторов имеют значение по каждому наблюдаемому атрибуту
coverage = {}
for slug in WATCH:
    coverage[slug] = (
        ProductAttributeValue.objects.filter(
            product_id__in=perf_ids,
            attribute__slug=slug,
            product__is_active=True,
            product__status="published",
        )
        .exclude(value_decimal__isnull=True, value_option__isnull=True,
                 value_integer__isnull=True, value_text="")
        .values("product_id").distinct().count()
    )

# фасеты витрины: Электроинструмент + панель «Перфораторы»
facets = build_facets(category, tool_type=TT)
power_facet = next((f for f in facets.get("facets", []) if f.get("slug") == "power"), None)
chuck_facet = next((f for f in facets.get("facets", []) if f.get("slug") == "chuck"), None)

# конкретный покупательский запрос: перфораторы 800–1000 Вт
facets_filtered = build_facets(category, tool_type=TT, attr_ranges={"power": (800, 1000)})
perf_in_range = facets_filtered.get("total_products")
total_unfiltered = facets.get("total_products")

result = {
    "category": CATEGORY_SLUG,
    "tool_type": TT,
    "visible_perforatory": len(perf_ids),
    "total_products_facet": total_unfiltered,
    "coverage": coverage,
    "power_facet": power_facet,
    "chuck_facet": chuck_facet,
    "facets_keys": sorted(facets.keys()),
    "power_800_1000_count": perf_in_range,
}
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(result, fh, ensure_ascii=False, indent=2, default=str)
print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:2000])
