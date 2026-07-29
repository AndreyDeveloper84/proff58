# Живая проверка build_facets: угольники (override) vs ключи (fallback).
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.facets import build_facets  # noqa: E402
from apps.catalog.models import Category, CategoryAttribute  # noqa: E402

rows = CategoryAttribute.objects.filter(attribute__slug="size").select_related("category")
for row in rows:
    cat = row.category
    data = build_facets(cat)
    facet = next((f for f in data["facets"] if f["slug"] == "size"), None)
    print(
        f"{cat.slug}: override={row.display_name!r} -> facet="
        f"{None if facet is None else (facet['slug'], facet['name'], facet['unit'])}"
    )
